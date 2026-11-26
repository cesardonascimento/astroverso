from __future__ import annotations

import json
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

from kit import backup as kit_backup
from kit import changes, config, container, distro, docs, net, routes, ui, watch
from kit.app import Action

from . import server

APP = "backup"
DESCRIPTION = "Servidor de backup da casa (restic): guarda, criptografados, os backups que os apps de todas as máquinas mandam"
ORDER = 40
DOCS = Path(__file__).with_name("docs")
MODES = ("server", "client")
BUTTONS = (("Resumo dos backups", "backup:summary"),)


def mode() -> str:
    return config.load(APP).get("MODE", "") if config.env_file(APP).exists() else ""


def status() -> bool:
    return server.installed() if mode() == "server" else mode() == "client" and kit_backup.configured()


def _verify(values: dict[str, str]) -> str:
    for item in kit_backup.destinations():
        problem = kit_backup.ensure_repository(values, item)
        if problem:
            return f"{item.path}: {problem}"
    return ""


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
    ui.info(f"código de ligação: {server.link_code(name)}")
    for item in server.destinations():
        ui.info(f"repositório em {item.path}: rest:https://{server.address()}/{name}/{item.id}/")


def _server(reuse: bool) -> None:
    server.ask(reuse)
    distro.install(["restic"])
    local = net.hostname()
    if local not in server.clients():
        old = ""
        if server.existing(local):
            ui.note(f"As pastas de destino já têm backups de {local}. Para continuar com eles, use a senha do repositório antiga (do gerenciador de senhas).")
            old = _old_password(local)
        server.add(local, old)
        ui.ok(f"máquina {local} cadastrada no servidor")
    server.start()
    values = server.clients()[local]
    kit_backup.save(f"https://{server.address()}", local, values["PASSWORD"], values["REPO_PASSWORD"])
    server.sync_local()
    if not reuse:
        ui.note("Esta é a senha do repositório desta máquina. Ela criptografa os backups e não fica em nenhum outro lugar seguro.")
        _show(local, values)
    problem = _verify(kit_backup.settings())
    if problem:
        ui.warn(f"o repositório desta máquina ainda não respondeu ({problem}): ele depende do Caddy e do DNS do app network")


def _link() -> None:
    ui.note(
        "Na máquina com o servidor de backup, use a ação Adicionar uma máquina (ou Mostrar os dados de uma máquina) do "
        "app backup: ela mostra o código de ligação (endereço, usuário e pastas de destino) e as duas senhas."
    )
    while True:
        url, user, items = kit_backup.read_code(ui.ask("código de ligação", validate=_code))
        password = ui.secret("senha de acesso", confirm=False)
        repository = ui.secret("senha do repositório", confirm=False)
        attempt = dict(zip(kit_backup.KEYS, (url, user, password, repository)))
        kit_backup.save_destinations(items)
        problem = _verify(attempt)
        if not problem:
            break
        ui.warn(f"o servidor não aceitou: {problem}")
    kit_backup.save(url, user, password, repository)
    ui.ok(f"esta máquina manda os backups para {url} ({len(items)} pasta(s) de destino)")


def _code(value: str) -> str:
    kit_backup.read_code(value)
    return "".join(value.split())


def _client(reuse: bool) -> None:
    distro.install(["restic"])
    current = kit_backup.settings()
    if reuse and kit_backup.configured() and not _verify(current):
        ui.ok("esta máquina continua ligada ao servidor de backup")
        return
    _link()


def update_destinations() -> None:
    values = kit_backup.settings()
    if not kit_backup.configured():
        ui.fail("esta máquina ainda não está ligada a um servidor de backup: instale o app backup")
    ui.note("Cole o código de ligação desta máquina, de Mostrar os dados de uma máquina no servidor. As senhas continuam as mesmas.")
    url, user, items = kit_backup.read_code(ui.ask("código de ligação", validate=_code))
    if (url, user) != (values["BACKUP_URL"], values["BACKUP_USER"]):
        ui.fail(f"esse código é de {user} em {url}; esta máquina é {values['BACKUP_USER']} em {values['BACKUP_URL']}")
    kit_backup.save_destinations(items)
    ui.ok("pastas de destino atualizadas: " + ", ".join(item.path for item in items))
    ui.info("os apps que mandavam para uma pasta que saiu avisam no #backup: desligue e ligue o backup deles para escolher de novo")


def install(reuse: bool | None = None) -> None:
    again = config.reuse(APP) if reuse is None else reuse
    ui.step("Backup")
    ui.note(
        "Cada app guarda todo dia a própria configuração (respostas, senhas, bancos) e, se tiver, os próprios dados, "
        "criptografados, num servidor de backup da casa, e pode ser restaurado de qualquer versão guardada. Uma máquina "
        "tem o servidor, com as pastas de destino; cada app escolhe para quais pastas manda o backup dele."
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
        for item in server.destinations():
            ui.info(f"os backups ficaram em {item.path} (apague à mão, se quiser)")
    kit_backup.forget()
    config.purge(APP)


def backup(folder: Path) -> None:
    shutil.copy2(config.env_file(APP), folder / ".env")
    if server.destinations_file().exists():
        shutil.copy2(server.destinations_file(), folder / "destinations.json")


def restore(folder: Path) -> None:
    if not (folder / ".env").exists():
        ui.fail(f"backup sem a configuração do {APP}")
    config.state(APP)
    current = config.read_env(folder / ".env")
    config.save(APP, {key: value for key, value in current.items() if key in ("MODE", "KEEP_DAILY", "KEEP_MONTHLY")})
    if (folder / "destinations.json").exists():
        shutil.copy2(folder / "destinations.json", server.destinations_file())
        server.destinations_file().chmod(0o600)
    ui.info("as senhas das máquinas não entram no backup: cadastre de novo (ação Adicionar uma máquina) ou use as do gerenciador de senhas")


def _old_password(name: str) -> str:
    for _ in range(3):
        password = ui.secret(f"senha do repositório antiga de {name}", confirm=False)
        problem = server.check_password(name, password)
        if not problem:
            ui.ok("a senha abre os backups que já existem")
            return password
        ui.warn(problem)
    ui.fail("a senha não abriu os backups: confira no gerenciador de senhas e tente de novo")


def add_machine() -> None:
    ui.note("Cada máquina que manda backups tem um usuário e duas senhas próprios. Use o nome da máquina.")
    name = ui.ask("nome da máquina", validate=server.validate_new)
    old = ""
    ui.note(
        "Uma máquina que está voltando (formatada, ou descadastrada antes) continua com os backups antigos se usar a "
        "senha do repositório antiga. A senha de acesso é sempre nova: ela não criptografa nada."
    )
    if ui.menu("Essa máquina", ["É nova (gera as duas senhas)", "Está voltando (usa a senha do repositório antiga)"]) == 1:
        if not server.existing(name):
            ui.warn(f"não há backups de {name} nas pastas de destino: confira o nome (a senha antiga só é conferida se houver)")
        old = _old_password(name)
    values = server.add(name, old)
    server.restart()
    ui.ok(f"máquina {name} cadastrada")
    _show(name, values)
    ui.note("Na outra máquina, instale o app backup, escolha mandar os backups para o servidor de outra máquina e cole os dados acima.")
    ui.link("PC com Windows (sem Astroverso): o restic e uma tarefa agendada, com os repositórios acima", docs.link(DOCS / "windows.md"))


def remove_machine() -> None:
    names = [name for name in server.clients() if name != net.hostname()]
    if not names:
        ui.info("só esta máquina está cadastrada")
        return
    chosen = ui.checklist("Quais máquinas descadastrar?", names, cancel=True) or []
    for index in chosen:
        name = names[index]
        (server.clients_folder() / f"{name}.env").unlink()
        ui.ok(f"{name} não manda mais backups (os repositórios dela ficaram nas pastas de destino)")
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
            ["Regra", f"{config.load(APP).get('KEEP_DAILY', '30')} diárias e {config.load(APP).get('KEEP_MONTHLY', '12')} mensais"],
        ])
        ui.section("Pastas de destino")
        ui.table([[item.path, server.free_space(item) if server.reachable(item) else ui.bad("indisponível"), item.detail()]
                  for item in server.destinations()] or [[ui.off("nenhuma"), "-", "-"]], ["Pasta", "Espaço", "Nuvem"])
        rows: list[list[str | ui.Cell]] = []
        for name, values in server.clients().items():
            for item in server.destinations():
                last = server.latest(server.snapshots(server.repository(item, name), values))
                for app_name, moment in sorted(last.items()):
                    fresh = datetime.now(timezone.utc) - moment < timedelta(hours=36)
                    rows.append([name, item.path, app_name, ui.good(server.ago(moment)) if fresh else ui.bad(server.ago(moment))])
        ui.section("Máquinas e apps")
        ui.table(rows or [[ui.off("nenhum backup ainda"), "-", "-", "-"]], ["Máquina", "Pasta", "App", "Último backup"])
        watch.summary(APP)
    ui.section("Esta máquina")
    ui.table([["Servidor de backup", kit_backup.settings().get("BACKUP_URL") or ui.pending("não configurado")]]
             + [["Pasta de destino", item.path] for item in kit_backup.destinations()])


def collect(previous: watch.State) -> dict[str, watch.Problem]:
    found: dict[str, watch.Problem] = {}
    if not server.installed():
        found["server"] = watch.Problem("erro", "Servidor de backup parado", "Nenhuma máquina consegue guardar backups até ele voltar.")
        return found
    now = datetime.now(timezone.utc)
    places = [item for item in server.destinations() if server.reachable(item)]
    for item in server.destinations():
        if item not in places:
            found[f"destination:{item.id}"] = watch.Problem(
                "erro", f"Pasta de destino indisponível: {item.path}",
                "O disco está desligado ou travado (veja o app disks): os backups para ela falham até ele voltar.", "destination")
    for name, values in server.clients().items():
        latest = {item: server.latest(server.snapshots(server.repository(item, name), values)) for item in places}
        moments = [moment for last in latest.values() for moment in last.values()]
        if not moments:
            continue
        newest = max(moments)
        if now - newest > timedelta(hours=36):
            found[f"machine:{name}"] = watch.Problem("erro", f"{name} sem backup há {int((now - newest).total_seconds() // 3600)} h",
                                                     "A máquina pode estar desligada ou sem acesso ao servidor.", f"machine:{name}")
            continue
        for item, last in latest.items():
            for app_name, moment in last.items():
                age = now - moment
                if timedelta(hours=36) < age < timedelta(days=14):
                    found[f"app:{name}:{item.id}:{app_name}"] = watch.Problem(
                        "aviso", f"{app_name} de {name} sem backup em {item.path} há {int(age.total_seconds() // 3600)} h",
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
    if mode() == "server":
        try:
            server.heal()
        except SystemExit:
            ui.warn("o servidor de backup não voltou ao ajustar as pastas de destino")
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
        return common + [Action("update-destinations", "Atualizar as pastas de destino", update_destinations)]
    return common + [
        Action("destinations", "Pastas de destino", server.manage_destinations),
        Action("add-machine", "Adicionar uma máquina", add_machine),
        Action("show-machine", "Mostrar os dados de uma máquina", show_machine),
        Action("remove-machine", "Descadastrar máquinas", remove_machine),
        Action("maintenance", "Manutenção dos repositórios agora", server.maintain, remote=True, confirm=True),
        Action("watch", "Verificar agora (e avisar no Discord)", check, remote=True),
    ]
