from __future__ import annotations

import shutil
from pathlib import Path

from kit import clouds, disks, ui
from kit.ui import Validator

OTHER = "Digitar outra pasta…"


def human(size: float) -> str:
    for unit in ("B", "K", "M", "G"):
        if size < 1024:
            return f"{size:.0f}{unit}"
        size /= 1024
    return f"{size:.1f}T"


def _existing(path: Path) -> Path:
    while not path.exists() and path != path.parent:
        path = path.parent
    return path


def describe(path: Path) -> str:
    disk = disks.containing(path)
    parts = [f"disco {disk.name}" if disk else "disco do sistema"]
    if disk is None or disks.available(path):
        try:
            usage = shutil.disk_usage(_existing(path))
            parts.append(f"{human(usage.free)} livres de {human(usage.total)}")
        except OSError:
            pass
    else:
        parts.append("indisponível")
    label = clouds.mark(path)
    if label:
        parts.append(f"☁ {label}")
    return " · ".join(parts)


def suggestions(current: str = "") -> list[Path]:
    found: list[Path] = []
    for path in [Path(current).expanduser()] if current else []:
        found.append(path)
    found += [disk.path for disk in disks.mounts()]
    found += [item.path for item in clouds.load()]
    found.append(Path.home())
    unique: list[Path] = []
    for path in found:
        if path not in unique:
            unique.append(path)
    return unique


def pick(question: str, current: str = "", validate: Validator | None = None) -> str:
    options = suggestions(current)
    index = ui.menu(question, [str(path) for path in options] + [OTHER], [describe(path) for path in options])
    start = options[index] if index < len(options) else Path(current or Path.home()).expanduser()
    ui.note(f"Enter usa {start}. Um nome sem / vira uma subpasta dela (criada se não existir); um caminho completo troca a pasta.")

    def check(value: str) -> str:
        path = Path(value.strip()).expanduser()
        text = str(path if path.is_absolute() else start / path)
        return validate(text) if validate else text

    return ui.ask(question, default=str(start), validate=check)
