from __future__ import annotations

import base64
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ElementTree
import zlib
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path

from kit import changes, config, discord, net, run, ui, units

COMMAND = Path(__file__).resolve().parents[2] / "astroverso"
CHANNEL = "vault"
KEYS = ("VAULT_URL", "VAULT_USER", "VAULT_PASSWORD", "VAULT_FOLDER", "VAULT_KEY")
KEEP_DAYS = 90
SUFFIX = ".tar.zst.gpg"
DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
LABEL = re.compile(r"^[a-z0-9-]+$")
DAV = "{DAV:}"


class DavError(Exception):
    pass


def settings_file() -> Path:
    return config.home() / "vault.env"


def settings() -> dict[str, str]:
    return config.read_env(settings_file())


def configured() -> bool:
    values = settings()
    return all(values.get(key) for key in KEYS)


def save(url: str, user: str, password: str, folder: str, key: str) -> None:
    config.home().mkdir(mode=0o700, exist_ok=True)
    config.write_env(settings_file(), dict(zip(KEYS, (url.rstrip("/"), user, password, clean_folder(folder), key))))


def forget() -> None:
    if settings_file().exists():
        settings_file().unlink()
        ui.ok("esta máquina deixou de mandar backups")


def clean_folder(value: str) -> str:
    parts = [part for part in value.strip().split("/") if part]
    if not parts or any(part in (".", "..") for part in parts):
        raise ValueError("uma pasta do Nextcloud, como /Backups")
    return "/" + "/".join(parts)


class Dav:
    def __init__(self, values: dict[str, str] | None = None, timeout: float = 120) -> None:
        values = values or settings()
        self.base = f"{values['VAULT_URL']}/remote.php/dav/files/{urllib.parse.quote(values['VAULT_USER'])}"
        token = base64.b64encode(f"{values['VAULT_USER']}:{values['VAULT_PASSWORD']}".encode()).decode()
        self.headers = {"Authorization": f"Basic {token}"}
        self.timeout = timeout

    def url(self, path: str) -> str:
        return self.base + "/" + "/".join(urllib.parse.quote(part) for part in path.split("/") if part)

    def request(self, method: str, path: str, data: bytes | None = None, headers: dict[str, str] | None = None) -> tuple[int, bytes]:
        request = urllib.request.Request(self.url(path), data=data, method=method, headers={**self.headers, **(headers or {})})
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return response.status, response.read()
        except urllib.error.HTTPError as error:
            with error:
                return error.code, error.read()
        except (urllib.error.URLError, OSError) as error:
            raise DavError(f"o Nextcloud não respondeu: {getattr(error, 'reason', error)}") from None

    def names(self, path: str) -> list[str] | None:
        code, body = self.request("PROPFIND", path, b"", {"Depth": "1"})
        if code == 404:
            return None
        _check(code, path)
        try:
            root = ElementTree.fromstring(body)
        except ElementTree.ParseError:
            raise DavError("o Nextcloud respondeu algo que não é uma lista de arquivos") from None
        own = urllib.parse.urlparse(self.url(path)).path.rstrip("/")
        found = []
        for item in root.iter(f"{DAV}response"):
            href = urllib.parse.unquote((item.findtext(f"{DAV}href") or "").rstrip("/"))
            if href and href != urllib.parse.unquote(own):
                found.append(href.rsplit("/", 1)[-1])
        return found

    def mkdirs(self, path: str) -> None:
        done = ""
        for part in [part for part in path.split("/") if part]:
            done += "/" + part
            code, _ = self.request("MKCOL", done)
            if code not in (201, 405):
                _check(code, done)

    def put(self, path: str, source: Path) -> None:
        code, _ = self.request("PUT", path, source.read_bytes(), {"Content-Type": "application/octet-stream"})
        _check(code, path)

    def get(self, path: str, target: Path) -> None:
        code, body = self.request("GET", path)
        _check(code, path)
        target.write_bytes(body)

    def delete(self, path: str) -> None:
        code, _ = self.request("DELETE", path)
        if code != 404:
            _check(code, path)


def _check(code: int, path: str) -> None:
    if code in (401, 403):
        raise DavError("o Nextcloud recusou o usuário ou a senha de app")
    if code == 507:
        raise DavError("o Nextcloud está sem espaço")
    if code >= 300:
        raise DavError(f"o Nextcloud recusou {path} (HTTP {code})")


def verify(values: dict[str, str]) -> str:
    try:
        dav = Dav(values, timeout=30)
        dav.mkdirs(values["VAULT_FOLDER"])
        if dav.names(values["VAULT_FOLDER"]) is None:
            return f"a pasta {values['VAULT_FOLDER']} não foi criada"
    except DavError as error:
        return str(error)
    return ""


def machine_folder(values: dict[str, str] | None = None) -> str:
    values = values or settings()
    return f"{values['VAULT_FOLDER']}/{net.hostname()}"


def file_name(app: str, label: str = "") -> str:
    return f"{app}{'-' + label if label else ''}{SUFFIX}"


def days(dav: Dav, folder: str) -> list[str]:
    return sorted((name for name in dav.names(folder) or [] if DAY.match(name)), reverse=True)


def unit(app: str, part: str = "") -> str:
    return f"astroverso-{app}-backup" + (f"-{part}" if part else "")


def minute(app: str) -> int:
    return zlib.crc32(app.encode()) % 60


def units_text(app: str) -> dict[str, str]:
    name = unit(app)
    return {
        f"{name}.timer": "\n".join([
            "[Unit]",
            f"Description=Astroverso {app}: backup da configuração todo dia",
            "",
            "[Timer]",
            f"OnCalendar=*-*-* 01:{minute(app):02d}:00",
            "Persistent=true",
            "",
            "[Install]",
            "WantedBy=timers.target",
            "",
        ]),
        f"{name}.service": "\n".join([
            "[Unit]",
            f"Description=Astroverso {app}: backup da configuração",
            "After=network-online.target",
            "",
            "[Service]",
            "Type=oneshot",
            f"ExecStart={COMMAND} {app} action backup-now",
            "",
        ]),
    }


def _enable(texts: dict[str, str]) -> None:
    if not configured():
        ui.warn("esta máquina ainda não manda backups (instale o app vault): ligue o backup depois, em Mudanças no sistema")
        return
    units.install(texts, [name for name in texts if name.endswith(".timer")])


def change(app: str) -> changes.Change:
    texts = units_text(app)
    return changes.Change(
        "backup", f"Fazer o backup da configuração do {app} todo dia (01:{minute(app):02d})",
        f"Um timer do usuário ({unit(app)}.timer) guarda a configuração do {app} num arquivo criptografado e envia para a "
        f"pasta dos backups no Nextcloud (app vault), um por dia, guardados por {KEEP_DAYS} dias, e avisa no canal #vault "
        "do Discord. Se a máquina estava desligada no horário, o backup roda ao ligar.",
        lambda: units.active(f"{unit(app)}.timer"),
        lambda: _enable(texts),
        lambda: units.remove(list(texts)),
    )


def _stage(app: str) -> Path:
    return config.home() / ".backups" / app


def _clean(folder: Path) -> None:
    if folder.exists():
        run.cmd(["podman", "unshare", "rm", "-rf", "--", str(folder)])


def pack(folder: Path, target: Path, key: str) -> str:
    archive = target.with_suffix("")
    code, output = run.output(["podman", "unshare", "tar", "--zstd", "-C", str(folder), "-cf", str(archive), "."])
    if code:
        return f"o tar não empacotou: {output.strip()[-300:]}"
    code, output = run.output(["gpg", "--batch", "--yes", "--quiet", "--pinentry-mode", "loopback", "--passphrase-fd", "0",
                               "--symmetric", "--cipher-algo", "AES256", "-o", str(target), str(archive)], input=key + "\n")
    archive.unlink(missing_ok=True)
    return f"o gpg não criptografou: {output.strip()[-300:]}" if code else ""


def unpack(source: Path, target: Path, key: str) -> str:
    archive = source.with_suffix("")
    code, output = run.output(["gpg", "--batch", "--yes", "--quiet", "--pinentry-mode", "loopback", "--passphrase-fd", "0",
                               "-o", str(archive), "-d", str(source)], input=key + "\n")
    if code:
        archive.unlink(missing_ok=True)
        return "a senha dos backups não abriu o arquivo" if "decryption failed" in output.lower() else f"o gpg não abriu: {output.strip()[-300:]}"
    code, output = run.output(["podman", "unshare", "tar", "--zstd", "-C", str(target), "-xf", str(archive)])
    archive.unlink(missing_ok=True)
    return f"o tar não abriu: {output.strip()[-300:]}" if code else ""


def prune(dav: Dav, folder: str, today: date | None = None) -> int:
    limit = (today or date.today()) - timedelta(days=KEEP_DAYS)
    gone = 0
    for day in days(dav, folder):
        if date.fromisoformat(day) < limit:
            dav.delete(f"{folder}/{day}")
            gone += 1
    return gone


def _report(app: str, problem: str, seconds: int, where: str, notify: bool) -> bool:
    host = net.hostname()
    if problem:
        ui.warn(f"backup do {app} falhou: {problem}")
        if notify:
            discord.notify(CHANNEL, "erro", f"Backup do {app} falhou em {host}", problem, actions=(("Tentar de novo", f"{app}:backup-now"),))
        return False
    ui.ok(f"backup do {app} enviado em {seconds} s ({where})")
    if notify:
        discord.notify(CHANNEL, "info", f"Backup do {app} feito em {host}", f"Em {seconds} s, em {where}.")
    return True


def run_backup(app: str, save_function: Callable[[Path], None], label: str = "", notify: bool = True) -> bool:
    if not configured():
        ui.info("esta máquina ainda não manda backups (instale o app vault): nada a fazer")
        return False
    values = settings()
    started = time.monotonic()
    folder = _stage(app)
    _clean(folder)
    content = folder / "conteudo"
    content.mkdir(parents=True, mode=0o700)
    target = folder / file_name(app, label)
    remote = f"{machine_folder(values)}/{date.today().isoformat()}"
    problem = ""
    try:
        save_function(content)
    except SystemExit:
        problem = "o backup do app falhou (veja a mensagem acima)"
    except Exception as error:
        problem = f"falha inesperada: {error}"
    if not problem:
        problem = pack(content, target, values["VAULT_KEY"])
    if not problem:
        try:
            dav = Dav(values)
            dav.mkdirs(remote)
            dav.put(f"{remote}/{target.name}", target)
            prune(dav, machine_folder(values))
        except DavError as error:
            problem = str(error)
    _clean(folder)
    return _report(app, problem, int(time.monotonic() - started), f"{remote}/{target.name}", notify)


def versions(app: str, dav: Dav | None = None, limit: int = 30) -> list[tuple[str, str]]:
    dav = dav or Dav()
    folder = machine_folder()
    found: list[tuple[str, str]] = []
    for day in days(dav, folder):
        for name in sorted(dav.names(f"{folder}/{day}") or []):
            if name == file_name(app) or (name.startswith(f"{app}-") and name.endswith(SUFFIX)
                                          and LABEL.match(name[len(app) + 1:-len(SUFFIX)])):
                found.append((day, name))
        if len(found) >= limit:
            break
    return found[:limit]


def when(item: tuple[str, str], app: str) -> str:
    day, name = item
    extra = name[len(app):-len(SUFFIX)].lstrip("-")
    return datetime.strptime(day, "%Y-%m-%d").strftime("%d/%m/%Y") + (f" ({extra})" if extra else "")


def _pick(app: str) -> tuple[str, str] | None:
    try:
        found = versions(app)
    except DavError as error:
        ui.fail(str(error))
    if not found:
        ui.fail(f"ainda não há nenhum backup do {app} desta máquina no Nextcloud")
    index = ui.menu("De quando restaurar?", [when(item, app) for item in found] + ["Voltar"])
    return None if index >= len(found) else found[index]


def _fetch(app: str, item: tuple[str, str], target: Path) -> None:
    values = settings()
    work = _stage(app)
    _clean(work)
    work.mkdir(parents=True, mode=0o700)
    target.mkdir(parents=True, mode=0o700)
    try:
        source = work / item[1]
        Dav(values).get(f"{machine_folder(values)}/{item[0]}/{item[1]}", source)
        problem = unpack(source, target, values["VAULT_KEY"])
    except DavError as error:
        problem = str(error)
    finally:
        _clean(work)
    if problem:
        _clean(target)
        ui.fail(f"não deu para trazer o backup: {problem}")


@contextmanager
def opened(app: str) -> Iterator[tuple[Path, str] | None]:
    if not configured():
        ui.fail("esta máquina ainda não manda backups: instale o app vault")
    item = _pick(app)
    if item is None:
        yield None
        return
    target = config.home() / ".backup-restore" / app
    _clean(target)
    _fetch(app, item, target)
    try:
        yield target, when(item, app)
    finally:
        _clean(target)


def restore(app: str, save_function: Callable[[Path], None], restore_function: Callable[[Path], None]) -> None:
    if not configured():
        ui.fail("esta máquina ainda não manda backups: instale o app vault")
    item = _pick(app)
    if item is None:
        return
    ui.warn(f"restaurar troca a configuração atual do {app} pela de {when(item, app)}")
    if not ui.confirm("Restaurar?", default=False):
        return
    ui.info("guardando antes a situação atual (backup \"antes-da-restauracao\")...")
    run_backup(app, save_function, "antes-da-restauracao", notify=False)
    target = config.home() / ".backup-restore" / app
    _clean(target)
    _fetch(app, item, target)
    try:
        restore_function(target)
    finally:
        _clean(target)
    ui.ok(f"{app} restaurado do backup de {when(item, app)}")


def summary(app: str) -> None:
    ui.section("Backup")
    if not configured():
        ui.table([["Vault", ui.pending("esta máquina ainda não manda backups (app vault)")]])
        return
    on = units.active(f"{unit(app)}.timer")
    try:
        found = versions(app, limit=1)
        last: str | ui.Cell = ui.good(when(found[0], app)) if found else ui.pending("nenhum ainda")
    except DavError as error:
        last = ui.bad(str(error))
    ui.table([["Backup diário", ui.good("ligado") if on else ui.pending("desligado")], ["Último", last],
              ["Pasta", machine_folder()]])
