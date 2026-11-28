from __future__ import annotations

import json
import os
import re

from kit import container, disks, run, ui

from . import nextcloud

FOLDER = "Discos"


def candidates() -> list[disks.Disk]:
    own = disks.containing(nextcloud.files())
    return [disk for disk in disks.mounts() if own is None or disk.uuid != own.uuid]


def refreshed(items: list[tuple[str, bool]]) -> list[tuple[str, bool]]:
    path = nextcloud.drive
    return [(name, disks.photo_of(path(name)) is not None if disks.mounted(path(name)) else readonly) for name, readonly in items]


def choose() -> bool:
    options = candidates()
    if not options:
        ui.info("nenhum outro disco montado para mostrar no Nextcloud")
        return False
    current = {name for name, _ in nextcloud.drives()}
    ui.note(
        f"Outros discos da máquina podem aparecer no Nextcloud de {nextcloud.admin()}, na pasta {FOLDER}, um por pasta. Os "
        "arquivos continuam onde estão: o Nextcloud só mostra, e vê também o que outros programas gravam. O disco de "
        "fotografias aparece só para leitura (para buscar um arquivo antigo em versoes/). Esses discos não têm versões no "
        "Nextcloud: quem guarda o histórico é a fotografia."
    )
    picked = ui.checklist(
        "Quais discos mostrar no Nextcloud?",
        [f"{disk.name}  (só leitura)" if disks.photo_of(disk.path) is not None else disk.name for disk in options],
        [i for i, disk in enumerate(options) if disk.name in current],
        cancel=True,
        details=[str(disk.path) for disk in options],
    )
    if picked is None:
        return False
    items = refreshed([(options[i].name, False) for i in picked])
    if items == nextcloud.drives():
        return False
    nextcloud.save_drives(items)
    return True


def _mounts() -> list[dict]:
    code, output = nextcloud.occ_output("files_external:list", "--output=json")
    if code != 0 or "[" not in output:
        return []
    try:
        data = json.loads(output[output.index("["):])
    except ValueError:
        return []
    return [item for item in data if isinstance(item, dict) and str(item.get("mount_point", "")).startswith(f"/{FOLDER}/")]


def _create(name: str) -> dict:
    output = nextcloud.occ("files_external:create", f"/{FOLDER}/{name}", "local", "null::null", "-c", f"datadir=/srv/{name}")
    found = re.search(r"(\d+)\s*$", output.strip())
    if not found:
        ui.fail(f"o Nextcloud não devolveu o número do disco {name}: {output.strip()[-200:]}")
    return {"mount_id": found.group(1), "applicable_users": [], "applicable_groups": []}


def sync() -> None:
    wanted = dict(nextcloud.drives())
    existing = _mounts()
    if not wanted and not existing:
        return
    if wanted:
        nextcloud.occ("app:enable", "files_external")
        nextcloud.occ("config:system:set", "files_external_allow_create_new_local", "--type=boolean", "--value=true")
    present: dict[str, dict] = {}
    for item in existing:
        name = str(item["mount_point"]).removeprefix(f"/{FOLDER}/")
        datadir = str((item.get("configuration") or {}).get("datadir", ""))
        if name in wanted and name not in present and datadir == f"/srv/{name}":
            present[name] = item
        else:
            nextcloud.occ("files_external:delete", "--yes", str(item["mount_id"]))
            ui.ok(f"{name} saiu do Nextcloud")
    for name, readonly in wanted.items():
        item = present.get(name) or _create(name)
        mount, owner = str(item["mount_id"]), nextcloud.admin()
        if owner not in (item.get("applicable_users") or []):
            nextcloud.occ("files_external:applicable", "--add-user", owner, mount)
        for other in [user for user in item.get("applicable_users") or [] if user != owner]:
            nextcloud.occ("files_external:applicable", "--remove-user", other, mount)
        for group in item.get("applicable_groups") or []:
            nextcloud.occ("files_external:applicable", "--remove-group", group, mount)
        for key, value in (("readonly", readonly), ("enable_sharing", True), ("filesystem_check_changes", 1), ("previews", True)):
            nextcloud.occ("files_external:option", mount, key, json.dumps(value))
        ui.ok(f"{name} no Nextcloud de {owner}, em /{FOLDER}/{name}" + (" (só leitura)" if readonly else ""))


def forget() -> None:
    for item in _mounts():
        nextcloud.occ("files_external:delete", "--yes", str(item["mount_id"]))


def missing() -> list[str]:
    return [name for name, _ in nextcloud.drives() if not disks.responds(nextcloud.drive(name))]


def stale() -> list[str]:
    found: list[str] = []
    for name, _ in nextcloud.drives():
        path = nextcloud.drive(name)
        if not disks.mounted(path):
            continue
        code, inside = run.output(["podman", "exec", nextcloud.NAME, "stat", "-c", "%d", f"/srv/{name}"], timeout=20)
        if code == 0 and inside.strip().isdigit() and int(inside.strip()) != os.stat(path).st_dev:
            found.append(name)
    return found


def heal() -> list[str]:
    names = stale()
    if names:
        ui.info(f"{', '.join(names)} voltou depois que o Nextcloud subiu: reiniciando os containers para ele aparecer")
        for spec in nextcloud.specs():
            if spec.name in (nextcloud.NAME, nextcloud.CRON):
                container.restart(spec, timeout=1500 if spec.name == nextcloud.NAME else 180)
    return names
