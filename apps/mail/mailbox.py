from __future__ import annotations

import email
import email.header
import email.policy
import fcntl
import json
import re
import secrets
import time
from datetime import datetime
from pathlib import Path

from kit import config, container, mailboxes, run, ui

from . import cloudflare

APP = "mail"
NAME = "astroverso-mail"
IMAGE = "docker.io/dovecot/dovecot:2.4.5"
USER = "inbox"
IMAP_PORT = 31143
SMTP_PORT = 31587
QUARANTINE = "Quarentena"
DOORBELL = "campainha"
KEY = re.compile(r"^(inbox|quarentena)\.(\d+)\.[0-9a-f-]+$")
CONF = Path(__file__).with_name("dovecot.conf")


def folder() -> Path:
    return config.state(APP)


def vmail() -> Path:
    return folder() / "vmail"


def users_file() -> Path:
    return folder() / "users"


def password_file() -> Path:
    return folder() / "secrets" / "imap_password"


def status_file() -> Path:
    return folder() / "fetch.json"


def spec() -> container.Container:
    return container.Container(
        name=NAME,
        image=IMAGE,
        description="Astroverso mail: caixa de e-mail (Dovecot)",
        volumes=[
            container.Volume(vmail(), "/srv/vmail", "Z,U"),
            container.Volume(users_file(), "/etc/dovecot/users", "ro,Z"),
            container.Volume(CONF, "/etc/dovecot/conf.d/astroverso.conf", "ro,z"),
        ],
    )


def installed() -> bool:
    return container.active(NAME)


def prepare() -> None:
    vmail().mkdir(exist_ok=True)
    password_file().parent.mkdir(mode=0o700, exist_ok=True)
    if not password_file().exists():
        password_file().touch(mode=0o600)
        password_file().write_text(secrets.token_urlsafe(24))
    if users_file().exists():
        return
    digest = run.capture(["openssl", "passwd", "-6", "-stdin"], input=password_file().read_text().strip())
    users_file().write_text(f"{USER}:{{SHA512-CRYPT}}{digest}\n")
    users_file().chmod(0o644)


def start() -> None:
    container.start(spec(), timeout=120)
    for _ in range(30):
        code, output = container.exec_output(NAME, ["doveadm", "mailbox", "create", "-u", USER, QUARANTINE])
        if code == 0 or "exists" in output.lower():
            return
        time.sleep(1)
    ui.warn(f"a pasta {QUARANTINE} não foi criada agora: ela aparece na primeira busca")


def publish(address: str) -> None:
    mailboxes.publish(APP, [mailboxes.Mailbox("inbox", address, NAME, IMAP_PORT, USER, str(password_file()), SMTP_PORT)])


def subject(raw: bytes) -> str:
    try:
        message = email.message_from_bytes(raw, policy=email.policy.default)
        return str(message.get("subject", "(sem assunto)")).replace("\n", " ")[:120] or "(sem assunto)"
    except Exception:
        return "(assunto ilegível)"


def _record(ok: bool, error: str = "", delivered: int = 0) -> None:
    previous = last_fetch()
    data = {"ok": ok, "error": error, "time": int(time.time()),
            "last_ok": int(time.time()) if ok else previous.get("last_ok", 0), "delivered": delivered}
    status_file().write_text(json.dumps(data) + "\n")


def last_fetch() -> dict:
    try:
        return json.loads(status_file().read_text())
    except (OSError, ValueError):
        return {}


def fetch(values: dict[str, str], force: bool) -> int:
    lock = open(folder() / ".fetch.lock", "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        ui.info("outra busca em andamento")
        return 0
    token, account, kv = values["CLOUDFLARE_API_TOKEN"], values["ACCOUNT_ID"], values["KV_ID"]
    try:
        if not force:
            if cloudflare.kv_get(token, account, kv, DOORBELL) is None:
                _record(True)
                return 0
            cloudflare.kv_remove(token, account, kv, DOORBELL)
        if not installed():
            raise cloudflare.CloudflareError(f"a caixa ({NAME}) está parada: os e-mails ficam guardados na Cloudflare")
        keys = sorted(key for key in cloudflare.kv_keys(token, account, kv) if KEY.match(key))
    except cloudflare.CloudflareError as problem:
        _record(False, str(problem))
        ui.fail(str(problem))
    delivered, failed = 0, []
    for key in keys:
        try:
            raw = cloudflare.kv_get(token, account, kv, key)
        except cloudflare.CloudflareError as problem:
            failed.append(str(problem))
            continue
        if raw is None:
            continue
        target = ["-m", QUARANTINE] if key.startswith("quarentena.") else []
        code, output = container.exec_output(NAME, ["doveadm", "save", "-u", USER, *target], input=raw)
        if code:
            failed.append(f"o Dovecot não aceitou {key}: {output.strip()[:200]}")
            continue
        try:
            cloudflare.kv_remove(token, account, kv, key)
        except cloudflare.CloudflareError as problem:
            failed.append(str(problem))
        delivered += 1
        ui.ok(f"entregue{' na ' + QUARANTINE if target else ''}: {subject(raw)}")
    if failed:
        _record(False, f"{len(failed)} e-mail(s) não chegaram: {failed[0]}", delivered)
        ui.fail(f"{len(failed)} e-mail(s) não chegaram à caixa (ficam na Cloudflare e são tentados de novo): {failed[0]}")
    _record(True, delivered=delivered)
    if delivered:
        ui.ok(f"{delivered} e-mail(s) novo(s)")
    else:
        ui.info("nenhum e-mail novo")
    return delivered


def pending(values: dict[str, str]) -> list[datetime]:
    keys = cloudflare.kv_keys(values["CLOUDFLARE_API_TOKEN"], values["ACCOUNT_ID"], values["KV_ID"])
    return [datetime.fromtimestamp(int(match.group(2)) / 1000) for key in keys if (match := KEY.match(key))]


def search_count(folder_name: str, *query: str) -> int:
    code, output = container.exec_output(NAME, ["doveadm", "search", "-u", USER, "mailbox", folder_name, *(query or ("all",))])
    return len([line for line in output.splitlines() if line.strip()]) if code == 0 else 0


def release(domain: str) -> int:
    count = search_count(QUARANTINE, "header", "X-Astroverso-Mail", f"@{domain}")
    if count and ui.confirm(f"Mover da {QUARANTINE} para a entrada os {count} e-mail(s) de @{domain}?", default=True):
        container.exec_output(NAME, ["doveadm", "move", "-u", USER, "INBOX", "mailbox", QUARANTINE, "header", "X-Astroverso-Mail", f"@{domain}"])
        ui.ok(f"{count} e-mail(s) de @{domain} movidos para a entrada")
    return count


def inbox(since: str = "") -> list[tuple[str, str, str]]:
    query = ["mailbox", "INBOX", "SINCE", since] if since else ["mailbox", "INBOX", "all"]
    code, output = container.exec_output(NAME, ["doveadm", "fetch", "-u", USER, "uid date.received hdr.subject", *query])
    found = []
    for block in output.split("\f") if code == 0 else []:
        fields: dict[str, str] = {}
        for line in block.strip("\n").split("\n"):
            key, _, value = line.partition(": ")
            if key in ("uid", "date.received", "hdr.subject"):
                fields[key] = value
        if "uid" not in fields:
            continue
        try:
            title = str(email.header.make_header(email.header.decode_header(fields.get("hdr.subject", ""))))
        except Exception:
            title = fields.get("hdr.subject", "")
        found.append((fields["uid"], fields.get("date.received", "")[:16] or "-", (title or "(sem assunto)").replace("\n", " ")[:90]))
    return found


def reprocess(uids: list[str]) -> int:
    count = 0
    for uid in uids:
        code, raw = container.exec_raw(NAME, ["doveadm", "fetch", "-u", USER, "text", "mailbox", "INBOX", "uid", uid])
        if raw.startswith(b"text:"):
            raw = raw[5:].lstrip(b" ")
            raw = raw[1:] if raw.startswith(b"\n") else raw
        if code or not raw.strip():
            ui.warn(f"não foi possível ler o e-mail {uid}")
            continue
        saved, _ = container.exec_output(NAME, ["doveadm", "save", "-u", USER, "-m", "INBOX"], input=raw)
        if saved:
            ui.warn(f"o Dovecot não aceitou de novo o e-mail {uid} (o original continua na entrada)")
            continue
        container.exec_output(NAME, ["doveadm", "expunge", "-u", USER, "mailbox", "INBOX", "uid", uid])
        ui.ok(f"entregue de novo: {subject(raw)}")
        count += 1
    ui.ok(f"{count} e-mail(s) entregue(s) de novo na entrada: as automações que leem a caixa os veem como novos")
    return count
