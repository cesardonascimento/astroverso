from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from kit import changes, config, discord, ui, units

COMMAND = Path(__file__).resolve().parents[2] / "astroverso"


@dataclass(frozen=True)
class Problem:
    level: str
    title: str
    text: str = ""
    kind: str = ""

    @property
    def identity(self) -> str:
        return self.kind or self.title


State = dict[str, dict[str, str]]


def name(app: str) -> str:
    return f"astroverso-{app}-watch"


def state_file(app: str) -> Path:
    return config.state(app) / "watch.json"


def load(app: str) -> State:
    try:
        saved = json.loads(state_file(app).read_text())
    except (OSError, ValueError):
        return {}
    return {key: value for key, value in saved.items() if isinstance(value, dict)} if isinstance(saved, dict) else {}


def save(app: str, state: State) -> None:
    temporary = state_file(app).with_suffix(".tmp")
    temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n")
    temporary.replace(state_file(app))


def carry(previous: State, key: str) -> Problem:
    item = previous[key]
    return Problem(item.get("level", "info"), item.get("title", key), item.get("text", ""), item.get("kind", ""))


def report(app: str, found: Mapping[str, Problem], previous: State, buttons: Sequence[tuple[str, str]] = (), healthy: str = "tudo em ordem") -> None:
    if not discord.configured():
        for problem in found.values():
            ui.warn(problem.title)
        ui.info("Discord não configurado nesta máquina: os problemas só aparecem aqui (instale o app discord)")
        return
    state = dict(previous)
    for key, problem in found.items():
        before = previous.get(key)
        if before and before.get("level") == problem.level and (before.get("kind") or before.get("title")) == problem.identity:
            continue
        if discord.notify(app, problem.level, problem.title, problem.text, actions=buttons):
            state[key] = {"level": problem.level, "title": problem.title, "text": problem.text, "kind": problem.kind}
            ui.warn(f"avisado no Discord: {problem.title}")
    for key, before in previous.items():
        if key in found:
            continue
        title = f"{before.get('title', key)}: resolvido"
        if discord.notify(app, "sucesso", title):
            state.pop(key, None)
            ui.ok(f"avisado no Discord: {title}")
    save(app, state)
    if not found:
        ui.ok(healthy)


def run(app: str, collect: Callable[[State], Mapping[str, Problem]], buttons: Sequence[tuple[str, str]] = (), healthy: str = "tudo em ordem") -> None:
    previous = load(app)
    report(app, collect(previous), previous, buttons, healthy)


def units_text(app: str, what: str) -> dict[str, str]:
    unit = name(app)
    return {
        f"{unit}.timer": "\n".join([
            "[Unit]",
            f"Description=Astroverso {app}: verifica {what} a cada hora e avisa no Discord",
            "",
            "[Timer]",
            "OnActiveSec=10min",
            "OnUnitActiveSec=1h",
            "RandomizedDelaySec=2min",
            "",
            "[Install]",
            "WantedBy=timers.target",
            "",
        ]),
        f"{unit}.service": "\n".join([
            "[Unit]",
            f"Description=Astroverso {app}: verificação de {what}",
            "",
            "[Service]",
            "Type=oneshot",
            f"ExecStart={COMMAND} {app} action watch",
            "",
        ]),
    }


def active(app: str) -> bool:
    return units.active(f"{name(app)}.timer")


def change(app: str, label: str, why: str, what: str) -> changes.Change:
    unit = name(app)
    return changes.Change(
        "watch", label, why,
        lambda: active(app),
        lambda: units.install(units_text(app, what), [f"{unit}.timer"]),
        lambda: units.remove([f"{unit}.timer", f"{unit}.service"]),
    )


def summary(app: str) -> None:
    state = load(app)
    ui.section("Verificação de hora em hora")
    rows: list[list[str | ui.Cell]] = [
        ["Verificação", ui.good("ligada") if active(app) else ui.pending("desligada")],
        ["Avisos no Discord", ui.good("ligados") if discord.configured() else ui.pending("instale o app discord")],
    ]
    for index, item in enumerate(state.values()):
        level = item.get("level", "")
        cell = ui.bad if level == "erro" else ui.pending if level == "aviso" else ui.off
        rows.append(["Aviso em aberto" if index == 0 else "", cell(item.get("title", ""))])
    if not state:
        rows.append(["Avisos em aberto", ui.good("nenhum")])
    ui.table(rows)
