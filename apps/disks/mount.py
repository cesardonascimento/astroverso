from __future__ import annotations

import json
import os
import re
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from kit import disks, distro, run, ui

CRYPTTAB = Path("/etc/crypttab")
UNITS = Path("/etc/systemd/system")
GENERATOR = Path("/run/systemd/generator")
TPM = Path("/dev/tpmrm0")
BY_UUID = Path("/dev/disk/by-uuid")
SYSTEM = {"/", "/boot", "/boot/efi", "/efi", "/home", "/usr", "/var", "[SWAP]"}
KNOWN = {"ext4", "xfs", "btrfs", "ntfs", "exfat", "vfat", "crypto_LUKS"}
LINUX = {"ext4", "xfs", "btrfs"}
FOREIGN = {"ntfs3", "exfat", "vfat"}
NAME = re.compile(r"^[A-Za-z0-9._-]+$")
CONTEXT = "context=system_u:object_r:container_file_t:s0"
MODE = 0o770


@dataclass(frozen=True)
class Found:
    uuid: str
    device: str
    fstype: str
    label: str
    size: int
    model: str
    inner: str

    @property
    def luks(self) -> bool:
        return self.fstype == "crypto_LUKS"

    def kind(self) -> str:
        if not self.luks:
            return self.fstype
        return f"criptografado, {self.inner}" if self.inner else "criptografado, travado"


@dataclass(frozen=True)
class Plan:
    uuid: str
    target: Path
    fstype: str
    fstab: str
    crypttab: str
    links: tuple[tuple[str, str], ...]


def human(size: int) -> str:
    value = float(size)
    for unit in ("B", "K", "M", "G", "T"):
        if value < 1024 or unit == "T":
            return f"{value:.1f}{unit}" if unit in "GT" else f"{int(value)}{unit}"
        value /= 1024
    return f"{value:.1f}T"


def escape(text: str, path: bool = False) -> str:
    if path:
        text = text.strip("/")
    out: list[str] = []
    for index, char in enumerate(text):
        if path and char == "/":
            out.append("-")
        elif char.isascii() and (char.isalnum() or char in ":_.") and not (index == 0 and char == "."):
            out.append(char)
        else:
            out.extend(f"\\x{byte:02x}" for byte in char.encode())
    return "".join(out)


def mapper(uuid: str) -> str:
    return f"luks-{uuid}"


def crypt_unit(uuid: str) -> str:
    return f"systemd-cryptsetup@{escape(mapper(uuid))}.service"


def mount_unit(target: Path) -> str:
    return f"{escape(str(target), path=True)}.mount"


def device_unit(uuid: str) -> str:
    return f"{escape(str(BY_UUID / uuid), path=True)}.device"


def _tree(node: dict) -> Iterator[dict]:
    yield node
    for child in node.get("children") or []:
        yield from _tree(child)


def parse_scan(data: dict) -> list[Found]:
    found: list[Found] = []
    for disk in data.get("blockdevices") or []:
        if disk.get("type") != "disk":
            continue
        if any(set(filter(None, node.get("mountpoints") or [])) & SYSTEM for node in _tree(disk)):
            continue
        model = (disk.get("model") or "").strip() or "-"
        for part in disk.get("children") or [disk]:
            size = int(part.get("size") or 0)
            if part.get("fstype") not in KNOWN or not part.get("uuid") or size < 2**30:
                continue
            inner = next(iter(part.get("children") or []), {}) if part["fstype"] == "crypto_LUKS" else {}
            label = inner.get("label") or part.get("label") or ""
            found.append(Found(part["uuid"], part.get("path") or "", part["fstype"], label, size, model, inner.get("fstype") or ""))
    return found


def scan() -> list[Found]:
    output = run.capture(["lsblk", "-J", "-b", "--tree", "-o", "PATH,UUID,LABEL,SIZE,FSTYPE,TYPE,MOUNTPOINTS,MODEL"])
    return parse_scan(json.loads(output or "{}"))


def info(device: str) -> dict[str, str]:
    output = run.capture(["lsblk", "-J", "-d", "-o", "UUID,FSTYPE,LABEL,FSVER", device])
    rows = json.loads(output or "{}").get("blockdevices") or [{}]
    return {key: str(value or "") for key, value in rows[0].items()}


def target_name(label: str, uuid: str, taken: set[str]) -> str:
    name = label if label and NAME.match(label) else f"disco-{uuid[:8]}"
    return f"{name}-{uuid[:8]}" if name in taken else name


def plan(uuid: str, fs_uuid: str, fs_type: str, target: Path, luks: bool, uid: int, gid: int) -> Plan:
    fstype = "ntfs3" if fs_type == "ntfs" else fs_type
    if luks:
        wait = f"x-systemd.device-timeout=5min,x-systemd.requires={crypt_unit(uuid)}"
    else:
        wait = "x-systemd.device-timeout=10s"
    options = ["nofail", "nosuid", "nodev", wait, "x-udisks-auth", CONTEXT, "x-gvfs-hide", f"x-systemd.before=user@{uid}.service"]
    if fstype in FOREIGN:
        options.append(f"uid={uid},gid={gid},umask=077")
    passno = 2 if fstype in LINUX else 0
    fstab = f"UUID={fs_uuid} {target} {fstype} {','.join(options)} 0 {passno}"
    if luks:
        crypttab = f"{mapper(uuid)} UUID={uuid} none tpm2-device=auto,headless=true,nofail,x-systemd.device-timeout=10s,x-udisks-auth"
        links = ((device_unit(uuid), crypt_unit(uuid)), (crypt_unit(uuid), mount_unit(target)))
    else:
        crypttab = ""
        links = ((device_unit(fs_uuid), mount_unit(target)),)
    return Plan(uuid, target, fstype, fstab, crypttab, links)


def rewrite(text: str, kind: str, keep: list[tuple[str, str]]) -> str:
    lines = [line for line in text.splitlines() if not line.startswith(disks.MARK) and not disks.ours(kind, line)]
    for uuid, line in keep:
        lines += [f"{disks.MARK}{uuid}", line]
    return "\n".join(lines) + "\n"


def mount_options(line: str) -> list[str]:
    fields = line.split()
    return sorted(option for option in (fields[3] if len(fields) > 3 else "").split(",") if not option.startswith("x-"))


def read_crypttab() -> str:
    if not CRYPTTAB.exists():
        return ""
    try:
        return CRYPTTAB.read_text()
    except PermissionError:
        return run.capture(["cat", str(CRYPTTAB)], sudo=True) + "\n"


def read_fstab() -> str:
    try:
        return disks.FSTAB.read_text()
    except OSError:
        return ""


def configured(uuid: str) -> bool:
    return any(owner == uuid for owner, _ in disks.blocks(read_fstab(), "fstab"))


def _save_table(path: Path, current: str, wanted: str, mode: int) -> bool:
    if wanted == current or (not current.strip() and not wanted.strip()):
        return False
    backup = path.with_name(path.name + ".astroverso-bak")
    if path.exists() and not backup.exists():
        run.cmd(["cp", "-a", str(path), str(backup)], sudo=True)
    distro.file_put(path, wanted, mode)
    return True


def write_tables(uuid: str, new: Plan | None) -> list[str]:
    fstab, crypttab = read_fstab(), read_crypttab()
    released = disks.orphans(fstab, "fstab")
    keep_fstab = [item for item in disks.blocks(fstab, "fstab") if item[0] != uuid]
    keep_crypttab = [item for item in disks.blocks(crypttab, "crypttab") if item[0] != uuid]
    if new:
        keep_fstab.append((uuid, new.fstab))
        if new.crypttab:
            keep_crypttab.append((uuid, new.crypttab))
    _save_table(CRYPTTAB, crypttab, rewrite(crypttab, "crypttab", keep_crypttab), 0o600)
    _save_table(disks.FSTAB, fstab, rewrite(fstab, "fstab", keep_fstab), 0o644)
    return [line.split()[1] for line in released]


def link(wanted_by: str, unit: str) -> None:
    folder = UNITS / f"{wanted_by}.wants"
    if (folder / unit).is_symlink():
        return
    run.cmd(["mkdir", "-p", str(folder)], sudo=True)
    run.cmd(["ln", "-sfn", str(GENERATOR / unit), str(folder / unit)], sudo=True)


def unlink(unit: str) -> None:
    for folder in UNITS.glob("*.wants"):
        if not (folder.name.endswith(".device.wants") or folder.name.startswith("systemd-cryptsetup@")):
            continue
        if (folder / unit).is_symlink():
            run.cmd(["rm", "-f", str(folder / unit)], sudo=True)
        try:
            empty = not any(folder.iterdir())
        except OSError:
            empty = False
        if empty:
            run.succeeds(["rmdir", str(folder)], sudo=True)


def tpm_ok(device: str) -> bool:
    return run.succeeds(["cryptsetup", "open", "--test-passphrase", "--token-only", device], sudo=True)


def tpm_enroll(device: str, name: str) -> bool:
    if tpm_ok(device):
        ui.ok(f"o TPM já destrava {name}")
        return True
    if not TPM.exists():
        ui.warn(f"máquina sem TPM 2.0: {name} não pode ser destravado sozinho no boot e fica de fora")
        return False
    ui.note(
        f"{name} é criptografado. Digite a senha do LUKS uma vez para cadastrar o TPM: depois disso, o TPM destrava o "
        "disco no boot, sem pedir senha (a máquina reinicia de longe e ninguém está na frente dela). A senha continua "
        "valendo como reserva."
    )
    for attempt in range(3):
        password = ui.secret(f"senha do LUKS de {name}", confirm=False)
        try:
            run.cmd(
                ["systemd-cryptenroll", "--unlock-key-file=/dev/stdin", "--wipe-slot=tpm2", "--tpm2-device=auto", "--tpm2-pcrs=7", device],
                sudo=True, input=password, quiet=True,
            )
            break
        except SystemExit:
            ui.warn("senha recusada pelo LUKS" + (", tente de novo" if attempt < 2 else ""))
    else:
        ui.warn(f"{name} fica de fora: cadastre de novo em Discos da máquina")
        return False
    if not tpm_ok(device):
        ui.warn(f"o TPM não conseguiu destravar {name} logo depois do cadastro; ele fica de fora")
        return False
    ui.ok(f"TPM cadastrado: {name} destrava sozinho no boot (Secure Boot conferido, PCR 7)")
    return True


def tpm_wipe(uuid: str) -> None:
    device = BY_UUID / uuid
    if not device.exists():
        return
    if run.succeeds(["systemd-cryptenroll", "--wipe-slot=tpm2", str(device)], sudo=True, timeout=60):
        ui.ok(f"TPM descadastrado do disco {uuid}: ele volta a abrir só com a senha")
    else:
        ui.warn(f"não foi possível descadastrar o TPM do disco {uuid} (a senha continua valendo)")


def unlock(uuid: str, name: str) -> bool:
    device = str(BY_UUID / uuid)
    if not tpm_enroll(device, name):
        return False
    if not Path("/dev/mapper", mapper(uuid)).exists() and not run.succeeds(["cryptsetup", "open", "--token-only", device, mapper(uuid)], sudo=True):
        ui.warn(f"não foi possível destravar {name} agora; ele fica de fora")
        return False
    run.succeeds(["udevadm", "settle"], timeout=30)
    return True


def keep_label(uuid: str, label: str) -> None:
    header = info(str(BY_UUID / uuid))
    if label and not header.get("label") and header.get("fsver") == "2":
        run.cmd(["cryptsetup", "config", "--label", label, str(BY_UUID / uuid)], sudo=True)
        ui.ok(f"nome {label} gravado no cabeçalho da criptografia (aparece mesmo com o disco travado)")


def immutable(target: Path, on: bool) -> None:
    run.succeeds(["chattr", "+i" if on else "-i", str(target)], sudo=True)


def permissions(target: Path) -> None:
    if not disks.mounted(target):
        return
    stat = target.stat()
    if (stat.st_uid, stat.st_gid) != (os.getuid(), os.getgid()):
        run.succeeds(["chown", f"{os.getuid()}:{os.getgid()}", str(target)], sudo=True)
    if stat.st_mode & 0o777 != MODE:
        run.cmd(["chmod", f"{MODE:o}", str(target)], sudo=True)


def _elsewhere(device: str, target: Path) -> tuple[bool, bool]:
    code, output = run.output(["findmnt", "-rn", "-o", "TARGET", "-S", os.path.realpath(device)], timeout=20)
    already = busy = False
    for place in (output.splitlines() if code == 0 else []):
        if place == str(target):
            already = True
        elif run.succeeds(["umount", place], sudo=True):
            ui.ok(f"{device} desmontado de {place}")
        else:
            busy = True
    return already, busy


def mount(device: str, new: Plan, before: str) -> bool:
    target = new.target
    already, busy = _elsewhere(device, target)
    if busy:
        ui.warn(f"{device} está em uso em outro lugar: feche os programas que o usam ou reinicie a máquina")
        return False
    if already and before and mount_options(before) != mount_options(new.fstab):
        if run.succeeds(["umount", str(target)], sudo=True):
            already = False
            ui.ok(f"{target} desmontado para aplicar as opções novas")
        else:
            ui.warn(f"{target} está em uso: as opções novas valem a partir do próximo boot")
    if already:
        ui.ok(f"{target} já montado")
        permissions(target)
        return True
    if not disks.mounted(target):
        run.cmd(["mkdir", "-p", str(target)], sudo=True)
        immutable(target, True)
    try:
        run.cmd(["mount", str(target)], sudo=True, quiet=True)
    except SystemExit:
        if new.fstype == "ntfs3":
            ui.note(
                "Um NTFS desligado sem fechar direito (Windows com a inicialização rápida) fica marcado como sujo. "
                f"Rode sudo ntfsfix -d {os.path.realpath(device)} e tente de novo em Discos da máquina."
            )
        ui.warn(f"não foi possível montar {target} agora; ele fica configurado para o próximo boot")
        return False
    ui.ok(f"{device} montado em {target} (também no boot, sem travar se faltar)")
    permissions(target)
    return True


def release(target: Path) -> None:
    if target.parent != disks.ROOT:
        return
    unlink(mount_unit(target))
    if disks.mounted(target):
        if run.succeeds(["umount", str(target)], sudo=True):
            ui.ok(f"{target} desmontado")
        else:
            ui.warn(f"{target} está em uso: ele sai do fstab e deixa de montar no próximo boot")
    if target.is_dir() and not disks.mounted(target):
        immutable(target, False)
        run.succeeds(["rmdir", str(target)], sudo=True)


def close(uuid: str) -> None:
    unlink(crypt_unit(uuid))
    if Path("/dev/mapper", mapper(uuid)).exists() and not run.succeeds(["cryptsetup", "close", mapper(uuid)], sudo=True):
        ui.warn(f"não foi possível travar {mapper(uuid)} (em uso)")


def attach(uuid: str, name: str, taken: set[str]) -> str:
    device = BY_UUID / uuid
    if not device.exists():
        ui.warn(f"disco {name or uuid} não encontrado: ele fica cadastrado e é montado quando for ligado")
        return name
    outer = info(str(device))
    luks = outer.get("fstype") == "crypto_LUKS"
    label = name or outer.get("label", "")
    if luks:
        if not unlock(uuid, label or f"o disco {uuid[:8]}"):
            return name
        device = Path("/dev/mapper", mapper(uuid))
    inner = info(str(device))
    if luks:
        keep_label(uuid, inner.get("label", ""))
    name = name or target_name(inner.get("label", ""), uuid, taken)
    target = disks.ROOT / name
    before = next((line for owner, line in disks.blocks(read_fstab(), "fstab") if owner == uuid), "")
    new = plan(uuid, inner.get("uuid", ""), inner.get("fstype", ""), target, luks, os.getuid(), os.getgid())
    if not new.fstype or not inner.get("uuid"):
        ui.warn(f"{name}: sistema de arquivos não reconhecido; ele fica de fora")
        return name
    for place in write_tables(uuid, new):
        release(Path(place))
    unlink(mount_unit(target))
    for wanted_by, unit in new.links:
        link(wanted_by, unit)
    distro.daemon_reload()
    mount(str(device), new, before)
    return name


def detach(uuid: str, wipe: bool = False) -> None:
    targets = [Path(line.split()[1]) for owner, line in disks.blocks(read_fstab(), "fstab") if owner == uuid]
    for target in targets:
        release(target)
    for place in write_tables(uuid, None):
        release(Path(place))
    close(uuid)
    distro.daemon_reload()
    if targets:
        ui.ok(f"{', '.join(map(str, targets))} fora do fstab: deixa de montar no boot (os dados continuam no disco)")
    if wipe:
        tpm_wipe(uuid)
