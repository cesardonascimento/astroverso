from __future__ import annotations

import json
import re
import threading
import time

from kit import changes, discord, run, ui, units
from manager.apps import ROOT, discover, installed

NAME = "astroverso-discord-agent"
COMMAND = ROOT / "astroverso"
REFRESH = 300
WAIT = 50
TIMEOUT = 780
PREFIX = re.compile(r"^\[[a-z0-9-]+\] {0,7}", re.MULTILINE)


def manifest() -> dict[str, list[dict]]:
    catalog: list[dict] = []
    guide: list[dict] = []
    for app in discover():
        if app.module is None or not installed(app):
            continue
        try:
            actions = app.actions()
        except Exception as problem:
            ui.warn(f"ações de {app.name} ignoradas: {problem}")
            continue
        for action in actions:
            if not action.remote:
                continue
            command = f"{app.name}:{action.id}"
            catalog.append({"id": command, "descricao": f"{app.name}: {action.label}"[:90], "confirmar": action.confirm, "tipo": "host"})
            guide.append({"grupo": f"{app.name} — {app.description}", "nome": action.label, "descricao": "",
                          "quando": "quando quiser", "comando": command})
    return {"catalogo": catalog, "ajuda": guide, "canais": [], "botoes": []}


def execute(command: str, known: set[str]) -> dict[str, object]:
    if command not in known:
        return {"ok": False, "saida": f"{command} não está disponível nesta máquina"}
    app, _, action = command.partition(":")
    ui.info(f"rodando {command} a pedido do Discord")
    code, output = run.output([str(COMMAND), app, "action", action], timeout=TIMEOUT, env={"NO_COLOR": "1"})
    return {"ok": code == 0, "saida": PREFIX.sub("", output).strip()}


def handle(event: dict, known: set[str]) -> None:
    kind = event.get("tipo")
    if kind == "comando":
        answer: dict[str, object] = execute(str(event.get("acao") or ""), known)
    elif kind == "botao":
        answer = {"texto": "este botão não é mais usado"}
    else:
        answer = {}
    try:
        discord.request("POST", f"/v1/eventos/{event.get('id')}/resposta", answer)
    except discord.DiscordError as problem:
        ui.warn(f"resposta não entregue ao Discord: {problem}")


def serve() -> None:
    if not discord.configured():
        ui.fail("esta máquina não está ligada ao bot: instale o app discord")
    ui.info("agente do Discord ligado: esperando comandos do /astro")
    published = ""
    refreshed = 0.0
    known: set[str] = set()
    while True:
        try:
            if time.monotonic() - refreshed > REFRESH:
                current = manifest()
                text = json.dumps(current, sort_keys=True)
                if text != published:
                    discord.request("PUT", "/v1/cliente", current)
                    published = text
                    known = {item["id"] for item in current["catalogo"]}
                    ui.ok(f"comandos publicados: {', '.join(sorted(known)) or 'nenhum'}")
                refreshed = time.monotonic()
            events = discord.request("GET", f"/v1/eventos?espera={WAIT}", timeout=WAIT + 15).get("eventos") or []
            for event in events:
                if isinstance(event, dict):
                    threading.Thread(target=handle, args=(event, set(known)), daemon=True).start()
        except discord.DiscordError as problem:
            ui.warn(f"bot fora do ar ({problem}): tentando de novo em 15 s")
            published = ""
            refreshed = 0.0
            time.sleep(15)


def unit_text() -> dict[str, str]:
    return {
        f"{NAME}.service": "\n".join([
            "[Unit]",
            "Description=Astroverso discord: agente que roda nesta máquina os comandos do /astro",
            "After=network-online.target",
            "",
            "[Service]",
            f"ExecStart={COMMAND} discord action agent",
            "Restart=always",
            "RestartSec=30",
            "",
            "[Install]",
            "WantedBy=default.target",
            "",
        ]),
    }


def _start() -> None:
    units.install(unit_text(), [f"{NAME}.service"])


def items() -> list[changes.Change]:
    return [
        changes.Change(
            "agent", "Rodar o agente do /astro nesta máquina",
            f"Um serviço do usuário ({NAME}) publica no bot as ações dos apps desta máquina e roda as que forem pedidas "
            "no comando /astro do Discord. Sem ele, esta máquina só manda avisos.",
            active, _start, remove,
        ),
    ]


def install(reuse: bool) -> None:
    was_active = active()
    changes.install("discord", items(), reuse)
    if was_active and active():
        units.restart(f"{NAME}.service")


def remove() -> None:
    units.remove([f"{NAME}.service"])


def active() -> bool:
    return units.active(f"{NAME}.service")
