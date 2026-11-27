from __future__ import annotations

import json
import shutil
from pathlib import Path

from kit import vault
from kit import changes, config, disks, distro, run, ui
from kit import watch as kit_watch
from kit.app import Action
from kit.watch import Problem

from . import mount, photos, rescue

APP = "disks"
DESCRIPTION = "Discos de dados da máquina: montados em /srv/<nome> no boot, os criptografados destravados pelo TPM"
ORDER = 20
PACKAGES = ["cryptsetup", "tpm2-tss", "rsync"]
BUTTONS = (("Resumo dos discos", "disks:summary"), ("Verificar de novo", "disks:watch"))
FULL = 90


def registry_file() -> Path:
    return config.state(APP) / "disks.json"


def registry() -> list[dict[str, str]]:
    try:
        saved = json.loads(registry_file().read_text())
    except (OSError, ValueError):
        return []
    return [item for item in saved if isinstance(item, dict) and item.get("uuid")] if isinstance(saved, list) else []


def save_registry(items: list[dict[str, str]]) -> None:
    temporary = registry_file().with_suffix(".tmp")
    temporary.write_text(json.dumps(items, ensure_ascii=False, indent=2) + "\n")
    temporary.chmod(0o600)
    temporary.replace(registry_file())












def _label(entry: dict[str, str]) -> str:
    return entry.get("name") or f"disco {entry['uuid'][:8]}"


def attach(uuid: str) -> None:
    items = registry()
    entry = next((item for item in items if item["uuid"] == uuid), {"uuid": uuid, "name": ""})
    taken = {item.get("name", "") for item in items if item["uuid"] != uuid} | {disk.name for disk in disks.mounts() if disk.uuid != uuid}
    name = mount.attach(uuid, entry.get("name", ""), taken)
    if name and name != entry.get("name"):
        for item in items:
            if item["uuid"] == uuid:
                item["name"] = name
        save_registry(items)


def disk_change(entry: dict[str, str]) -> changes.Change:
    uuid = entry["uuid"]
    name = entry.get("name") or uuid[:8]
    return changes.Change(
        f"disk-{uuid[:8]}", f"Montar o disco {name} em {disks.ROOT / name}",
        f"O disco entra no /etc/fstab (e no /etc/crypttab, se for criptografado, destravado pelo TPM) e monta no boot em "
        f"{disks.ROOT / name}, só do seu usuário. Sem isso, os apps que guardam coisas nele param de encontrá-lo. "
        "Desfazer só desmonta: os dados continuam no disco.",
        lambda: mount.configured(uuid), lambda: attach(uuid), lambda: mount.detach(uuid), danger=True,
    )


def watch_change() -> changes.Change:
    return kit_watch.change(
        APP, "Verificar os discos de hora em hora",
        "De hora em hora, confere se cada disco está montado, se responde e se tem espaço, e avisa no canal #disks do "
        "Discord só quando algo muda (unidades do usuário astroverso-disks-watch).",
        "os discos",
    )




def extras() -> list[changes.Change]:
    return [watch_change(), photos.change(), vault.change(APP)]


def items() -> list[changes.Change]:
    return [disk_change(entry) for entry in registry()] + extras()


def status() -> bool:
    return config.env_file(APP).exists()


def _row(found: mount.Found) -> str:
    return f"{found.label or Path(found.device).name:<20} {mount.human(found.size):>8}  {found.kind():<24} {found.model}"


def choose() -> None:
    saved = registry()
    known = {item["uuid"]: item for item in saved}
    found = mount.scan()
    lines = [_row(item) for item in found]
    uuids = [item.uuid for item in found]
    for item in saved:
        if item["uuid"] not in uuids:
            lines.append(f"{_label(item):<20} {'-':>8}  {'desligado':<24}")
            uuids.append(item["uuid"])
    if not uuids:
        ui.info("nenhum disco além do disco do sistema")
        return
    ui.note(
        f"Os discos escolhidos montam no boot em {disks.ROOT}/<nome>, só do seu usuário. Os criptografados (LUKS) são "
        "destravados pelo TPM, sem pedir senha. Disco que não é escolhido fica como está, sem ser montado."
    )
    chosen = ui.checklist(
        "Quais discos a máquina monta?", lines, selected=[i for i, uuid in enumerate(uuids) if uuid in known], cancel=True,
    )
    if chosen is None:
        return
    picked = [uuids[i] for i in chosen]
    leaving = [item for item in saved if item["uuid"] not in picked]
    if leaving:
        ui.warn(f"deixam de ser montados: {', '.join(_label(item) for item in leaving)} (os dados continuam nos discos)")
        ui.warn("os apps que guardam coisas nesses discos param de encontrá-los")
        if not ui.confirm("confirma?", default=False):
            ui.info("nada mudou")
            return
    for item in leaving:
        mount.detach(item["uuid"], wipe=True)
        config.save(APP, {changes.key(disk_change(item)): None})
    kept = [item for item in saved if item["uuid"] in picked]
    save_registry(kept + [{"uuid": uuid, "name": ""} for uuid in picked if uuid not in known])
    for uuid in picked:
        attach(uuid)
        entry = next(item for item in registry() if item["uuid"] == uuid)
        config.save(APP, {changes.key(disk_change(entry)): "yes" if mount.configured(uuid) else "no"})


def install(reuse: bool | None = None) -> None:
    again = config.reuse(APP) if reuse is None else reuse
    run.sudo_prepare("montar os discos e mexer no /etc/fstab")
    distro.install(PACKAGES)
    ui.step("Discos da máquina")
    config.save(APP, {})
    if again and registry():
        for entry in registry():
            if changes.wanted(APP, disk_change(entry)) is not False:
                attach(entry["uuid"])
    else:
        choose()
    changes.install(APP, extras(), again)
    summary()


def remove() -> None:
    ui.step("Discos da máquina")
    for entry in registry():
        mount.detach(entry["uuid"], wipe=True)
    changes.undo_all(extras())
    config.purge(APP)


def backup(folder: Path) -> None:
    for source in (config.env_file(APP), registry_file(), photos.pairs_file()):
        if source.exists():
            shutil.copy2(source, folder / source.name)


def restore(folder: Path) -> None:
    if not (folder / ".env").exists():
        ui.fail(f"backup sem a configuração do {APP}: {folder / '.env'}")
    config.state(APP)
    for name, target in ((".env", config.env_file(APP)), ("disks.json", registry_file()), ("photos.json", photos.pairs_file())):
        if (folder / name).exists():
            shutil.copy2(folder / name, target)
            target.chmod(0o600)
    install(reuse=True)


def _situation(disk: disks.Disk) -> tuple[ui.Cell, str]:
    if not disks.mounted(disk.path):
        return ui.bad("não montado"), "-"
    if not disks.responds(disk.path):
        return ui.bad("não responde"), "-"
    used, total = disks.usage(disk.path)
    percent = round(used * 100 / total) if total else 0
    cell = ui.pending("quase cheio") if percent >= FULL else ui.good("montado")
    return cell, f"{mount.human(used)} de {mount.human(total)} ({percent}%)"


def summary() -> None:
    ui.step("Resumo dos discos")
    mounted = {disk.uuid: disk for disk in disks.mounts()}
    rows: list[list[str | ui.Cell]] = []
    for entry in registry():
        disk = mounted.get(entry["uuid"])
        if disk is None:
            rows.append([_label(entry), "-", "-", ui.off("desfeito"), "-"])
            continue
        situation, use = _situation(disk)
        rows.append([disk.name, str(disk.path), disk.fstype, situation, use])
    if rows:
        ui.table(rows, ["Disco", "Caminho", "Sistema", "Situação", "Uso"])
    else:
        ui.info("nenhum disco cadastrado: escolha em Discos da máquina")
    ui.section("Fotografias")
    ui.table(photos.rows() or [[ui.off("nenhuma"), "-", "-", "-"]], ["Origem", "Fotografias em", "Última", "Histórico"])
    ui.section("Mudanças no sistema")
    ui.table(changes.rows(items()), ["Mudança", "Situação"])
    kit_watch.summary(APP)


def collect(previous: kit_watch.State) -> dict[str, Problem]:
    found: dict[str, Problem] = {}
    for disk in disks.mounts():
        if not disks.mounted(disk.path):
            found[disk.name] = Problem("erro", f"Disco {disk.name} não está montado",
                                       "Confira se ele está ligado e conectado: os apps que guardam coisas nele param de encontrá-lo.", "missing")
        elif not disks.responds(disk.path):
            found[disk.name] = Problem("erro", f"Disco {disk.name} parou de responder",
                                       "A conexão caiu e voltou? Ele fica inacessível até a máquina ser reiniciada.", "stuck")
        else:
            used, total = disks.usage(disk.path)
            percent = round(used * 100 / total) if total else 0
            if percent >= FULL:
                found[f"full:{disk.name}"] = Problem("aviso", f"Disco {disk.name} com {percent}% ocupado",
                                                     f"Sobram {mount.human(total - used)}. Libere espaço antes que os apps parem de gravar.", "full")
    found.update(photos.collect())
    return found


def check() -> None:
    kit_watch.run(APP, collect, BUTTONS, "todos os discos montados e respondendo")


def manage() -> None:
    changes.manage(APP, items())


def manage_disks() -> None:
    run.sudo_prepare("montar os discos e mexer no /etc/fstab")
    ui.step("Discos da máquina")
    choose()
















def actions() -> list[Action]:
    return [
        Action("summary", "Resumo dos discos", summary, remote=True),
        Action("disks", "Discos da máquina", manage_disks),
        Action("changes", "Mudanças no sistema", manage),
        Action("watch", "Verificar agora", check, remote=True),
        Action("photos", "Fotografias dos discos", photos.manage),
        Action("photos-now", "Fotografar agora", lambda: photos.run_all(), remote=True, confirm=True),
        Action("photos-timer", "Fotografar (timer)", lambda: photos.run_all(), menu=False),
        Action("photos-release", "Liberar a fotografia", photos.release),
        Action("rescue", "Resgatar um disco", lambda: rescue.rescue(registry, save_registry, attach, disk_change)),
        Action("backup-now", "Fazer backup agora", lambda: vault.run_backup(APP, backup), remote=True),
        Action("restore-version", "Restaurar uma versão", lambda: vault.restore(APP, backup, restore)),
    ]
