from __future__ import annotations

import shutil
from pathlib import Path

from kit import config, ui
from kit.app import Action

from . import adguard, caddy, tailscale

APP = "network"
DESCRIPTION = "Rede da casa: acesso de fora (Tailscale), DNS com bloqueio (AdGuard) e endereços com HTTPS (Caddy)"


def status() -> bool:
    return tailscale.installed() and adguard.installed() and caddy.installed()


def install(reuse: bool | None = None) -> None:
    again = config.reuse(APP) if reuse is None else reuse
    tailscale.install(again)
    adguard.install(again)
    caddy.install(again)
    summary()


def remove() -> None:
    caddy.remove()
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
    for source in (caddy.env_file(), caddy.devices_file()):
        if source.exists():
            shutil.copy2(source, folder / source.name)


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
    for name, target in (("caddy.env", caddy.env_file()), ("devices.json", caddy.devices_file())):
        if (folder / name).exists():
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            shutil.copy2(folder / name, target)
            target.chmod(0o600)
    install(reuse=True)


def summary() -> None:
    ui.step("Resumo da rede")
    tailscale.summary()
    adguard.summary()
    caddy.summary()
    ui.section("Portas")
    ui.table(tailscale.port_rows() + adguard.port_rows() + caddy.port_rows(), ["Porta", "Para quê", "Firewall", "Roteador"])


def actions() -> list[Action]:
    return [
        Action("summary", "Resumo da rede", summary),
        Action("reconnect", "Reconectar ao Tailscale", tailscale.reconnect),
        Action("router", "Marcar o redirecionamento no roteador como feito", tailscale.mark_router),
        Action("devices", "Endereços de aparelhos da rede", caddy.manage_devices),
        Action("reload", "Recarregar os endereços do Caddy", caddy.reload),
        Action("router-dns", "Marcar o DNS no roteador como feito", adguard.mark_router),
    ]
