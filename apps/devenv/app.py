from __future__ import annotations

import os
import re
import shutil
from pathlib import Path

from kit import backup as kit_backup
from kit import changes, config, run, ui
from kit.app import Action

APP = "devenv"
DESCRIPTION = "Ambiente de desenvolvimento no terminal: os programas do astroverso-devenv e as configurações do astroverso-dotfiles"
PROJECTS = Path.home() / "Projects"
REPO = re.compile(r"^(git@[\w.-]+:[\w./-]+?|https://[\w.-]+/[\w./-]+?)(\.git)?$")
PROGRAMS = ("zsh", "starship", "zellij", "asdf", "node", "pnpm", "claude", "podman", "docker", "podman-compose")
TIMER = "astroverso-dotfiles-update.timer"
BATCH = {"GIT_SSH_COMMAND": "ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new", "GIT_TERMINAL_PROMPT": "0"}


def items() -> list[changes.Change]:
    return [kit_backup.change(APP)]


def status() -> bool:
    return config.env_file(APP).exists() and folder("DOTFILES").is_dir()


def _repo(value: str) -> str:
    value = value.strip()
    if not REPO.match(value):
        raise ValueError("endereço de um repositório git, como git@github.com:<conta>/<repositório>.git")
    return value


def folder(key: str) -> Path:
    url = config.load(APP).get(f"{key}_REPO", "")
    name = url.rstrip("/").rsplit("/", 1)[-1].rsplit(":", 1)[-1].removesuffix(".git")
    return PROJECTS / (name or key.lower())


def reachable(url: str, agent: bool = True) -> bool:
    env = dict(BATCH) if agent else {**BATCH, "SSH_AUTH_SOCK": ""}
    return run.output(["git", "ls-remote", "--heads", url], env=env, timeout=60)[0] == 0


def fetch(key: str) -> Path:
    url = config.load(APP)[f"{key}_REPO"]
    path = folder(key)
    if (path / ".git").is_dir():
        ui.info(f"atualizando {path}...")
        code, output = run.output(["git", "-C", str(path), "pull", "--ff-only", "--quiet"], env=BATCH, timeout=300)
        if code:
            ui.fail(f"não deu para atualizar {path}: {output.strip()[-300:]}")
    else:
        PROJECTS.mkdir(exist_ok=True)
        ui.info(f"clonando {url} em {path}...")
        code, output = run.output(["git", "clone", "--quiet", url, str(path)], env=BATCH, timeout=600)
        if code:
            ui.fail(f"não deu para clonar {url}: {output.strip()[-300:]}")
    return path


def _ask(reuse: bool) -> None:
    values = config.load(APP)
    if reuse and values.get("DEVENV_REPO") and values.get("DOTFILES_REPO"):
        return
    ui.note("Os endereços dos dois repositórios (os seus, no GitHub). Ficam só nesta máquina.")
    config.save(APP, {
        "DEVENV_REPO": ui.ask("repositório do astroverso-devenv", default=values.get("DEVENV_REPO") or None, validate=_repo),
        "DOTFILES_REPO": ui.ask("repositório do astroverso-dotfiles", default=values.get("DOTFILES_REPO") or None, validate=_repo),
    })


def _access() -> None:
    for key in ("DEVENV", "DOTFILES"):
        url = config.load(APP)[f"{key}_REPO"]
        if not reachable(url):
            ui.warn(f"sem acesso a {url}")
            ui.note(
                "Repositório privado precisa da máquina aceita pelo GitHub: a chave desta máquina (app system → Chave desta "
                "máquina para o GitHub) ou o agente do seu computador (entre com ssh -A)."
            )
            ui.fail("sem acesso aos repositórios")


def apply() -> None:
    _access()
    devenv = fetch("DEVENV")
    script = devenv / "linux" / "install.sh"
    if not script.is_file():
        ui.fail(f"{script} não existe: o astroverso-devenv precisa ter o linux/install.sh")
    run.sudo_prepare("instalar os programas do astroverso-devenv")
    run.cmd([str(script)], timeout=3600)
    dotfiles = fetch("DOTFILES")
    run.cmd([str(dotfiles / "install.sh")], timeout=600)
    ui.ok("ambiente aplicado: abra um terminal novo (ou exec zsh)")


def update_problems() -> list[str]:
    found = []
    if not run.succeeds(["systemctl", "--user", "is-enabled", "-q", TIMER]):
        found.append("o timer do dotfiles-update não está ligado (rode o install.sh dos dotfiles)")
    linger = run.output(["loginctl", "show-user", os.environ.get("USER", ""), "-p", "Linger", "--value"], timeout=10)[1].strip()
    if linger != "yes":
        found.append("o linger está desligado: o timer só roda com você logado (sudo loginctl enable-linger $USER)")
    url = config.load(APP).get("DOTFILES_REPO", "")
    if url.startswith("git@") and not reachable(url, agent=False):
        found.append("sem o agente do seu computador, esta máquina não alcança o repositório dos dotfiles: cadastre a chave "
                     "desta máquina no GitHub (app system → Chave desta máquina para o GitHub)")
    return found


def check_update() -> None:
    problems = update_problems()
    for problem in problems:
        ui.warn(f"dotfiles-update: {problem}")
    if not problems:
        ui.ok("dotfiles-update pronto: o timer roda todo dia, sozinho")


def install(reuse: bool | None = None) -> None:
    again = config.reuse(APP) if reuse is None else reuse
    ui.step("Ambiente de desenvolvimento")
    ui.note(
        "Instala os programas do seu astroverso-devenv (zsh, Starship, Zellij, asdf com Node, Claude Code, Podman com "
        "docker compatível) pelo linux/install.sh dele e aplica o seu astroverso-dotfiles por cima. As configurações são "
        "todas dos dotfiles."
    )
    _ask(again)
    apply()
    check_update()
    changes.install(APP, items(), again)
    summary()


def remove() -> None:
    ui.step("Ambiente de desenvolvimento")
    changes.undo_all(items())
    ui.info(f"os programas, os repositórios ({folder('DEVENV')}, {folder('DOTFILES')}) e as configurações dos dotfiles "
            "ficam como estão: este app só os instalou")
    config.purge(APP)


def backup(target: Path) -> None:
    shutil.copy2(config.env_file(APP), target / ".env")


def restore(source: Path) -> None:
    if not (source / ".env").exists():
        ui.fail(f"backup sem a configuração do {APP}")
    config.state(APP)
    shutil.copy2(source / ".env", config.env_file(APP))
    config.env_file(APP).chmod(0o600)
    install(reuse=True)


def _commit(path: Path) -> str:
    code, output = run.output(["git", "-C", str(path), "log", "-1", "--format=%h %cd", "--date=format:%d/%m/%Y"], timeout=10)
    return output.strip() if code == 0 else "-"


def _found(program: str) -> bool:
    places = os.pathsep.join(["/usr/local/bin", str(Path.home() / ".local" / "bin"),
                              str(Path(os.environ.get("ASDF_DATA_DIR", Path.home() / ".asdf")) / "shims"), os.environ.get("PATH", "")])
    return shutil.which(program, path=places) is not None


def summary() -> None:
    ui.step("Resumo do ambiente de desenvolvimento")
    ui.section("Repositórios")
    ui.table([[key.lower(), str(folder(key)), _commit(folder(key)) if folder(key).is_dir() else ui.pending("não clonado")]
              for key in ("DEVENV", "DOTFILES")], ["Repositório", "Pasta", "Último commit"])
    ui.section("Programas")
    ui.table([[program, ui.good("instalado") if _found(program) else ui.bad("falta")] for program in PROGRAMS], ["Programa", "Situação"])
    ui.section("Atualização dos dotfiles")
    problems = update_problems()
    ui.table([["dotfiles-update", ui.good("pronto (todo dia)") if not problems else ui.pending(f"{len(problems)} pendência(s)")]]
             + [["", ui.pending(problem)] for problem in problems])


def manage() -> None:
    changes.manage(APP, items())


def actions() -> list[Action]:
    return [
        Action("summary", "Resumo do ambiente", summary, remote=True),
        Action("update", "Atualizar (puxa os repositórios e roda os instaladores)", lambda: (apply(), check_update())),
        Action("check", "Conferir o dotfiles-update", check_update, remote=True),
        Action("changes", "Mudanças no sistema", manage),
        Action("backup-now", "Fazer backup agora", lambda: kit_backup.run_backup(APP, backup), remote=True),
        Action("restore-version", "Restaurar uma versão", lambda: kit_backup.restore(APP, backup, restore)),
    ]
