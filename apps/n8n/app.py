from __future__ import annotations

import json
import shutil
from pathlib import Path

from kit import backup as kit_backup
from kit import changes, config, container, routes, ui, validate, watch
from kit.app import Action
from kit.watch import Problem

from . import commands, connections, modules, n8n

APP = "n8n"
DESCRIPTION = "Rotinas automáticas montadas pelo navegador (n8n) em https://n8n.<domínio>, com módulos do Astroverso"
BUTTONS = (("Resumo do n8n", "n8n:summary"), ("Verificar de novo", "n8n:watch"))
FILES = (".env", "n8n.env", "owner_password_hash", "commands.json")


def items() -> list[changes.Change]:
    return [
        watch.change(
            APP, "Verificar o n8n de hora em hora e avisar no Discord",
            f"Um timer do usuário ({watch.name(APP)}.timer) confere a cada hora se o n8n, o executor de código e os "
            "módulos estão no ar e respondendo, e avisa no Discord quando algo quebra e quando volta.",
            "o n8n",
        ),
        kit_backup.change(APP),
    ]


def status() -> bool:
    return n8n.installed()


def _password(value: str) -> str:
    if len(value) < 8:
        raise ValueError("use pelo menos 8 caracteres")
    return value


def _ask(reuse: bool) -> None:
    values = config.load(APP)
    if reuse and values.get("HOST") and values.get("OWNER_EMAIL") and n8n.hash_file().exists():
        return
    domain = config.domain()
    ui.note(f"O endereço do n8n, só na rede de casa e no Tailscale. O padrão é n8n.{domain}.")
    answers = {"HOST": ui.ask("endereço do n8n", default=values.get("HOST") or f"n8n.{domain}", validate=validate.domain)}
    ui.note("A conta de administrador do n8n. O e-mail é só o login: não precisa existir, o n8n não manda e-mails.")
    answers["OWNER_EMAIL"] = ui.ask("e-mail do administrador", default=values.get("OWNER_EMAIL") or f"n8n@{domain}", validate=validate.email)
    answers["OWNER_FIRST_NAME"] = ui.ask("nome", default=values.get("OWNER_FIRST_NAME") or "Astroverso")
    answers["OWNER_LAST_NAME"] = ui.ask("sobrenome", default=values.get("OWNER_LAST_NAME") or "n8n")
    config.save(APP, answers)
    if not n8n.hash_file().exists() or ui.confirm("Trocar a senha do administrador?", default=False):
        n8n.save_password(_secret())


def _secret() -> str:
    while True:
        try:
            return _password(ui.secret("senha do administrador do n8n (mínimo 8 caracteres)"))
        except ValueError as problem:
            ui.warn(str(problem))


def install(reuse: bool | None = None) -> None:
    again = config.reuse(APP) if reuse is None else reuse
    ui.step("n8n: as rotinas automáticas")
    ui.note(
        "O n8n monta rotinas automáticas pelo navegador (ler e-mails, gravar arquivos, avisar no Discord...), com blocos "
        "prontos para centenas de serviços. As rotinas ficam no banco dele: você cria, edita e liga por lá. Os módulos do "
        "Astroverso (apps/n8n/modules) sobem junto, como APIs que as rotinas chamam."
    )
    _ask(again)
    n8n.prepare_secrets()
    n8n.start()
    connections.sync()
    routes.publish(APP, [routes.Route(n8n.host(), f"http://{n8n.NAME}:{n8n.PORT}")])
    changes.install(APP, items(), again)
    ui.info(f"https://{n8n.host()} (login {config.load(APP).get('OWNER_EMAIL')} e a senha do administrador)")
    summary()


def remove() -> None:
    ui.step("n8n")
    changes.undo_all(items())
    routes.withdraw(APP)
    for spec in reversed(n8n.specs()):
        container.remove(spec.name, spec.image)
    if ui.confirm(f"Apagar também as rotinas, as credenciais e o histórico ({n8n.folder()})? Só voltam por um backup", default=False):
        config.purge(APP)
    else:
        ui.info(f"as rotinas ficaram em {n8n.folder()}: uma instalação nova as encontra")


def backup(folder: Path) -> None:
    n8n.export(folder)
    for name in FILES:
        source = n8n.folder() / name
        if source.exists():
            shutil.copy2(source, folder / name)


def restore(folder: Path) -> None:
    for name in (".env", "n8n.env", "entities"):
        if not (folder / name).exists():
            ui.fail(f"backup incompleto do n8n: falta {name}")
    n8n.stop()
    config.state(APP)
    for name in FILES:
        if (folder / name).exists():
            shutil.copy2(folder / name, n8n.folder() / name)
            (n8n.folder() / name).chmod(0o644 if name == "owner_password_hash" else 0o600)
    n8n.load_entities(folder / "entities")
    install(reuse=True)


def restore_workflow() -> None:
    if not n8n.installed():
        ui.fail("o n8n precisa estar no ar")
    with kit_backup.opened(APP) as opened:
        if opened is None:
            return
        folder, moment = opened
        found = n8n.workflows(folder / "workflows")
        if not found:
            ui.fail(f"o backup de {moment} não tem rotinas em arquivos separados")
        index = ui.menu(f"Qual rotina trazer do backup de {moment}?", [str(item["name"]) for item in found] + ["Voltar"])
        if index >= len(found):
            return
        chosen = dict(found[index])
        way = ui.menu("Como trazer?", [f"Como cópia, ao lado da atual ({chosen['name']} (restaurada de {moment[:5]}))",
                                       "Substituindo a atual (mesma rotina, volta a ficar como estava)", "Voltar"])
        if way == 2:
            return
        active = bool(chosen.get("active"))
        if way == 0:
            chosen.pop("id", None)
            chosen["name"] = f"{chosen['name']} (restaurada de {moment[:5]})"
            chosen["active"] = False
        else:
            ui.warn(f"a rotina {chosen['name']} atual é trocada pela de {moment} (o histórico do n8n guarda a atual)")
            if not ui.confirm("Substituir?", default=False):
                return
        code, output = n8n.import_file("workflow", json.dumps(chosen))
        if code:
            ui.fail(f"o n8n não importou a rotina: {output.strip()[-300:]}")
    if way == 0:
        ui.ok(f"rotina {chosen['name']} criada, desligada: compare e ligue pelo n8n")
        return
    if active:
        code, output = n8n.cli("publish:workflow", f"--id={chosen['id']}")
        if code:
            ui.warn(f"a rotina voltou, mas desligada: ligue pelo n8n ({output.strip()[-200:]})")
    ui.ok(f"rotina {chosen['name']} de volta como estava em {moment}" + (" e ligada" if active else ""))


def _folder(value: str) -> str:
    path = Path(value.strip()).expanduser()
    if not path.is_dir():
        raise ValueError("essa pasta não existe")
    if not n8n.workflows(path):
        raise ValueError("essa pasta não tem rotinas do n8n (arquivos .json)")
    return str(path)


def import_workflows() -> None:
    if not n8n.installed():
        ui.fail("o n8n precisa estar no ar")
    ui.note(
        "Traz rotinas de arquivos JSON (exportadas de outro n8n ou do backup). Elas entram desligadas; uma rotina com o "
        "mesmo id é substituída. As credenciais são ligadas pelo id ou, se não houver, pelo nome e tipo: crie antes, no "
        "n8n, as que faltarem, com o mesmo nome."
    )
    folder = Path(ui.ask("pasta com as rotinas", default=str(Path.home()), validate=_folder))
    found = n8n.workflows(folder)
    chosen = ui.checklist("Quais rotinas importar?", [str(item["name"]) for item in found], selected=list(range(len(found))), cancel=True)
    if not chosen:
        return
    existing = n8n.credential_names()
    missing = sorted({pair for i in chosen for pair in n8n.needed(found[i])} - existing)
    if missing:
        ui.warn("credenciais que ainda não existem no n8n: " + ", ".join(f"{name} ({kind})" for kind, name in missing))
        ui.warn("sem elas, os nós que as usam ficam sem credencial (dá para escolher depois, no n8n)")
        if not ui.confirm("Importar assim mesmo?", default=False):
            return
    for i in chosen:
        code, output = n8n.import_file("workflow", json.dumps(found[i]))
        if code:
            ui.warn(f"{found[i]['name']}: o n8n não importou ({output.strip()[-200:]})")
        else:
            ui.ok(f"{found[i]['name']} importada, desligada")
    ui.info(f"confira cada rotina em https://{n8n.host()} e ligue as que estiverem certas")


def summary() -> None:
    ui.step("Resumo do n8n")
    values = config.load(APP)
    ui.section("n8n")
    ui.table([
        ["Situação", ui.good("no ar") if n8n.installed() else ui.bad("parado")],
        ["Versão", n8n.VERSION],
        ["Endereço", f"https://{n8n.host()}"],
        ["Administrador", values.get("OWNER_EMAIL", "-")],
    ])
    ui.section("Containers")
    rows: list[list[str | ui.Cell]] = [[spec.name, ui.good("no ar") if container.active(spec.name) else ui.bad("parado"), "-"]
                                       for spec in (n8n.main_spec(), n8n.runners_spec())]
    rows += [[module.container, _health_cell(modules.health(module)), module.url] for module in modules.found()]
    ui.table(rows, ["Container", "Situação", "Endereço para as rotinas"])
    found, missing = connections.build()
    ui.section("Conexões do Astroverso (credenciais no n8n)")
    ui.table([[item.name.removeprefix("Astroverso: "), item.id, item.detail] for item in found]
             + [[name, ui.pending("não disponível"), "-"] for name in missing], ["Conexão", "Credencial (id)", "Uso"])
    watch.summary(APP)


def _health_cell(state: str) -> ui.Cell:
    return ui.good("no ar") if state == "healthy" else ui.pending("subindo") if state == "starting" else ui.bad(state or "parado")


def collect(previous: watch.State) -> dict[str, Problem]:
    found: dict[str, Problem] = {}
    stopped = [spec.name for spec in (n8n.main_spec(), n8n.runners_spec()) if not container.active(spec.name)]
    if stopped:
        found["containers"] = Problem("erro", "n8n parado", f"Containers parados: {', '.join(stopped)}. As rotinas não rodam.")
        return found
    code, _ = container.exec_output(n8n.NAME, ["wget", "-q", "-O", "/dev/null", f"http://127.0.0.1:{n8n.PORT}/healthz"], user=n8n.USER, timeout=30)
    if code:
        found["health"] = Problem("erro", "n8n não responde", "O container está de pé, mas o n8n não responde: as rotinas podem não estar rodando.")
    for module in modules.found():
        state = modules.health(module)
        if state not in ("healthy", "starting"):
            found[f"module:{module.name}"] = Problem("erro", f"Módulo {module.name} do n8n fora do ar",
                                                     f"Situação: {state}. As rotinas que usam {module.url} falham até ele voltar.", "module")
    return found


def check() -> None:
    watch.run(APP, collect, BUTTONS, "n8n e módulos no ar")


def password() -> None:
    n8n.save_password(_secret())
    container.restart(n8n.main_spec())


def manage() -> None:
    changes.manage(APP, items())


def _remote(item: dict[str, str]) -> None:
    if not commands.call(item):
        raise SystemExit(1)


def manage_commands() -> None:
    commands.manage({action.id for action in base_actions()})


def actions() -> list[Action]:
    return base_actions() + [Action(item["name"], item.get("description") or f"Rotina {item['path']}", lambda item=item: _remote(item),
                                    remote=True, menu=False) for item in commands.commands()]


def base_actions() -> list[Action]:
    return [
        Action("summary", "Resumo do n8n", summary, remote=True),
        Action("connections", "Atualizar as conexões do Astroverso", connections.sync, remote=True),
        Action("password", "Trocar a senha do administrador", password),
        Action("restore-workflow", "Restaurar uma rotina", restore_workflow),
        Action("import-workflows", "Importar rotinas (arquivos JSON)", import_workflows),
        Action("commands", "Comandos do Discord", manage_commands),
        Action("changes", "Mudanças no sistema", manage),
        Action("watch", "Verificar agora", check, remote=True),
        Action("backup-now", "Fazer backup agora", lambda: kit_backup.run_backup(APP, backup), remote=True),
        Action("restore-version", "Restaurar uma versão", lambda: kit_backup.restore(APP, backup, restore)),
    ]
