from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from kit import config, ui


@dataclass(frozen=True)
class Route:
    host: str
    target: str
    app: str = ""


def folder() -> Path:
    return config.home() / "routes"


def _file(app: str) -> Path:
    if not config.APP.match(app):
        ui.fail(f"nome de app inválido: {app!r}")
    return folder() / f"{app}.json"


def publish(app: str, routes: Sequence[Route]) -> None:
    path = _file(app)
    content = json.dumps([{"host": route.host, "target": route.target} for route in routes], indent=2) + "\n"
    try:
        if path.read_text() == content:
            return
    except FileNotFoundError:
        pass
    folder().mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = config.home() / f".routes-{app}.json.tmp"
    temporary.write_text(content)
    temporary.replace(path)
    ui.ok(f"endereço publicado: {', '.join('https://' + route.host for route in routes)}")


def withdraw(app: str) -> None:
    path = _file(app)
    if path.exists():
        path.unlink()
        ui.ok("endereço retirado")


def load() -> list[Route]:
    found: list[Route] = []
    if not folder().is_dir():
        return found
    for path in sorted(folder().glob("*.json")):
        try:
            items = json.loads(path.read_text())
        except ValueError:
            ui.warn(f"endereços ignorados, arquivo inválido: {path}")
            continue
        for item in items if isinstance(items, list) else []:
            if isinstance(item, dict) and item.get("host") and item.get("target"):
                found.append(Route(str(item["host"]), str(item["target"]), path.stem))
    return found
