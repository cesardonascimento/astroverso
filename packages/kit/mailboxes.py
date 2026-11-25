from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

from kit import config, ui


@dataclass(frozen=True)
class Mailbox:
    name: str
    address: str
    host: str
    port: int
    user: str
    password_file: str
    smtp_port: int = 0
    app: str = ""

    def password(self) -> str:
        return Path(self.password_file).read_text().strip()


def folder() -> Path:
    return config.home() / "mailboxes"


def _file(app: str) -> Path:
    if not config.APP.match(app):
        ui.fail(f"nome de app inválido: {app!r}")
    return folder() / f"{app}.json"


def publish(app: str, boxes: Sequence[Mailbox]) -> None:
    path = _file(app)
    content = json.dumps([{key: value for key, value in asdict(box).items() if key != "app"} for box in boxes], indent=2) + "\n"
    try:
        if path.read_text() == content:
            return
    except FileNotFoundError:
        pass
    folder().mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = config.home() / f".mailboxes-{app}.json.tmp"
    temporary.write_text(content)
    temporary.chmod(0o600)
    temporary.replace(path)
    ui.ok(f"caixa de e-mail publicada para os outros apps: {', '.join(box.address for box in boxes)}")


def withdraw(app: str) -> None:
    path = _file(app)
    if path.exists():
        path.unlink()
        ui.ok("caixa de e-mail retirada dos outros apps")


def load() -> list[Mailbox]:
    found: list[Mailbox] = []
    if not folder().is_dir():
        return found
    fields = set(Mailbox.__dataclass_fields__) - {"app"}
    for path in sorted(folder().glob("*.json")):
        try:
            items = json.loads(path.read_text())
        except ValueError:
            ui.warn(f"caixas ignoradas, arquivo inválido: {path}")
            continue
        for item in items if isinstance(items, list) else []:
            if isinstance(item, dict) and {"name", "address", "host", "port", "user", "password_file"} <= set(item):
                found.append(Mailbox(**{key: value for key, value in item.items() if key in fields}, app=path.stem))
    return found
