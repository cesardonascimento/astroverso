from __future__ import annotations

import json
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

from kit import backup as kit_backup
from kit import changes, config, container, distro, docs, net, routes, ui, validate, watch
from kit.app import Action

from . import server

APP = "backup"
DESCRIPTION = "Backup das configurações dos apps de todas as máquinas, criptografado, num servidor da casa (restic)"
DOCS = Path(__file__).with_name("docs")
MODES = ("server", "client")
BUTTONS = (("Resumo dos backups", "backup:summary"),)


def mode() -> str:
    return config.load(APP).get("MODE", "") if config.env_file(APP).exists() else ""


def status() -> bool:
    return server.installed() if mode() == "server" else mode() == "client" and kit_backup.configured()


def items() -> list[changes.Change]:
    found = [kit_backup.change(APP)]
    if mode() == "server":
        found = [server.change(), watch.change(
            APP, "Verificar os backups de hora em hora e avisar no Discord",
            f"Um timer do usuário ({watch.name(APP)}.timer) confere a cada hora se o servidor está no ar, se cada "
            "máquina e cada app mandaram backup nas últimas 36 horas e o resultado da manutenção semanal.",
            "os backups",
        )] + found
    return found


def _show(name: str, values: dict[str, str]) -> None:
    ui.warn("guarde a senha do repositório no seu gerenciador de senhas: sem ela, nem você abre os backups desta máquina")
    ui.link("por que isso importa", docs.link(DOCS / "senhas.md"))
    ui.info(f"endereço: https://{server.address()}")
    ui.info(f"usuário: {name}")
    ui.info(f"senha de acesso: {values['PASSWORD']}")
    ui.info(f"senha do repositório: {values['REPO_PASSWORD']}")


def _server(reuse: bool) -> None:
    server.ask(reuse)
    distro.install(["restic"])
    local = net.hostname()
    if local not in server.clients():
        server.add(local)
        ui.ok(f"máquina {local} cadastrada no servidor")
    server.start()
    values = server.clients()[local]
    kit_backup.save(f"https://{server.address()}", local, values["PASSWORD"], values["REPO_PASSWORD"])
    if not reuse:
        ui.note("Esta é a senha do repositório desta máquina. Ela criptografa os backups e não fica em nenhum outro lugar seguro.")
        _show(local, values)
    problem = kit_backup.ensure_repository(kit_backup.settings())
    if problem:
        ui.warn(f"o repositório desta máquina ainda não respondeu ({problem}): ele depende do Caddy e do DNS do app network")


def _client(reuse: bool) -> None:
    distro.install(["restic"])
    current = kit_backup.settings()
    if reuse and kit_backup.configured() and not kit_backup.ensure_repository(current):
        ui.ok("esta máquina continua ligada ao servidor de backup")
        return
    ui.note(
        "Na máquina com o servidor de backup, use a ação Adicionar uma máquina do app backup: ela mostra o endereço, o "
        "usuário e as duas senhas para colar aqui."
    )
    domain = config.saved_domain()
    while True:
        url = ui.ask("endereço do servidor de backup", default=current.get("BACKUP_URL") or f"https://backup.{domain}", validate=_url)
        user = ui.ask("usuário desta máquina", default=current.get("BACKUP_USER") or net.hostname(), validate=validate.name)
        password = ui.secret("senha de acesso", confirm=False)
        repository = ui.secret("senha do repositório", confirm=False)
        attempt = dict(zip(kit_backup.KEYS, (url, user, password, repository)))
        problem = kit_backup.ensure_repository(attempt)
        if not problem:
            break
        ui.warn(f"o servidor não aceitou: {problem}")
    kit_backup.save(url, user, password, repository)
    ui.ok(f"esta máquina manda os backups para {url}")


def _url(value: str) -> str:
    value = value.strip().rstrip("/")
    if not value.startswith("https://") or " " in value:
        raise ValueError("endereço com https://, como https://backup.casa.com")
    return value


def install(reuse: bool | None = None) -> None:
    again = config.reuse(APP) if reuse is None else reuse
    ui.step("Backup das configurações")
    ui.note(
        "Cada app guarda todo dia a própria configuração (respostas, senhas, bancos), criptografada, num servidor de "
        "backup da casa, e pode ser restaurado de qualquer versão guardada. Uma máquina tem o servidor; as outras só "
        "mandam os backups dos apps delas."
    )
    chosen = mode() if again and mode() in MODES else ""
    if not chosen:
        chosen = MODES[ui.menu("Esta máquina", ["Tem o servidor de backup (guarda os backups de todas as máquinas)",
                                                "Só manda os backups dos apps dela para o servidor de outra máquina"])]
    config.save(APP, {"MODE": chosen})
    if chosen == "server":
        _server(again)
    else:
        _client(again)
    changes.install(APP, items(), again)
    ui.info("os apps desta máquina ganham a pergunta do backup diário na próxima instalação deles (ou em Mudanças no sistema)")
    summary()


def remove() -> None:
    ui.step("Backup")
    changes.undo_all(items())
    if mode() == "server":
        container.remove(server.NAME, server.IMAGE)
        routes.withdraw(APP)
        ui.info(f"os backups ficaram em {server.repos()} (apague à mão, se quiser)")
    kit_backup.forget()
    config.purge(APP)


def backup(folder: Path) -> None:
    shutil.copy2(config.env_file(APP), folder / ".env")


def restore(folder: Path) -> None:
    if not (folder / ".env").exists():
        ui.fail(f"backup sem a configuração do {APP}")
    config.state(APP)
    current = config.read_env(folder / ".env")
    config.save(APP, {key: value for key, value in current.items() if key in ("MODE", "REPOS", "KEEP_DAILY", "KEEP_MONTHLY")})
    ui.info("as senhas das máquinas não entram no backup: cadastre de novo (ação Adicionar uma máquina) ou use as do gerenciador de senhas")


def add_machine() -> None:
    ui.note("Cada máquina que manda backups tem um usuário e duas senhas próprios. Use o nome da máquina.")
    name = ui.ask("nome da máquina", validate=server.validate_new)
    values = server.add(name)
    server.restart()
    ui.ok(f"máquina {name} cadastrada")
    _show(name, values)
    ui.note("Na outra máquina, instale o app backup, escolha mandar os backups para o servidor de outra máquina e cole os dados acima.")


def remove_machine() -> None:
    names = [name for name in server.clients() if name != net.hostname()]
    if not names:
        ui.info("só esta máquina está cadastrada")
        return
    chosen = ui.checklist("Quais máquinas descadastrar?", names, cancel=True) or []
    for index in chosen:
        name = names[index]
        (server.clients_folder() / f"{name}.env").unlink()
        ui.ok(f"{name} não manda mais backups (o repositório dela ficou em {server.repos() / name})")
    if chosen:
        server._write_htpasswd()
        server.restart()


def show_machine() -> None:
    names = list(server.clients())
    index = ui.menu("Qual máquina?", names + ["Voltar"])
    if index < len(names):
        _show(names[index], server.clients()[names[index]])


def summary() -> None:
    ui.step("Resumo dos backups")
    if mode() == "server":
        ui.section("Servidor")
        ui.table([
            ["Servidor", ui.good("no ar") if server.installed() else ui.bad("parado")],
            ["Endereço", f"https://{server.address()}"],
            ["Pasta", str(server.repos())],
            ["Espaço", server.free_space()],
            ["Regra", f"{config.load(APP).get('KEEP_DAILY', '30')} diárias e {config.load(APP).get('KEEP_MONTHLY', '12')} mensais"],
        ])
        rows: list[list[str | ui.Cell]] = []
        for name, values in server.clients().items():
            last = server.latest(server.snapshots(name, values))
            if not last:
                rows.append([name, ui.off("nenhum backup ainda"), "-"])
            for app_name, moment in sorted(last.items()):
                fresh = datetime.now(timezone.utc) - moment < timedelta(hours=36)
                rows.append([name, app_name, ui.good(server.ago(moment)) if fresh else ui.bad(server.ago(moment))])
        ui.section("Máquinas e apps")
        ui.table(rows or [[ui.off("nenhuma"), "-", "-"]], ["Máquina", "App", "Último backup"])
        watch.summary(APP)
    ui.section("Esta máquina")
    ui.table([["Servidor de backup", kit_backup.settings().get("BACKUP_URL") or ui.pending("não configurado")]])


def collect(previous: watch.State) -> dict[str, watch.Problem]:
    found: dict[str, watch.Problem] = {}
    if not server.installed():
        found["server"] = watch.Problem("erro", "Servidor de backup parado", "Nenhuma máquina consegue guardar backups até ele voltar.")
        return found
    now = datetime.now(timezone.utc)
    for name, values in server.clients().items():
        last = server.latest(server.snapshots(name, values))
        if not last:
            continue
        newest = max(last.values())
        if now - newest > timedelta(hours=36):
            found[f"machine:{name}"] = watch.Problem("erro", f"{name} sem backup há {int((now - newest).total_seconds() // 3600)} h",
                                                     "A máquina pode estar desligada ou sem acesso ao servidor.", f"machine:{name}")
            continue
        for app_name, moment in last.items():
            age = now - moment
            if timedelta(hours=36) < age < timedelta(days=14):
                found[f"app:{name}:{app_name}"] = watch.Problem("aviso", f"{app_name} de {name} sem backup há {int(age.total_seconds() // 3600)} h",
                                                                "O backup do app está falhando (veja o #backup).", f"app:{name}:{app_name}")
    try:
        report = json.loads(server.maintenance_file().read_text())
    except (OSError, ValueError):
        report = {}
    if report.get("problems"):
        found["maintenance"] = watch.Problem("erro", "Manutenção dos backups com problema",
                                             "; ".join(f"{name}: {text}" for name, text in report["problems"].items()), "maintenance")
    return found


def check() -> None:
    watch.run(APP, collect, BUTTONS, "backups em ordem")


def backup_now() -> None:
    kit_backup.run_backup(APP, backup)


def restore_version() -> None:
    kit_backup.restore(APP, backup, restore)


def manage() -> None:
    changes.manage(APP, items())


def actions() -> list[Action]:
    common = [
        Action("summary", "Resumo dos backups", summary, remote=True),
        Action("changes", "Mudanças no sistema", manage),
        Action("backup-now", "Fazer backup agora", backup_now, remote=True),
        Action("restore-version", "Restaurar uma versão", restore_version),
    ]
    if mode() != "server":
        return common
    return common + [
        Action("add-machine", "Adicionar uma máquina", add_machine),
        Action("show-machine", "Mostrar os dados de uma máquina", show_machine),
        Action("remove-machine", "Descadastrar máquinas", remove_machine),
        Action("maintenance", "Manutenção dos repositórios agora", server.maintain, remote=True, confirm=True),
        Action("watch", "Verificar agora (e avisar no Discord)", check, remote=True),
    ]
