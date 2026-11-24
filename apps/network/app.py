from __future__ import annotations

import shutil
from pathlib import Path

from kit import config, ui
from kit.app import Action

from . import adguard, tailscale

APP = "network"
DESCRIPTION = "Rede da casa: acesso de fora (Tailscale) e DNS com bloqueio (AdGuard); Caddy em breve"


def status() -> bool:
    return tailscale.installed() and adguard.installed()


def install(reuse: bool | None = None) -> None:
    again = config.reuse(APP) if reuse is None else reuse
    tailscale.install(again)
    adguard.install(again)
    summary()


def remove() -> None:
    adguard.remove()
    tailscale.remove()
    config.purge(APP)


def backup(folder: Path) -> None:
    source = config.env_file(APP)
    if source.exists():
        shutil.copy2(source, folder / ".env")
    conf = adguard.conf_file()
    if conf.exists():
        shutil.copy2(conf, folder / "AdGuardHome.yaml")


def restore(folder: Path) -> None:
    source = folder / ".env"
    if not source.exists():
        ui.fail(f"backup sem a configuração do {APP}: {source}")
    config.state(APP)
    target = config.env_file(APP)
    shutil.copy2(source, target)
    target.chmod(0o600)
    saved = folder / "AdGuardHome.yaml"
    if saved.exists():
        adguard.conf_file().parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        shutil.copy2(saved, adguard.conf_file())
        adguard.conf_file().chmod(0o600)
    install(reuse=True)


def summary() -> None:
    ui.step("Resumo da rede")
    tailscale.summary()
    adguard.summary()
    ui.section("Portas")
    ui.table(tailscale.port_rows() + adguard.port_rows(), ["Porta", "Para quê", "Firewall", "Roteador"])


def actions() -> list[Action]:
    return [
        Action("summary", "Resumo da rede", summary),
        Action("reconnect", "Reconectar ao Tailscale", tailscale.reconnect),
        Action("router", "Marcar o redirecionamento no roteador como feito", tailscale.mark_router),
        Action("router-dns", "Marcar o DNS no roteador como feito", adguard.mark_router),
    ]
