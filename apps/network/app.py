from __future__ import annotations

import shutil
from pathlib import Path

from kit import config, ui
from kit.app import Action

from . import tailscale

APP = "network"
DESCRIPTION = "Rede da casa: acesso de fora pelo Tailscale (AdGuard e Caddy em breve)"


def status() -> bool:
    return tailscale.installed()


def install(reuse: bool | None = None) -> None:
    tailscale.install(config.reuse(APP) if reuse is None else reuse)
    summary()


def remove() -> None:
    tailscale.remove()
    config.purge(APP)


def backup(folder: Path) -> None:
    source = config.env_file(APP)
    if source.exists():
        shutil.copy2(source, folder / ".env")


def restore(folder: Path) -> None:
    source = folder / ".env"
    if not source.exists():
        ui.fail(f"backup sem a configuração do {APP}: {source}")
    config.state(APP)
    target = config.env_file(APP)
    shutil.copy2(source, target)
    target.chmod(0o600)
    install(reuse=True)


def summary() -> None:
    ui.step("Resumo da rede")
    tailscale.summary()


def actions() -> list[Action]:
    return [
        Action("summary", "Resumo da rede", summary),
        Action("reconnect", "Reconectar ao Tailscale", tailscale.reconnect),
        Action("router", "Marcar o redirecionamento no roteador como feito", tailscale.mark_router),
    ]
