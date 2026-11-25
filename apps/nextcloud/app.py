from __future__ import annotations

import shutil
from pathlib import Path

from kit import changes, config, container, docs, routes, ui, validate, watch
from kit.app import Action

from . import backup as copies
from . import nextcloud

APP = "nextcloud"
DESCRIPTION = "Nuvem própria: arquivos, fotos, agenda e contatos em https://nextcloud.<domínio>"
DOCS = Path(__file__).with_name("docs")
BUTTONS = (("Resumo do Nextcloud", "nextcloud:summary"), ("Verificar de novo", "nextcloud:watch"))


def items() -> list[changes.Change]:
    return [
        watch.change(
            APP, "Verificar o Nextcloud de hora em hora e avisar no Discord",
            f"Um timer do usuário ({watch.name(APP)}.timer) confere a cada hora se os containers estão no ar, se o "
            "Nextcloud saiu da manutenção, os erros da verificação do próprio Nextcloud e o espaço livre da pasta dos "
            "arquivos, e avisa no Discord quando algo quebra e quando volta ao normal.",
            "o Nextcloud",
        ),
    ]


def status() -> bool:
    return nextcloud.installed()


def _ask(reuse: bool) -> str:
    values = config.load(APP)
    domain = config.domain()
    first = not nextcloud.created()
    if reuse and values.get("HOST") and values.get("FILES") and not first:
        return ""
    ui.note(f"O endereço do Nextcloud, igual dentro e fora de casa. O padrão é nextcloud.{domain}.")
    address = ui.ask("endereço do Nextcloud", default=values.get("HOST") or f"nextcloud.{domain}", validate=nextcloud.validate_host)
    answers = {"HOST": address}
    password = ""
    if first:
        ui.note("A conta de administrador do Nextcloud. O nome não muda depois da instalação; a senha, sim (Gerenciar → Trocar a senha).")
        answers["ADMIN_USER"] = ui.ask("usuário administrador", default=values.get("ADMIN_USER") or "astroverso", validate=validate.name)
        password = ui.secret(f"senha do administrador {answers['ADMIN_USER']}")
        ui.note(
            "A pasta onde ficam os arquivos de todos os usuários do Nextcloud. Ela pertence ao Nextcloud: só ele mexe "
            "nos arquivos dela."
        )
        answers["FILES"] = ui.ask("pasta dos arquivos", default=values.get("FILES") or str(nextcloud.DEFAULT_FILES),
                                  validate=nextcloud.validate_folder)
    elif values.get("FILES") is None:
        answers["FILES"] = str(nextcloud.files())
    config.save(APP, answers)
    return password


def install(reuse: bool | None = None) -> None:
    again = config.reuse(APP) if reuse is None else reuse
    ui.step("Nextcloud: a nuvem própria")
    ui.note(
        "O Nextcloud guarda arquivos, fotos, agenda e contatos nesta máquina, com apps para o celular e o computador, "
        "como um Google Drive seu. Ele roda em containers e abre pelo endereço com cadeado do Caddy."
    )
    first = not nextcloud.created()
    password = _ask(again)
    container.prepare()
    nextcloud.prepare_secrets()
    nextcloud.prepare_files(nextcloud.files())
    nextcloud.render_site(nextcloud.host())
    nextcloud.start()
    nextcloud.wait_ready()
    if password:
        nextcloud.change_password(nextcloud.admin(), password)
    nextcloud.tune(nextcloud.host(), first)
    nextcloud.publish(nextcloud.host())
    changes.install(APP, items(), again)
    ui.info(f"https://{nextcloud.host()} (usuário {nextcloud.admin()})")
    ui.link("conectar o celular, o computador, a agenda e os contatos", docs.link(DOCS / "apps.md"))
    summary()


def remove() -> None:
    ui.step("Nextcloud")
    path = nextcloud.files()
    changes.undo_all(items())
    nextcloud.remove_containers()
    routes.withdraw(APP)
    if path.exists() and ui.confirm(f"Apagar também a pasta dos arquivos ({path}), com os arquivos de todos os usuários?", default=False):
        nextcloud.remove_files(path)
    elif path.exists():
        ui.info(f"a pasta dos arquivos ficou: {path}")
    config.purge(APP)


def backup(folder: Path) -> None:
    copies.save(folder)


def restore(folder: Path) -> None:
    copies.load(folder)
    install(reuse=True)
    nextcloud.occ("maintenance:data-fingerprint")


def summary() -> None:
    ui.step("Resumo do Nextcloud")
    state = nextcloud.status() if nextcloud.installed() else {}
    ui.section("Nextcloud")
    rows: list[list[str | ui.Cell]] = [
        ["Situação", (ui.pending("em manutenção") if state.get("maintenance") else ui.good("no ar")) if state else ui.bad("parado")],
        ["Versão", state.get("versionstring") or "-"],
        ["Endereço", f"https://{nextcloud.host()}"],
        ["Administrador", nextcloud.admin()],
        ["Pasta dos arquivos", str(nextcloud.files())],
        ["Espaço", nextcloud.free_space(nextcloud.files())],
    ]
    if state:
        cron = nextcloud.last_cron()
        rows.append(["Tarefas em segundo plano", ui.good(f"última às {cron}") if cron else ui.pending("ainda não rodaram")])
        errors = nextcloud.checks()
        rows.append(["Verificação do Nextcloud", ui.good("sem erros") if not errors else ui.bad(f"{len(errors)} erro(s)")])
    ui.table(rows)
    ui.section("Containers")
    ui.table([[spec.name, ui.good("no ar") if container.active(spec.name) else ui.bad("parado")] for spec in nextcloud.specs()],
             ["Container", "Situação"])
    watch.summary(APP)


def collect(previous: watch.State) -> dict[str, watch.Problem]:
    found: dict[str, watch.Problem] = {}
    stopped = [spec.name for spec in nextcloud.specs() if not container.active(spec.name)]
    if stopped:
        found["containers"] = watch.Problem("erro", "Nextcloud parado", f"Containers parados: {', '.join(stopped)}.")
        return found
    state = nextcloud.status()
    if state.get("maintenance"):
        found["maintenance"] = watch.Problem("aviso", "Nextcloud em manutenção", "Ninguém consegue usar o Nextcloud até sair da manutenção.")
    for check, text in nextcloud.checks().items():
        found[f"check:{check}"] = watch.Problem("aviso", f"Verificação do Nextcloud: {check}", text, "check")
    try:
        usage = shutil.disk_usage(nextcloud.files())
    except OSError:
        usage = None
    if usage and usage.free < usage.total * 0.1:
        found["space"] = watch.Problem("aviso", "Pasta dos arquivos quase cheia", nextcloud.free_space(nextcloud.files()))
    return found


def check() -> None:
    watch.run(APP, collect, BUTTONS, "Nextcloud em ordem")


def repair() -> None:
    ui.info("conferindo o banco, reparando e reverificando os arquivos (pode demorar)...")
    nextcloud.occ("db:add-missing-indices")
    nextcloud.occ("maintenance:repair", "--include-expensive")
    nextcloud.occ("files:scan", "--all")
    ui.ok("Nextcloud reparado e arquivos reverificados")


def password() -> None:
    new = ui.secret(f"nova senha do administrador {nextcloud.admin()}")
    nextcloud.change_password(nextcloud.admin(), new)


def manage() -> None:
    changes.manage(APP, items())


def actions() -> list[Action]:
    return [
        Action("summary", "Resumo do Nextcloud", summary, remote=True),
        Action("changes", "Mudanças no sistema", manage),
        Action("password", "Trocar a senha do administrador", password),
        Action("repair", "Reparar o Nextcloud", repair, remote=True, confirm=True),
        Action("watch", "Verificar agora (e avisar no Discord)", check, remote=True),
    ]
