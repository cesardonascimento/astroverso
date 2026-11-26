from __future__ import annotations

import re

from kit import config, distro, net, ui

APP = "system"
LABEL = re.compile(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$")


def validate(value: str) -> str:
    text = value.strip().lower()
    if not LABEL.match(text):
        raise ValueError("use letras minúsculas, números e hífen (até 63), sem hífen no começo nem no fim")
    return text


def apply(name: str) -> None:
    current = net.hostname()
    if name == current:
        ui.ok(f"nome da máquina: {name}")
        return
    distro.hostname_set(name)
    ui.ok(f"nome da máquina trocado: {current} → {name}")
    ui.warn("o nome antigo continua no Tailscale, no endereço do Cockpit e nos backups: reinstale os apps que já estavam instalados")


def install(reuse: bool) -> None:
    saved = config.load(APP).get("HOSTNAME", "")
    if not (reuse and saved):
        ui.note(
            "O nome identifica esta máquina na rede da casa, no Tailscale, no endereço do painel "
            "(<nome-da-máquina>.<domínio>) e nos backups. Defina antes de instalar os outros apps."
        )
        saved = ui.ask("nome da máquina", default=saved or net.hostname(), validate=validate)
        config.save(APP, {"HOSTNAME": saved})
    apply(saved)


def summary() -> None:
    ui.section("Nome da máquina")
    saved = config.load(APP).get("HOSTNAME", "")
    current = net.hostname()
    situation = ui.good("aplicado") if not saved or saved == current else ui.pending(f"definido {saved}, atual {current}")
    ui.table([["Nome", current], ["Situação", situation]])
