from __future__ import annotations

import shutil
from pathlib import Path

from kit import vault
from kit import changes, config, discord, net, ui
from kit.app import Action

from . import agent, client, server

APP = "discord"
DESCRIPTION = "Bot do Discord do Astroverso: avisos dos apps em canais próprios e o comando /astro"
ORDER = 60
MODES = ("server", "client")


def mode() -> str:
    return config.load(APP).get("MODE", "") if config.env_file(APP).exists() else ""


def status() -> bool:
    return server.installed() if mode() == "server" else mode() == "client" and discord.configured()


def install(reuse: bool | None = None) -> None:
    again = config.reuse(APP) if reuse is None else reuse
    ui.step("Discord: o bot do Astroverso")
    ui.note(
        "O bot fica num servidor do Discord só do Astroverso, com um canal para cada app. Os apps de todas as máquinas "
        "da casa mandam avisos para lá (um cadeado perto de vencer, um backup que falhou), e o comando /astro roda "
        "ações deles. Uma máquina roda o bot; as outras só usam o bot dela."
    )
    chosen = mode() if again and mode() in MODES else ""
    if not chosen:
        choice = ui.menu("Esta máquina", [
            "Roda o bot (a primeira máquina da casa com o Discord)",
            "Usa o bot que roda em outra máquina",
        ])
        chosen = MODES[choice]
    if chosen == "server":
        server.install(again)
    else:
        client.install(again)
    agent.install(again)
    changes.install(APP, [vault.change(APP)], again)
    summary()


def remove() -> None:
    ui.step("Discord")
    changes.undo_all([vault.change(APP)])
    agent.remove()
    if mode() == "server":
        server.remove()
    discord.forget()
    config.purge(APP)


def backup(folder: Path) -> None:
    source = config.env_file(APP)
    if source.exists():
        shutil.copy2(source, folder / ".env")
    if server.keys_folder().exists() and mode() == "server":
        shutil.copytree(server.keys_folder(), folder / "clients", dirs_exist_ok=True)
    if discord.settings_file().exists():
        shutil.copy2(discord.settings_file(), folder / "discord.env")


def restore(folder: Path) -> None:
    source = folder / ".env"
    if not source.exists():
        ui.fail(f"backup sem a configuração do {APP}: {source}")
    config.state(APP)
    shutil.copy2(source, config.env_file(APP))
    config.env_file(APP).chmod(0o600)
    if (folder / "clients").is_dir():
        shutil.copytree(folder / "clients", server.keys_folder(), dirs_exist_ok=True)
        server.keys_folder().chmod(0o700)
        for key in server.keys_folder().iterdir():
            key.chmod(0o600)
    if (folder / "discord.env").exists():
        shutil.copy2(folder / "discord.env", discord.settings_file())
        discord.settings_file().chmod(0o600)
    install(reuse=True)


def summary() -> None:
    ui.step("Resumo do Discord")
    if mode() == "server":
        server.summary()
    client.summary()


def test() -> None:
    if not discord.configured():
        ui.fail("esta máquina ainda não está ligada ao bot: instale o app discord")
    if discord.notify(APP, "info", "Mensagem de teste", f"Enviada por {net.hostname()} pelo gerenciador do Astroverso."):
        ui.ok("mensagem enviada ao canal #discord")


def manage() -> None:
    changes.manage(APP, agent.items() + [vault.change(APP)])


def actions() -> list[Action]:
    common = [
        Action("summary", "Resumo do Discord", summary, remote=True),
        Action("changes", "Mudanças no sistema", manage),
        Action("test", "Mensagem de teste", test, remote=True),
        Action("agent", "Agente do Discord", agent.serve, menu=False),
        Action("backup-now", "Fazer backup agora", lambda: vault.run_backup(APP, backup), remote=True),
        Action("restore-version", "Restaurar uma fotografia", lambda: vault.restore(APP, backup, restore)),
    ]
    if mode() != "server":
        return common
    return common + [
        Action("key", "Mostrar a chave de um cliente", server.show_key),
        Action("add-client", "Adicionar um cliente", server.add_client),
    ]
