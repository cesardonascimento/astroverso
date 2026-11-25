from __future__ import annotations

import fcntl
import json
import os
import re
import time
import zlib
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path

from kit import clouds, config, disks, ui

from . import proton, rclone

APP = "cloud"
PROVIDERS = {proton.NAME: proton}
KINDS = {"sync": "duas vias", "send": "envio"}
RESYNC = ("must run --resync", "cannot find prior Path1 or Path2 listings", "--resync")
TOO_MANY = ("too many deletes", "max-delete", "--max-delete")
LOCKS = Path.home() / ".cache" / "rclone" / "bisync"


@dataclass(frozen=True)
class Account:
    id: str
    provider: str
    user: str

    def label(self) -> str:
        return f"{PROVIDERS[self.provider].LABEL} ({self.user})" if self.provider in PROVIDERS else self.id


@dataclass(frozen=True)
class Job:
    id: str
    kind: str
    local: str
    account: str
    remote: str

    def target(self) -> str:
        return f"{self.account}:{self.remote}"

    def arrow(self) -> str:
        return "⇄" if self.kind == "sync" else "⇒"


def _read(name: str) -> list[dict]:
    try:
        items = json.loads((config.state(APP) / name).read_text())
    except (OSError, ValueError):
        return []
    return [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []


def _save(name: str, items: list[dict]) -> None:
    path = config.state(APP) / name
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(items, ensure_ascii=False, indent=2) + "\n")
    temporary.chmod(0o600)
    temporary.replace(path)


def accounts() -> list[Account]:
    return [Account(str(item["id"]), str(item["provider"]), str(item.get("user", ""))) for item in _read("accounts.json")
            if item.get("id") and item.get("provider")]


def save_accounts(items: list[Account]) -> None:
    _save("accounts.json", [asdict(item) for item in items])


def account(id: str) -> Account | None:
    return next((item for item in accounts() if item.id == id), None)


def new_account_id(provider: str) -> str:
    taken = {item.id for item in accounts()}
    number = 1
    while f"{provider}-{number}" in taken:
        number += 1
    return f"{provider}-{number}"


def jobs() -> list[Job]:
    return [Job(str(item["id"]), str(item["kind"]), str(item["local"]), str(item["account"]), str(item.get("remote", "")))
            for item in _read("jobs.json") if item.get("id") and item.get("kind") in KINDS and item.get("local") and item.get("account")]


def save_jobs(items: list[Job]) -> None:
    _save("jobs.json", [asdict(item) for item in items])
    publish()


def new_job_id(kind: str, local: str, target: str) -> str:
    return f"{zlib.crc32(f'{kind}|{local}|{target}'.encode()):08x}"


def publish() -> None:
    linked = []
    for job in jobs():
        owner = account(job.account)
        provider = PROVIDERS[owner.provider].LABEL if owner and owner.provider in PROVIDERS else job.account
        linked.append(clouds.Linked(Path(job.local), f"{provider} ({KINDS[job.kind]})"))
    if linked:
        clouds.publish(APP, linked)
    else:
        clouds.withdraw(APP)


def state_file() -> Path:
    return config.state(APP) / "state.json"


def states() -> dict[str, dict]:
    try:
        saved = json.loads(state_file().read_text())
    except (OSError, ValueError):
        return {}
    return {key: value for key, value in saved.items() if isinstance(value, dict)} if isinstance(saved, dict) else {}


def record(job: Job, error: str = "", blocked: bool = False) -> None:
    saved = states()
    item = saved.get(job.id, {})
    item.update({"error": error, "blocked": blocked, "tried": int(time.time())})
    if not error:
        item["ok"] = int(time.time())
    saved[job.id] = item
    temporary = state_file().with_suffix(".tmp")
    temporary.write_text(json.dumps(saved, ensure_ascii=False, indent=2) + "\n")
    temporary.replace(state_file())


@contextmanager
def locked(wait: bool) -> Iterator[bool]:
    with open(config.state(APP) / "run.lock", "w") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | (0 if wait else fcntl.LOCK_NB))
        except BlockingIOError:
            yield False
            return
        try:
            yield True
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def _options(job: Job) -> list[str]:
    owner = account(job.account)
    return list(PROVIDERS[owner.provider].OPTIONS) if owner and owner.provider in PROVIDERS else []


def _ready(job: Job) -> str:
    path = Path(job.local)
    if not disks.available(path) or not path.is_dir():
        return f"{job.local} indisponível (disco desligado, travado ou pasta apagada): nada foi feito"
    if job.account not in rclone.sections():
        return f"a conta {job.account} não está conectada: entre de novo em Contas na nuvem"
    return ""


def _clear_locks() -> None:
    for path in LOCKS.glob("*.lck") if LOCKS.is_dir() else []:
        path.unlink(missing_ok=True)


def sync_args(job: Job, resync: bool = False, force: bool = False, dry: bool = False) -> list[str]:
    args = ["bisync", job.local, job.target(), "--resilient", "--recover", "--max-lock", "2h",
            "--conflict-resolve", "newer", "--conflict-loser", "num", "--max-delete", "5", "--exclude", "*.partial", *_options(job)]
    if resync:
        args += ["--resync", "--resync-mode", "newer"]
    if force:
        args.append("--force")
    if dry:
        args.append("--dry-run")
    return args


def count_files(path: Path) -> int:
    return sum(len(names) for _, _, names in os.walk(path))


def send_args(job: Job, force: bool = False, dry: bool = False) -> list[str]:
    args = ["sync", job.local, job.target(), "--exclude", "*.partial", *_options(job)]
    if not force:
        args += ["--max-delete", str(max(10, count_files(Path(job.local)) * 5 // 100))]
    if dry:
        args.append("--dry-run")
    return args


def _blocked(output: str) -> bool:
    text = output.lower()
    return any(item in text for item in TOO_MANY)


def run_job(job: Job, force: bool = False) -> bool:
    problem = _ready(job)
    if problem:
        record(job, problem)
        ui.warn(problem)
        return False
    ui.info(f"{job.local} {job.arrow()} {job.target()}...")
    if job.kind == "sync":
        first = "ok" not in states().get(job.id, {})
        code, output = rclone.call(sync_args(job, resync=first, force=force), unshare=True)
        if code and not first and any(item in output.lower() for item in RESYNC) and not _blocked(output):
            ui.info("o estado da sincronização se perdeu: juntando os dois lados sem apagar nada (--resync)")
            code, output = rclone.call(sync_args(job, resync=True), unshare=True)
    else:
        code, output = rclone.call(send_args(job, force=force), unshare=True)
    if code == 0:
        record(job)
        ui.ok(f"{job.local} {job.arrow()} {job.target()} em dia")
        return True
    if _blocked(output):
        record(job, "parou para não apagar arquivos demais: confira e use Liberar exclusões", blocked=True)
        ui.warn(f"{job.local}: parou para não apagar arquivos demais (use Liberar exclusões)")
        return False
    record(job, rclone.tail(output))
    ui.warn(f"{job.local} {job.arrow()} {job.target()} falhou: {rclone.tail(output)}")
    return False


def run_kind(kind: str, wait: bool) -> bool:
    chosen = [job for job in jobs() if job.kind == kind]
    if not chosen:
        ui.info(f"nenhum{'a sincronização' if kind == 'sync' else ' envio'} cadastrad{'a' if kind == 'sync' else 'o'}")
        return True
    with locked(wait) as mine:
        if not mine:
            ui.info("outra rodada do rclone está em andamento: esta fica para a próxima")
            return True
        _clear_locks()
        return all([run_job(job) for job in chosen])


def preview(job: Job) -> list[str]:
    args = sync_args(job, force=True, dry=True) if job.kind == "sync" else send_args(job, force=True, dry=True)
    _, output = rclone.call(args, unshare=True)
    return [line.strip() for line in output.splitlines() if re.search(r"delet", line, re.IGNORECASE)]
