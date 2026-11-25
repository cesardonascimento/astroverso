from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from kit import config, ui


@dataclass(frozen=True)
class Linked:
    path: Path
    label: str
    app: str = ""


def folder() -> Path:
    return config.home() / "clouds"


def _file(app: str) -> Path:
    if not config.APP.match(app):
        ui.fail(f"nome de app inválido: {app!r}")
    return folder() / f"{app}.json"


def publish(app: str, items: Sequence[Linked]) -> None:
    path = _file(app)
    content = json.dumps([{"path": str(item.path), "label": item.label} for item in items], ensure_ascii=False, indent=2) + "\n"
    try:
        if path.read_text() == content:
            return
    except FileNotFoundError:
        pass
    folder().mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = config.home() / f".clouds-{app}.json.tmp"
    temporary.write_text(content)
    temporary.replace(path)


def withdraw(app: str) -> None:
    path = _file(app)
    if path.exists():
        path.unlink()


def load() -> list[Linked]:
    found: list[Linked] = []
    if not folder().is_dir():
        return found
    for path in sorted(folder().glob("*.json")):
        try:
            items = json.loads(path.read_text())
        except ValueError:
            continue
        for item in items if isinstance(items, list) else []:
            if isinstance(item, dict) and item.get("path") and item.get("label"):
                found.append(Linked(Path(str(item["path"])), str(item["label"]), path.stem))
    return found


def mark(path: Path) -> str:
    for item in load():
        if path == item.path or item.path in path.parents:
            return item.label
    return ""
