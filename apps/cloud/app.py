from __future__ import annotations

import shutil
import time
from pathlib import Path

from kit import backup as kit_backup
from kit import changes, clouds, config, distro, folders, ui, units, watch
from kit.app import Action
from kit.watch import Problem

from . import jobs, rclone
from .jobs import Job

APP = "cloud"
DESCRIPTION = "Pastas da máquina sincronizadas com a nuvem (Proton Drive) pelo rclone: duas vias e envios"
COMMAND = Path(__file__).resolve().parents[2] / "astroverso"
BUTTONS = (("Resumo da nuvem", "cloud:summary"), ("Sincronizar agora", "cloud:sync"))
TIMERS = {
    "sync": ("astroverso-cloud-sync", "*-*-* *:20:00", "sincroniza as pastas de duas vias", "sync"),
    "send": ("astroverso-cloud-send", "*-*-* 05:00:00", "envia as pastas de uma via", "send"),
}
LATE = {"sync": 3 * 3600, "send": 30 * 3600}


def _timer_units(kind: str) -> dict[str, str]:
    name, when, what, action = TIMERS[kind]
    return {
        f"{name}.timer": "\n".join([
            "[Unit]", f"Description=Astroverso cloud: {what}", "", "[Timer]", f"OnCalendar={when}", "Persistent=true", "",
            "[Install]", "WantedBy=timers.target", "",
        ]),
        f"{name}.service": "\n".join([
            "[Unit]", f"Description=Astroverso cloud: {what}", "After=network-online.target", "", "[Service]", "Type=oneshot",
            f"ExecStart={COMMAND} {APP} action {action}-timer", "",
        ]),
    }


def _timer_change(kind: str, label: str, why: str) -> changes.Change:
    texts = _timer_units(kind)
    name = TIMERS[kind][0]
    return changes.Change(kind, label, why, lambda: units.active(f"{name}.timer"),
                          lambda: units.install(texts, [f"{name}.timer"]), lambda: units.remove(list(texts)), danger=True)


def items() -> list[changes.Change]:
    return [
        _timer_change("sync", "Sincronizar as pastas de duas vias de hora em hora",
                      f"Um timer do usuário ({TIMERS['sync'][0]}.timer) roda o rclone bisync de cada sincronização a cada hora "
                      "(minuto 20). Sem ele, nada vai nem volta da nuvem."),
        _timer_change("send", "Enviar as pastas de uma via todo dia às 05:00",
                      f"Um timer do usuário ({TIMERS['send'][0]}.timer) espelha cada envio na nuvem às 05:00, depois dos backups "
                      "da madrugada. Se a máquina estava desligada, roda ao ligar."),
        watch.change(APP, "Verificar a nuvem de hora em hora e avisar no Discord",
                     f"Um timer do usuário ({watch.name(APP)}.timer) confere cada sincronização e envio (falha, exclusões "
                     "travadas, disco indisponível, atraso) e avisa no canal #cloud do Discord só quando algo muda.",
                     "a nuvem"),
        kit_backup.change(APP),
    ]


def status() -> bool:
    return config.env_file(APP).exists()


def add_account() -> None:
    providers = list(jobs.PROVIDERS.values())
    index = ui.menu("Qual nuvem?", [item.LABEL for item in providers] + ["Voltar"])
    if index >= len(providers):
        return
    provider = providers[index]
    section = jobs.new_account_id(provider.NAME)
    user = provider.login(section)
    jobs.save_accounts(jobs.accounts() + [jobs.Account(section, provider.NAME, user)])


def relogin(item: jobs.Account) -> None:
    provider = jobs.PROVIDERS.get(item.provider)
    if provider is None:
        ui.fail(f"provedor desconhecido: {item.provider}")
    user = provider.login(item.id, item.user)
    jobs.save_accounts([jobs.Account(item.id, item.provider, user) if other.id == item.id else other for other in jobs.accounts()])


def manage_accounts() -> None:
    while True:
        found = jobs.accounts()
        if found:
            ui.table([[item.label(), ui.good("conectada") if item.id in rclone.sections() else ui.pending("entre de novo")] for item in found],
                     ["Conta", "Situação"])
        options = ["Adicionar uma conta"] + (["Entrar de novo numa conta", "Remover uma conta"] if found else []) + ["Pronto"]
        choice = options[ui.menu("Contas na nuvem", options)]
        if choice == "Pronto":
            return
        if choice == "Adicionar uma conta":
            add_account()
            continue
        index = ui.menu("Qual conta?", [item.label() for item in found] + ["Voltar"])
        if index >= len(found):
            continue
        if choice.startswith("Entrar"):
            relogin(found[index])
        elif any(job.account == found[index].id for job in jobs.jobs()):
            ui.warn("essa conta tem sincronizações ou envios: tire-os antes, em Sincronizações e envios")
        elif ui.confirm(f"Remover a conta {found[index].label()} desta máquina? (nada é apagado na nuvem)", default=False):
            rclone.drop_section(found[index].id)
            jobs.save_accounts([item for item in found if item.id != found[index].id])
            ui.ok("conta removida desta máquina")


def pick_remote(account: str) -> str | None:
    path = ""
    while True:
        names = rclone.folders(account, path)
        if names is None:
            return None
        here = f"/{path}" if path else "/ (raiz)"
        options = ([".. (voltar uma pasta)"] if path else []) + [f"{name}/" for name in names] + [f"Usar esta pasta: {here}", "Criar uma pasta aqui", "Cancelar"]
        choice = options[ui.menu(f"Pasta na nuvem: {here}", options)]
        if choice == "Cancelar":
            return None
        if choice.startswith("Usar"):
            return path
        if choice.startswith(".."):
            path = path.rpartition("/")[0]
        elif choice == "Criar uma pasta aqui":
            name = ui.ask("nome da pasta nova", validate=_folder_name)
            if rclone.mkdir(account, f"{path}/{name}".lstrip("/")):
                path = f"{path}/{name}".lstrip("/")
        else:
            path = f"{path}/{choice.rstrip('/')}".lstrip("/")


def _folder_name(value: str) -> str:
    value = value.strip()
    if not value or "/" in value or value in (".", ".."):
        raise ValueError("um nome de pasta, sem /")
    return value


def _local(value: str) -> str:
    path = Path(value.strip()).expanduser()
    if not path.is_absolute():
        raise ValueError("use um caminho completo")
    if path in (Path("/"), Path.home()) or config.home() == path or config.home() in path.parents:
        raise ValueError("escolha uma pasta só para isso (fora do ~/.astroverso)")
    return str(path)


def add_job(kind: str) -> None:
    found = [item for item in jobs.accounts() if item.id in rclone.sections()]
    if not found:
        ui.warn("nenhuma conta conectada: adicione uma em Contas na nuvem")
        return
    if kind == "sync":
        ui.note("Duas vias: o que muda na pasta da máquina vai para a nuvem e o que muda na nuvem vem para a pasta, de hora em hora.")
    else:
        ui.note("Uma via: a pasta da nuvem vira um espelho da pasta da máquina, todo dia às 05:00 (o que sai daqui sai de lá).")
    index = 0 if len(found) == 1 else ui.menu("Qual conta?", [item.label() for item in found])
    owner = found[index]
    local = folders.pick("pasta da máquina", validate=_local)
    Path(local).mkdir(parents=True, exist_ok=True)
    remote = pick_remote(owner.id)
    if remote is None:
        ui.info("nada mudou")
        return
    job = Job(jobs.new_job_id(kind, local, f"{owner.id}:{remote}"), kind, local, owner.id, remote)
    if any(item.id == job.id for item in jobs.jobs()):
        ui.warn("isso já está cadastrado")
        return
    jobs.save_jobs(jobs.jobs() + [job])
    ui.ok(f"{local} {job.arrow()} {owner.label()}:/{remote}")
    if kind == "sync":
        ui.info("a primeira rodada junta os dois lados sem apagar nada; ela roda no próximo horário ou em Sincronizar agora")


def _job_rows() -> list[list[str | ui.Cell]]:
    saved = jobs.states()
    rows: list[list[str | ui.Cell]] = []
    for job in jobs.jobs():
        owner = jobs.account(job.account)
        rows.append([jobs.KINDS[job.kind], job.local, job.arrow(), f"{owner.label() if owner else job.account}:/{job.remote}", _situation(saved.get(job.id, {}))])
    return rows


def _situation(item: dict) -> ui.Cell:
    if item.get("blocked"):
        return ui.bad("exclusões travadas")
    if item.get("error"):
        return ui.bad("falhou")
    if item.get("ok"):
        return ui.good(time.strftime("%d/%m %H:%M", time.localtime(item["ok"])))
    return ui.off("ainda não rodou")


def manage_jobs() -> None:
    while True:
        current = jobs.jobs()
        if current:
            ui.table(_job_rows(), ["Tipo", "Pasta da máquina", "", "Na nuvem", "Última rodada"])
        options = ["Adicionar uma sincronização (duas vias)", "Adicionar um envio (uma via)"] + (["Tirar"] if current else []) + ["Pronto"]
        choice = options[ui.menu("Sincronizações e envios", options)]
        if choice == "Pronto":
            return
        if choice.startswith("Adicionar uma"):
            add_job("sync")
        elif choice.startswith("Adicionar um"):
            add_job("send")
        else:
            chosen = ui.checklist("O que sai?", [f"{job.local} {job.arrow()} {job.target()}" for job in current], cancel=True) or []
            if chosen:
                jobs.save_jobs([job for i, job in enumerate(current) if i not in chosen])
                ui.ok("tirado (nada foi apagado, nem na máquina nem na nuvem)")


def release() -> None:
    blocked = [job for job in jobs.jobs() if jobs.states().get(job.id, {}).get("blocked")]
    if not blocked:
        ui.info("nenhuma sincronização ou envio com exclusões travadas")
        return
    index = ui.menu("Qual?", [f"{job.local} {job.arrow()} {job.target()}" for job in blocked] + ["Voltar"])
    if index >= len(blocked):
        return
    job = blocked[index]
    ui.info("conferindo o que seria apagado (sem apagar nada)...")
    lines = jobs.preview(job)
    for line in lines[:30]:
        ui.prefixed(line)
    if len(lines) > 30:
        ui.info(f"... e mais {len(lines) - 30}")
    ui.warn(f"{len(lines)} exclusões. Renomear ou mover uma pasta grande também aparece assim (apaga uma, cria outra)")
    if not ui.confirm("Liberar essas exclusões nesta rodada?", default=False):
        return
    with jobs.locked(True):
        jobs.run_job(job, force=True)


def install(reuse: bool | None = None) -> None:
    again = config.reuse(APP) if reuse is None else reuse
    ui.step("Nuvem")
    ui.note(
        "Liga pastas da máquina a uma conta na nuvem: sincronizações de duas vias (as duas pontas ficam iguais) e envios "
        "de uma via (a nuvem vira um espelho da pasta). Você escolhe as pastas: o Astroverso não decide o que vai para a nuvem."
    )
    distro.install(["rclone"])
    config.save(APP, {})
    for item in jobs.accounts():
        if item.id not in rclone.sections():
            ui.info(f"a conta {item.label()} precisa de login nesta máquina")
            relogin(item)
    if not jobs.accounts() and ui.confirm("Conectar uma conta na nuvem agora?", default=True):
        add_account()
    if not again and jobs.accounts():
        manage_jobs()
    jobs.publish()
    changes.install(APP, items(), again)
    summary()


def remove() -> None:
    ui.step("Nuvem")
    changes.undo_all(items())
    clouds.withdraw(APP)
    ui.info("as pastas da máquina e da nuvem ficaram como estão")
    config.purge(APP)


def backup(folder: Path) -> None:
    for name in (".env", "accounts.json", "jobs.json"):
        source = config.state(APP) / name
        if source.exists():
            shutil.copy2(source, folder / name)


def restore(folder: Path) -> None:
    if not (folder / ".env").exists():
        ui.fail(f"backup sem a configuração do {APP}")
    for name in (".env", "accounts.json", "jobs.json"):
        if (folder / name).exists():
            target = config.state(APP) / name
            shutil.copy2(folder / name, target)
            target.chmod(0o600)
    ui.info("as senhas das contas não entram no backup: cada conta pede o login de novo")
    install(reuse=True)


def summary() -> None:
    ui.step("Resumo da nuvem")
    ui.section("Contas")
    ui.table([[item.label(), ui.good("conectada") if item.id in rclone.sections() else ui.pending("entre de novo")] for item in jobs.accounts()]
             or [[ui.off("nenhuma"), "-"]], ["Conta", "Situação"])
    ui.section("Sincronizações e envios")
    ui.table(_job_rows() or [[ui.off("nenhum"), "-", "", "-", "-"]], ["Tipo", "Pasta da máquina", "", "Na nuvem", "Última rodada"])
    ui.section("Mudanças no sistema")
    ui.table(changes.rows(items()), ["Mudança", "Situação"])
    watch.summary(APP)


def collect(previous: watch.State) -> dict[str, Problem]:
    found: dict[str, Problem] = {}
    saved = jobs.states()
    now = time.time()
    for job in jobs.jobs():
        item = saved.get(job.id, {})
        where = f"{job.local} {job.arrow()} {job.target()}"
        if item.get("blocked"):
            found[job.id] = Problem("erro", f"Exclusões travadas: {where}", "Mais de 5% dos arquivos seriam apagados. Confira e use Liberar exclusões no gerenciador.", "blocked")
        elif item.get("error"):
            found[job.id] = Problem("erro", f"Falhou: {where}", item["error"], "error")
        elif item.get("ok") and now - item["ok"] > LATE[job.kind]:
            found[job.id] = Problem("aviso", f"Atrasado: {where}", f"Última rodada certa em {time.strftime('%d/%m %H:%M', time.localtime(item['ok']))}.", "late")
    return found


def check() -> None:
    watch.run(APP, collect, BUTTONS, "nuvem em dia")


def manage() -> None:
    changes.manage(APP, items())


def actions() -> list[Action]:
    return [
        Action("summary", "Resumo da nuvem", summary, remote=True),
        Action("accounts", "Contas na nuvem", manage_accounts),
        Action("jobs", "Sincronizações e envios", manage_jobs),
        Action("sync", "Sincronizar agora", lambda: jobs.run_kind("sync", False), remote=True),
        Action("send", "Enviar agora", lambda: jobs.run_kind("send", False), remote=True),
        Action("sync-timer", "Sincronizar (timer)", lambda: jobs.run_kind("sync", False), menu=False),
        Action("send-timer", "Enviar (timer)", lambda: jobs.run_kind("send", True), menu=False),
        Action("release", "Liberar exclusões", release),
        Action("changes", "Mudanças no sistema", manage),
        Action("watch", "Verificar agora", check, remote=True),
        Action("backup-now", "Fazer backup agora", lambda: kit_backup.run_backup(APP, backup), remote=True),
        Action("restore-version", "Restaurar uma versão", lambda: kit_backup.restore(APP, backup, restore)),
    ]
