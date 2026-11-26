from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class Action:
    id: str
    label: str
    run: Callable[[], None]
    remote: bool = False
    confirm: bool = False
    menu: bool = True


class App(Protocol):
    DESCRIPTION: str
    ORDER: int

    def status(self) -> bool: ...

    def install(self) -> None: ...

    def remove(self) -> None: ...

    def backup(self, folder: Path) -> None: ...

    def restore(self, folder: Path) -> None: ...


REQUIRED: tuple[str, ...] = ("DESCRIPTION", "status", "install", "remove", "backup", "restore")
