from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from kit import changes, config, disks, run, ui

from . import mount, photos

APP = "disks"


def blank_disks(data: dict, used: set[str]) -> list[dict[str, str]]:
    found: list[dict[str, str]] = []
    for disk in data.get("blockdevices") or []:
        if disk.get("type") != "disk" or int(disk.get("size") or 0) < 2**30:
            continue
        nodes = list(mount._tree(disk))
        if any(point for node in nodes for point in node.get("mountpoints") or [] if point):
            continue
        if any(node.get("uuid") in used for node in nodes if node.get("uuid")):
            continue
        content = sorted({str(node["fstype"]) for node in nodes if node.get("fstype")})
        found.append({"path": str(disk.get("path") or ""), "size": str(disk.get("size") or 0),
                      "model": (disk.get("model") or "").strip() or "-", "content": ", ".join(content) or "vazio"})
    return [item for item in found if item["path"]]


def scan_blank(used: set[str]) -> list[dict[str, str]]:
    output = run.capture(["lsblk", "-J", "-b", "--tree", "-o", "PATH,UUID,SIZE,FSTYPE,TYPE,MOUNTPOINTS,MODEL"])
    return blank_disks(json.loads(output or "{}"), used)


def size_of(path: Path) -> int:
    code, output = run.output(["podman", "unshare", "du", "-sb", str(path)])
    try:
        return int(output.split()[0]) if code == 0 else 0
    except (IndexError, ValueError):
        return 0


def format_disk(device: str, name: str, password: str) -> str:
    run.cmd(["wipefs", "-a", device], sudo=True)
    run.cmd(["cryptsetup", "luksFormat", "--type", "luks2", "--batch-mode", "--label", name, "--key-file=-", device],
            sudo=True, input=password)
    run.succeeds(["udevadm", "settle"], timeout=30)
    uuid = mount.info(device).get("uuid", "")
    if not uuid:
        ui.fail(f"o disco {device} foi criptografado, mas não apareceu com um UUID: rode o resgate de novo")
    run.cmd(["cryptsetup", "open", "--key-file=-", device, mount.mapper(uuid)], sudo=True, input=password)
    run.cmd(["mkfs.ext4", "-q", "-L", name, f"/dev/mapper/{mount.mapper(uuid)}"], sudo=True)
    run.succeeds(["udevadm", "settle"], timeout=30)
    ui.ok(f"{device} formatado: criptografado (LUKS2) e ext4, com o nome {name}")
    return uuid


def _typed(name: str) -> Callable[[str], str]:
    def check(value: str) -> str:
        if value.strip() != name:
            raise ValueError(f"digite exatamente {name}")
        return value.strip()
    return check


def rescue(registry: Callable[[], list[dict[str, str]]], save_registry: Callable[[list[dict[str, str]]], None],
           attach: Callable[[str], None], disk_change: Callable[[dict[str, str]], changes.Change]) -> None:
    run.sudo_prepare("formatar o disco novo e mexer no /etc/fstab")
    sources = [(disk, disks.photo_of(disk.path) or {}) for disk in disks.photo_disks()]
    sources = [(disk, info) for disk, info in sources if info.get("source_name")]
    if not sources:
        ui.fail("nenhum disco de fotografias montado: cadastre-o primeiro em Discos da máquina")
    ui.note(
        "O resgate recria um disco que morreu a partir da última fotografia: formata o disco novo (criptografado, com o "
        "TPM), dá a ele o nome do antigo, monta no mesmo lugar e copia de volta tudo o que está no atual/ da fotografia. "
        "O que mudou depois da última fotografia não volta."
    )
    index = ui.menu("De qual disco de fotografias?", [f"{disk.name}  (fotografias de {info['source_name']})" for disk, info in sources] + ["Voltar"])
    if index >= len(sources):
        return
    photo, info = sources[index]
    name, old = info["source_name"], info.get("source_uuid", "")
    current = photo.path / photos.CURRENT
    if not current.is_dir() or not any(current.iterdir()):
        ui.fail(f"{current} está vazio: não há fotografia para resgatar")
    alive = disks.ROOT / name
    if disks.mounted(alive) and disks.responds(alive):
        ui.fail(f"o disco {name} está montado e respondendo em {alive}: o resgate é para um disco que morreu")
    used = {entry["uuid"] for entry in registry()} | {disk.uuid for disk in disks.mounts()}
    candidates = scan_blank(used)
    if not candidates:
        ui.fail("nenhum disco novo encontrado: ligue o disco novo (ele não pode estar montado nem cadastrado)")
    choice = ui.menu("Qual é o disco novo?", [f"{item['path']}  {mount.human(int(item['size']))}  {item['model']}  ({item['content']})"
                                              for item in candidates] + ["Voltar"])
    if choice >= len(candidates):
        return
    device = candidates[choice]
    needed = size_of(current)
    if needed and int(device["size"]) < needed:
        ui.fail(f"o disco novo tem {mount.human(int(device['size']))}, e a fotografia precisa de {mount.human(needed)}")
    ui.warn(f"tudo o que está em {device['path']} ({device['content']}) será apagado")
    ui.ask(f"digite {name} para confirmar", validate=_typed(name))
    ui.note("A senha do LUKS do disco novo: guarde no seu gerenciador de senhas. Ela é a reserva do TPM.")
    password = ui.secret(f"senha do LUKS do novo {name}")
    for entry in [item for item in registry() if item["uuid"] == old or item.get("name") == name]:
        mount.detach(entry["uuid"])
        config.save(APP, {changes.key(disk_change(entry)): None})
        save_registry([item for item in registry() if item["uuid"] != entry["uuid"]])
        ui.ok(f"o disco antigo {name} saiu do cadastro")
    uuid = format_disk(device["path"], name, password)
    if not mount.tpm_enroll(str(mount.BY_UUID / uuid), name, password):
        ui.fail("o TPM não foi cadastrado no disco novo: confira o Secure Boot e rode o resgate de novo")
    entry = {"uuid": uuid, "name": name}
    save_registry(registry() + [entry])
    attach(uuid)
    target = disks.ROOT / name
    if not disks.mounted(target):
        ui.fail(f"o disco novo não montou em {target}: veja as mensagens acima")
    config.save(APP, {changes.key(disk_change(entry)): "yes"})
    ui.info(f"copiando {mount.human(needed)} da fotografia para {target} (pode demorar horas)...")
    code, output = run.output(["podman", "unshare", "rsync", "-aH", "--numeric-ids", f"{current}/", f"{target}/"])
    if code not in (0, 24):
        ui.error(f"o rsync parou: {photos._tail(output)}")
        ui.fail(f"para continuar a cópia de onde parou, rode: podman unshare rsync -aH --numeric-ids {current}/ {target}/")
    mount.permissions(target)
    pairs = photos.pairs()
    if any(pair["target"] == photo.uuid for pair in pairs):
        pairs = [{**pair, "source": uuid} if pair["target"] == photo.uuid else pair for pair in pairs]
    else:
        pairs.append({"source": uuid, "target": photo.uuid})
    photos.save_pairs(pairs)
    restored = next(disk for disk in disks.mounts() if disk.uuid == uuid)
    photos.mark(photo, restored)
    ui.ok(f"{name} resgatado em {target}, com a fotografia de {photo.name}")
    ui.note(
        "Os apps que usam o disco voltam a encontrá-lo no mesmo caminho. Reinicie a máquina (ou os apps) e confira; num "
        "Nextcloud, rode também o Reparar, para ele reler os arquivos. A fotografia noturna continua, agora do disco novo."
    )
