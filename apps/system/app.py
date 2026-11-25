from __future__ import annotations

import shutil
from pathlib import Path

from kit import backup as kit_backup
from kit import changes, config, ui
from kit.app import Action

from . import power, ssh

APP = "system"
DESCRIPTION = "Configurações da máquina: sempre ligada (energia) e acesso remoto (SSH e chave para o GitHub)"


def items() -> list[changes.Change]:
    return power.items() + ssh.items() + [kit_backup.change(APP)]


def status() -> bool:
    return config.env_file(APP).exists()


def install(reuse: bool | None = None) -> None:
    again = config.reuse(APP) if reuse is None else reuse
    ui.step("Energia: sempre ligada")
    ui.note(
        "Estes ajustes garantem que a máquina fique sempre ligada e acessível, mesmo de tampa fechada. Cada um é "
        "perguntado e pode ser desfeito depois em Gerenciar → Mudanças no sistema."
    )
    changes.install(APP, power.items(), again)
    ui.step("SSH: acesso remoto")
    changes.install(APP, ssh.items(), again)
    ssh.install(again)
    changes.install(APP, [kit_backup.change(APP)], again)
    summary()


def remove() -> None:
    ui.step("Configurações da máquina")
    changes.undo_all([item for item in items() if item.id != "ssh-server"])
    ui.info(f"o servidor SSH e o {ssh.authorized_file()} ficam, para você não perder o acesso")
    config.purge(APP)


def backup(folder: Path) -> None:
    for source in (config.env_file(APP), ssh.keys_file()):
        if source.exists():
            shutil.copy2(source, folder / source.name)


def restore(folder: Path) -> None:
    source = folder / ".env"
    if not source.exists():
        ui.fail(f"backup sem a configuração do {APP}: {source}")
    config.state(APP)
    for name, target in ((".env", config.env_file(APP)), ("ssh-keys.json", ssh.keys_file())):
        if (folder / name).exists():
            shutil.copy2(folder / name, target)
            target.chmod(0o600)
    install(reuse=True)


def summary() -> None:
    ui.step("Resumo da máquina")
    ui.section("Mudanças no sistema")
    ui.table(changes.rows(items()), ["Mudança", "Situação"])
    ssh.summary()


def manage() -> None:
    changes.manage(APP, items())


def actions() -> list[Action]:
    return [
        Action("summary", "Resumo da máquina", summary, remote=True),
        Action("changes", "Mudanças no sistema", manage),
        Action("keys", "Chaves SSH autorizadas", ssh.manage_keys),
        Action("github", "Chave desta máquina para o GitHub", ssh.github),
        Action("backup-now", "Fazer backup agora", lambda: kit_backup.run_backup(APP, backup), remote=True),
        Action("restore-version", "Restaurar uma versão", lambda: kit_backup.restore(APP, backup, restore)),
    ]
