from __future__ import annotations

import os
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

from kit import distro, ui
from manager.apps import APPS, ROOT, LoadedApp, call, discover, install, installed, interrupted, present, remove

USAGE = "uso: astroverso [<app> install | remove | status | backup <pasta> | restore <pasta> | action <id>]"


def ensure_command(home: Path | None = None) -> None:
    folder = (home or Path.home()) / ".local" / "bin"
    link = folder / "astroverso"
    target = ROOT / "astroverso"
    if link.is_symlink() or link.exists():
        return
    folder.mkdir(parents=True, exist_ok=True)
    link.symlink_to(target)
    ui.ok(f"comando astroverso criado em {link}")
    if str(folder) not in os.environ.get("PATH", "").split(os.pathsep):
        ui.warn(f"{folder} não está no PATH: abra um novo terminal ou use {target}")


def _valid(apps: list[LoadedApp]) -> list[LoadedApp]:
    for app in apps:
        if app.problem:
            ui.warn(f"app inválido: {app.name}: {app.problem}")
    return [app for app in apps if app.module]


def _stopped(stop: KeyboardInterrupt) -> None:
    if not isinstance(stop, ui.Cancelled):
        sys.stdout.write("\n")


def _run(app: LoadedApp, what: str, function: Callable[..., tuple[bool, object]], *args: object) -> bool | None:
    try:
        return function(*args)[0]
    except KeyboardInterrupt as stop:
        _stopped(stop)
        ui.warn(f"{what} cancelada")
        return None


def _confirm(question: str) -> bool:
    try:
        return ui.confirm(question)
    except ui.Cancelled:
        return False


def _details(apps: list[LoadedApp]) -> list[str]:
    return [f"instalação interrompida: {app.description}" if interrupted(app) else app.description for app in apps]


def _install(apps: list[LoadedApp]) -> None:
    pending = [app for app in apps if not installed(app)]
    if not pending:
        ui.ok("todos os apps já estão instalados")
        return
    chosen = ui.checklist(
        "Quais apps instalar?", [app.name for app in pending], all_option=True, cancel=True, details=_details(pending)
    )
    if not chosen:
        return
    done: list[str] = []
    failed: list[str] = []
    skipped: list[str] = []
    for position, index in enumerate(chosen):
        app = pending[index]
        ui.step(f"Instalando {app.name}")
        ui.note("Esc cancela a instalação e volta ao menu.")
        success = _run(app, f"instalação do {app.name}", install, app)
        if success is None:
            skipped = [pending[i].name for i in chosen[position:]]
            break
        (done if success else failed).append(app.name)
    ui.step("Resumo")
    if done:
        ui.ok(f"instalados: {', '.join(done)}")
    if failed:
        ui.error(f"falharam: {', '.join(failed)}")
    if skipped:
        ui.warn(f"cancelados: {', '.join(skipped)}")


def _manage_app(app: LoadedApp) -> None:
    while True:
        success, actions = call(app, app.actions)
        actions = [action for action in actions if action.menu] if success else []
        labels = [action.label for action in actions] + ["Reinstalar", "Remover", "Voltar"]
        choice = ui.menu(f"Gerenciar {app.name}", labels)
        if choice < len(actions):
            ui.step(actions[choice].label)
            _run(app, f"ação {actions[choice].label}", call, app, actions[choice].run)
        elif labels[choice] == "Reinstalar":
            ui.step(f"Reinstalando {app.name}")
            ui.note("Esc cancela a instalação e volta ao menu.")
            if _run(app, f"instalação do {app.name}", install, app):
                ui.ok(f"{app.name} reinstalado")
        elif labels[choice] == "Remover":
            if _confirm(f"remover o {app.name}?"):
                ui.step(f"Removendo {app.name}")
                if _run(app, f"remoção do {app.name}", remove, app):
                    ui.ok(f"{app.name} removido")
                    return
        else:
            return


def _manage(apps: list[LoadedApp]) -> None:
    while True:
        shown = [app for app in apps if present(app)]
        if not shown:
            ui.warn("nenhum app instalado")
            return
        choice = ui.menu("Qual app?", [app.name for app in shown] + ["Voltar"], details=_details(shown))
        if choice == len(shown):
            return
        _manage_app(shown[choice])


def interactive(folder: Path) -> int:
    ui.banner()
    distro.check()
    while True:
        apps = _valid(discover(folder))
        if not apps:
            ui.warn("nenhum app disponível ainda")
            return 0
        choice = ui.menu("O que fazer?", ["Instalar apps", "Gerenciar apps", "Sair"])
        if choice == 0:
            _install(apps)
        elif choice == 1:
            _manage(apps)
        else:
            return 0


def direct(folder: Path, argv: Sequence[str]) -> int:
    if len(argv) < 2:
        ui.fail(USAGE)
    name, command, *rest = argv
    app = next((app for app in discover(folder) if app.name == name), None)
    if app is None:
        ui.fail(f"app não encontrado: {name}")
    if app.module is None:
        ui.fail(f"app inválido: {app.name}: {app.problem}")
    if command != "status":
        distro.check()
    if command == "status" and not rest:
        done = installed(app)
        situation = "instalado" if done else "instalação interrompida" if interrupted(app) else "não instalado"
        ui.info(f"{app.name}: {situation}")
        return 0 if done else 1
    if command in ("install", "remove") and not rest:
        return 0 if (install if command == "install" else remove)(app)[0] else 1
    if command in ("backup", "restore") and len(rest) == 1:
        return 0 if call(app, getattr(app.module, command), Path(rest[0]))[0] else 1
    if command == "action" and len(rest) == 1:
        success, actions = call(app, app.actions)
        action = next((action for action in actions or [] if action.id == rest[0]), None) if success else None
        if action is None:
            ui.fail(f"ação não encontrada: {rest[0]}")
        return 0 if call(app, action.run)[0] else 1
    ui.fail(USAGE)


def main(argv: Sequence[str] | None = None, folder: Path = APPS) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    try:
        if not args:
            return interactive(folder)
        if args[0] in ("-h", "--help", "ajuda"):
            ui.info(USAGE)
            return 0
        return direct(folder, args)
    except KeyboardInterrupt as stop:
        _stopped(stop)
        ui.warn("interrompido")
        return 130
