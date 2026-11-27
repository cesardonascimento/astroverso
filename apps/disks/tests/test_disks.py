import io
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "packages"))

from kit import config, disks, ui
from kit.testing import run_in_pty
from manager.apps import load

APP = load(ROOT / "apps" / "disks")
assert APP.module is not None, APP.problem
app = APP.module
mount = app.mount

LUKS = "1111aaaa-2222-3333-4444-555566667777"
PLAIN = "9999bbbb-8888-7777-6666-555544443333"
GONE = "0000cccc-1111-2222-3333-444455556666"
SCAN = {"blockdevices": [
    {"path": "/dev/nvme0n1", "type": "disk", "model": "Sistema", "children": [
        {"path": "/dev/nvme0n1p1", "uuid": "raiz", "fstype": "xfs", "size": 2**40, "mountpoints": ["/"]}]},
    {"path": "/dev/sda", "type": "disk", "model": "Gaveta USB ", "children": [
        {"path": "/dev/sda1", "uuid": LUKS, "fstype": "crypto_LUKS", "label": None, "size": 2**40, "children": [
            {"path": f"/dev/mapper/luks-{LUKS}", "uuid": "dentro", "fstype": "ext4", "label": "dados", "size": 2**40}]},
        {"path": "/dev/sda2", "uuid": "pequena", "fstype": "vfat", "size": 2**20}]},
    {"path": "/dev/sdb", "type": "disk", "model": None, "uuid": PLAIN, "fstype": "ntfs", "label": "jogos", "size": 2**41},
]}


class DisksAppTest(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.home = Path(temp.name)
        patch = mock.patch.dict(os.environ, {"HOME": str(self.home)})
        patch.start()
        self.addCleanup(patch.stop)
        ui.set_app("disks")
        patch = mock.patch.object(__import__("kit.vault").vault, "units", mock.Mock(active=mock.Mock(return_value=False)))
        patch.start()
        self.addCleanup(patch.stop)

    def test_scan(self) -> None:
        found = mount.parse_scan(SCAN)
        self.assertEqual([(item.uuid, item.label, item.kind(), item.model) for item in found],
                         [(LUKS, "dados", "criptografado, ext4", "Gaveta USB"), (PLAIN, "jogos", "ntfs", "-")])
        self.assertEqual(mount.human(2**40), "1.0T")

    @unittest.skipUnless(shutil.which("systemd-escape"), "sem systemd-escape")
    def test_escape_matches_systemd(self) -> None:
        def real(*args: str) -> str:
            return subprocess.run(["systemd-escape", *args], capture_output=True, text=True, check=True).stdout.strip()

        self.assertEqual(mount.mount_unit(Path("/srv/meu-disco.2")), real("-p", "--suffix=mount", "/srv/meu-disco.2"))
        self.assertEqual(mount.crypt_unit(LUKS), f"systemd-cryptsetup@{real(f'luks-{LUKS}')}.service")
        self.assertEqual(mount.device_unit(LUKS), real("-p", "--suffix=device", f"/dev/disk/by-uuid/{LUKS}"))

    def test_plan(self) -> None:
        luks = mount.plan(LUKS, "dentro", "ext4", Path("/srv/dados"), True, 1000, 1000)
        self.assertTrue(luks.fstab.startswith("UUID=dentro /srv/dados ext4 nofail,nosuid,nodev,x-systemd.device-timeout=5min,"))
        self.assertIn(f"x-systemd.requires={mount.crypt_unit(LUKS)}", luks.fstab)
        self.assertIn("x-systemd.before=user@1000.service", luks.fstab)
        self.assertTrue(luks.fstab.endswith(" 0 2"))
        self.assertEqual(luks.crypttab, f"luks-{LUKS} UUID={LUKS} none tpm2-device=auto,headless=true,nofail,x-systemd.device-timeout=10s,x-udisks-auth")
        self.assertEqual(luks.links, ((mount.device_unit(LUKS), mount.crypt_unit(LUKS)), (mount.crypt_unit(LUKS), "srv-dados.mount")))
        self.assertTrue(disks.owns(LUKS, luks.fstab) and disks.ours("fstab", luks.fstab) and disks.ours("crypttab", luks.crypttab))
        plain = mount.plan(PLAIN, PLAIN, "ntfs", Path("/srv/jogos"), False, 1000, 1001)
        self.assertIn(" ntfs3 ", plain.fstab)
        self.assertIn("uid=1000,gid=1001,umask=077", plain.fstab)
        self.assertTrue(plain.fstab.endswith(" 0 0"))
        self.assertEqual(plain.crypttab, "")
        self.assertEqual(mount.target_name("dados", LUKS, {"dados"}), "dados-1111aaaa")
        self.assertEqual(mount.target_name("com espaço", LUKS, set()), "disco-1111aaaa")

    def test_write_tables(self) -> None:
        fstab, crypttab = self.home / "fstab", self.home / "crypttab"
        old = mount.plan(PLAIN, PLAIN, "ext4", Path("/srv/velho"), False, 1000, 1000)
        fstab.write_text(f"UUID=raiz / xfs defaults 0 0\n{disks.MARK}{PLAIN}\n{old.fstab}\nUUID=x /srv/solto ext4 nofail,x-udisks-auth,container_file_t 0 0\n")
        written: dict[str, tuple[str, int]] = {}

        def put(path, content, mode=None):
            written[str(path)] = (content, mode)
            Path(path).write_text(content)
            return True

        new = mount.plan(LUKS, "dentro", "ext4", Path("/srv/dados"), True, 1000, 1000)
        with mock.patch.object(disks, "FSTAB", fstab), mock.patch.object(mount, "CRYPTTAB", crypttab), \
                mock.patch.object(mount.distro, "file_put", side_effect=put), mock.patch.object(mount.run, "cmd") as cmd:
            released = mount.write_tables(LUKS, new)
            self.assertEqual(released, ["/srv/solto"])
            self.assertEqual(fstab.read_text(), "\n".join([
                "UUID=raiz / xfs defaults 0 0", f"{disks.MARK}{PLAIN}", old.fstab, f"{disks.MARK}{LUKS}", new.fstab, ""]))
            self.assertEqual(written[str(crypttab)], (f"{disks.MARK}{LUKS}\n{new.crypttab}\n", 0o600))
            cmd.assert_called_once_with(["cp", "-a", str(fstab), str(fstab) + ".astroverso-bak"], sudo=True)
            self.assertTrue(mount.configured(LUKS))
            mount.write_tables(PLAIN, None)
            self.assertNotIn(old.fstab, fstab.read_text())
            self.assertIn(new.fstab, fstab.read_text())

    def test_choose(self) -> None:
        app.save_registry([{"uuid": PLAIN, "name": "jogos"}, {"uuid": GONE, "name": "velho"}])
        attached: list[str] = []

        def attach(uuid, name, taken):
            attached.append(uuid)
            return name or "dados"

        with mock.patch.object(mount, "scan", return_value=mount.parse_scan(SCAN)), \
                mock.patch.object(mount, "attach", side_effect=attach), mock.patch.object(mount, "detach") as detach, \
                mock.patch.object(mount, "configured", return_value=True), mock.patch.object(disks, "mounts", return_value=[]):
            outcome = run_in_pty(lambda: (app.choose(), app.registry())[1], [b" ", b"\x1b[B\x1b[B", b" ", b"\r", b"s\n"], columns=160)
        self.assertEqual(outcome.code, 0, outcome.screen)
        self.assertEqual(outcome.result, [{"uuid": PLAIN, "name": "jogos"}, {"uuid": LUKS, "name": "dados"}])
        self.assertIn("deixam de ser montados: velho", outcome.screen)
        self.assertIn("desligado", outcome.screen)
        values = config.load("disks")
        self.assertEqual((values.get("CHANGE_DISK_1111AAAA"), values.get("CHANGE_DISK_9999BBBB")), ("yes", "yes"))

    def test_collect(self) -> None:
        found = [disks.Disk(LUKS, Path("/srv/dados"), "ext4", ""), disks.Disk(PLAIN, Path("/srv/jogos"), "ntfs3", ""),
                 disks.Disk(GONE, Path("/srv/velho"), "ext4", "")]
        with mock.patch.object(disks, "mounts", return_value=found), \
                mock.patch.object(disks, "mounted", side_effect=lambda path: path.name != "velho"), \
                mock.patch.object(disks, "responds", side_effect=lambda path: path.name == "dados"), \
                mock.patch.object(disks, "usage", return_value=(95, 100)):
            problems = app.collect({})
        self.assertEqual(sorted(problems), ["full:dados", "jogos", "velho"])
        self.assertEqual(problems["full:dados"].level, "aviso")
        self.assertEqual(problems["jogos"].title, "Disco jogos parou de responder")
        self.assertEqual(problems["velho"].kind, "missing")

    def test_items_and_actions(self) -> None:
        app.save_registry([{"uuid": LUKS, "name": "dados"}])
        ids = [(item.id, item.danger) for item in app.items()]
        self.assertEqual(ids, [("disk-1111aaaa", True), ("watch", False), ("photos", False), ("backup", False)])
        self.assertEqual(app.registry_file().stat().st_mode & 0o777, 0o600)
        self.assertEqual([(a.id, a.remote) for a in app.actions()],
                         [("summary", True), ("disks", False), ("changes", False), ("watch", True), ("photos", False),
                          ("photos-now", True), ("photos-timer", False), ("photos-release", False), ("rescue", False), ("backup-now", True),
                          ("restore-version", False)])
        with mock.patch.object(sys, "stdout", io.StringIO()):
            self.assertFalse(app.status())


if __name__ == "__main__":
    unittest.main()
