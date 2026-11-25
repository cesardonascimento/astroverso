from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from kit import run

ROOT = Path("/srv")
FSTAB = Path("/etc/fstab")
MARK = "# astroverso "
TIMEOUT = 20


@dataclass(frozen=True)
class Disk:
    uuid: str
    path: Path
    fstype: str
    line: str

    @property
    def name(self) -> str:
        return self.path.name


def escaped(uuid: str) -> str:
    return uuid.replace("-", "\\x2d")


def owns(uuid: str, line: str) -> bool:
    return bool(uuid) and (uuid in line or escaped(uuid) in line)


def ours(kind: str, line: str) -> bool:
    fields = line.split()
    if len(fields) < 4 or line.lstrip().startswith("#"):
        return False
    if kind == "fstab":
        return fields[1].startswith(f"{ROOT}/") and "x-udisks-auth" in fields[3] and "container_file_t" in fields[3]
    return fields[0].startswith("luks-") and "headless=true" in fields[3]


def marks(text: str) -> list[str]:
    found: list[str] = []
    for line in text.splitlines():
        parts = line.split()
        if line.startswith(MARK) and len(parts) > 2 and parts[2] not in found:
            found.append(parts[2])
    return found


def blocks(text: str, kind: str) -> list[tuple[str, str]]:
    uuids = marks(text)
    paired: list[tuple[str, str]] = []
    for line in text.splitlines():
        if not ours(kind, line):
            continue
        owner = next((uuid for uuid in uuids if owns(uuid, line)), "")
        if owner and all(owner != uuid for uuid, _ in paired):
            paired.append((owner, line))
    return paired


def orphans(text: str, kind: str) -> list[str]:
    paired = {line for _, line in blocks(text, kind)}
    return [line for line in text.splitlines() if ours(kind, line) and line not in paired]


def mounts(fstab: Path = FSTAB) -> list[Disk]:
    try:
        text = fstab.read_text()
    except OSError:
        return []
    return [Disk(uuid, Path(line.split()[1]), line.split()[2], line) for uuid, line in blocks(text, "fstab")]


def source(path: Path) -> str:
    code, output = run.output(["findmnt", "-no", "SOURCE", "--mountpoint", str(path)], timeout=TIMEOUT)
    return output.strip() if code == 0 else ""


def mounted(path: Path) -> bool:
    return bool(source(path))


def _device_present(device: str) -> bool:
    if not device.startswith("/dev/mapper/"):
        return True
    slaves = Path("/sys/block") / Path(os.path.realpath(device)).name / "slaves"
    try:
        return all(slave.exists() for slave in slaves.iterdir())
    except OSError:
        return True


def responds(path: Path) -> bool:
    device = source(path)
    if not device or not _device_present(device):
        return False
    code, _ = run.output(["ls", "-A", str(path)], timeout=TIMEOUT)
    return code == 0


def containing(path: Path) -> Disk | None:
    target = Path(os.path.abspath(path))
    for disk in mounts():
        if target == disk.path or disk.path in target.parents:
            return disk
    return None


def available(path: Path) -> bool:
    disk = containing(path)
    return disk is None or responds(disk.path)


def usage(path: Path) -> tuple[int, int]:
    total, used, _ = shutil.disk_usage(path)
    return used, total
