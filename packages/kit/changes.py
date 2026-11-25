from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from kit import config, ui


@dataclass(frozen=True)
class Change:
    id: str
    label: str
    why: str
    applied: Callable[[], bool]
    apply: Callable[[], None]
    undo: Callable[[], None]
    danger: bool = False


def key(change: Change) -> str:
    return "CHANGE_" + re.sub(r"[^A-Z0-9]", "_", change.id.upper())


def wanted(app: str, change: Change) -> bool | None:
    saved = config.load(app).get(key(change))
    return None if saved is None else saved == "yes"


def _save(app: str, answers: dict[Change, bool]) -> None:
    config.save(app, {key(change): "yes" if on else "no" for change, on in answers.items()})


def _warn_danger(app: str, change: Change) -> None:
    ui.warn(f"sem isso, o {app} pode não funcionar direito: refaça em Gerenciar → Mudanças no sistema")


def ask(app: str, changes: Sequence[Change], reuse: bool) -> dict[Change, bool]:
    answers: dict[Change, bool] = {}
    for change in changes:
        saved = wanted(app, change)
        if reuse and saved is not None:
            answers[change] = saved
            continue
        ui.note(change.why)
        answers[change] = ui.confirm(f"{change.label}?", default=True if saved is None else saved)
        if change.danger and not answers[change]:
            _warn_danger(app, change)
    _save(app, answers)
    return answers


def _set(change: Change, on: bool) -> None:
    if on and not change.applied():
        change.apply()
    elif not on and change.applied():
        change.undo()


def install(app: str, changes: Sequence[Change], reuse: bool) -> None:
    for change, on in ask(app, changes, reuse).items():
        _set(change, on)


def manage(app: str, changes: Sequence[Change]) -> None:
    current = [change.applied() for change in changes]
    chosen = ui.checklist(
        "Mudanças no sistema (marcadas = aplicadas; ⚠ = importante para o funcionamento)",
        [change.label for change in changes],
        selected=[i for i, on in enumerate(current) if on],
        danger=[i for i, change in enumerate(changes) if change.danger],
        cancel=True,
    )
    if chosen is None:
        return
    answers: dict[Change, bool] = {}
    for i, change in enumerate(changes):
        on = i in chosen
        if on == current[i]:
            continue
        if change.danger and not on and not ui.confirm(f"{change.label} é importante para o {app}. Desfazer mesmo?", default=False):
            continue
        _set(change, on)
        answers[change] = on
    _save(app, answers)
    if not answers:
        ui.info("nada mudou")


def undo_all(changes: Sequence[Change]) -> None:
    for change in reversed(changes):
        if change.applied():
            change.undo()


def rows(changes: Sequence[Change]) -> list[list[str | ui.Cell]]:
    return [
        [f"⚠ {change.label}" if change.danger else change.label, ui.good("aplicada") if change.applied() else ui.off("desfeita")]
        for change in changes
    ]
