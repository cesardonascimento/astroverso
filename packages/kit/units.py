from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

from kit import run, ui


def folder() -> Path:
    return Path.home() / ".config" / "systemd" / "user"


def _write(path: Path, content: str) -> bool:
    try:
        if path.read_text() == content:
            return False
    except FileNotFoundError:
        pass
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(content)
    temporary.replace(path)
    return True


def active(name: str) -> bool:
    return run.succeeds(["systemctl", "--user", "is-active", "-q", name])


def install(units: Mapping[str, str], start: Sequence[str]) -> None:
    changed = [name for name, content in units.items() if _write(folder() / name, content)]
    if changed:
        run.cmd(["systemctl", "--user", "daemon-reload"], quiet=True)
    for name in start:
        if not active(name):
            run.cmd(["systemctl", "--user", "enable", "--now", name], quiet=True)
            ui.ok(f"unidade {name} ligada")
        elif name in changed:
            run.cmd(["systemctl", "--user", "restart", name], quiet=True)


def restart(name: str) -> None:
    run.cmd(["systemctl", "--user", "restart", name], quiet=True)


def remove(names: Sequence[str]) -> None:
    present = [name for name in names if (folder() / name).exists()]
    for name in present:
        run.succeeds(["systemctl", "--user", "disable", "--now", name])
        (folder() / name).unlink()
        run.succeeds(["systemctl", "--user", "reset-failed", name])
    if present:
        run.cmd(["systemctl", "--user", "daemon-reload"], quiet=True)
        ui.ok(f"unidades removidas: {', '.join(present)}")
