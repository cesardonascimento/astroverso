import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "packages"))

from kit import changes, disks, ui
from kit.testing import run_in_pty
from manager.apps import load

APP = load(ROOT / "apps" / "disks")
assert APP.module is not None, APP.problem
app = APP.module
rescue = app.rescue
photos = app.photos

OLD = "1111aaaa-0000-0000-0000-000000000000"
PHOTO = "2222bbbb-0000-0000-0000-000000000000"
NEW = "3333cccc-0000-0000-0000-000000000000"
TREE = {"blockdevices": [
    {"path": "/dev/nvme0n1", "type": "disk", "size": 2**40, "children": [
        {"path": "/dev/nvme0n1p1", "uuid": "raiz", "fstype": "xfs", "size": 2**40, "mountpoints": ["/"]}]},
    {"path": "/dev/sda", "type": "disk", "size": 2**40, "model": "Fotos", "children": [
        {"path": "/dev/sda1", "uuid": PHOTO, "fstype": "crypto_LUKS", "size": 2**40}]},
    {"path": "/dev/sdb", "type": "disk", "size": 2**41, "model": "Novo ", "fstype": None},
    {"path": "/dev/sdc", "type": "disk", "size": 2**41, "model": "Velho", "children": [
        {"path": "/dev/sdc1", "uuid": "x", "fstype": "ntfs", "size": 2**41}]},
    {"path": "/dev/sdd", "type": "disk", "size": 2**20, "model": "Pequeno"},
]}


class RescueTest(unittest.TestCase):
    def test_blank_disks(self) -> None:
        found = rescue.blank_disks(TREE, {PHOTO})
        self.assertEqual([(item["path"], item["model"], item["content"]) for item in found],
                         [("/dev/sdb", "Novo", "vazio"), ("/dev/sdc", "Velho", "ntfs")])

    @unittest.skipUnless(shutil.which("rsync") and shutil.which("podman"), "sem rsync ou podman")
    def test_rescue(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        home = Path(temp.name)
        srv = home / "srv"
        photo = srv / "storage-vault"
        (photo / "atual" / "nextcloud").mkdir(parents=True)
        (photo / "atual" / "nextcloud" / "a.txt").write_text("de volta")
        mounted = [disks.Disk(PHOTO, photo, "ext4", "")]
        registry = [{"uuid": OLD, "name": "storage"}, {"uuid": PHOTO, "name": "storage-vault"}]
        calls: list[tuple] = []

        def attach(uuid: str) -> None:
            calls.append(("attach", uuid))
            (srv / "storage").mkdir()
            mounted.append(disks.Disk(NEW, srv / "storage", "ext4", ""))

        def save(items: list) -> None:
            registry[:] = items

        for patch in (
            mock.patch.dict(os.environ, {"HOME": str(home)}),
            mock.patch.object(disks, "ROOT", srv),
            mock.patch.object(disks, "mounts", side_effect=lambda fstab=None: list(mounted)),
            mock.patch.object(disks, "mounted", side_effect=lambda path: any(disk.path == path for disk in mounted)),
            mock.patch.object(disks, "responds", return_value=True),
            mock.patch.object(rescue.run, "sudo_prepare"),
            mock.patch.object(rescue, "scan_blank", return_value=rescue.blank_disks(TREE, {PHOTO})),
            mock.patch.object(rescue, "format_disk", side_effect=lambda device, name, password: calls.append(("format", device, name, password)) or NEW),
            mock.patch.object(rescue.mount, "tpm_enroll", side_effect=lambda device, name, known: calls.append(("tpm", name, known)) or True),
            mock.patch.object(rescue.mount, "detach", side_effect=lambda uuid, wipe=False: calls.append(("detach", uuid))),
            mock.patch.object(rescue.mount, "permissions"),
        ):
            patch.start()
            self.addCleanup(patch.stop)
        ui.set_app("disks")
        photos.mark(mounted[0], disks.Disk(OLD, srv / "storage", "ext4", ""))
        photos.save_pairs([{"source": OLD, "target": PHOTO}])
        keys = [b"\r", b"\r", b"storag\n", b"storage\n", b"nova\n", b"nova\n"]
        outcome = run_in_pty(lambda: (rescue.rescue(lambda: list(registry), save, attach, app.disk_change), calls, registry,
                                      photos.pairs(), (srv / "storage" / "nextcloud" / "a.txt").read_text())[1:], keys, columns=160)
        self.assertEqual(outcome.code, 0, outcome.screen)
        steps, saved, pairs, content = outcome.result
        self.assertEqual(steps, [["detach", OLD], ["format", "/dev/sdb", "storage", "nova"], ["tpm", "storage", "nova"], ["attach", NEW]])
        self.assertEqual(saved, [{"uuid": PHOTO, "name": "storage-vault"}, {"uuid": NEW, "name": "storage"}])
        self.assertEqual(pairs, [{"source": NEW, "target": PHOTO}])
        self.assertEqual(content, "de volta")
        self.assertIn("digite exatamente storage", outcome.screen)
        self.assertIn("storage resgatado", outcome.screen)
        self.assertEqual(disks.photo_of(photo)["source_uuid"], NEW)

    def test_refuses_living_disk(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        srv = Path(temp.name)
        photo = srv / "storage-vault"
        (photo / "atual" / "x").mkdir(parents=True)
        mounted = [disks.Disk(PHOTO, photo, "ext4", ""), disks.Disk(OLD, srv / "storage", "ext4", "")]
        (srv / "storage").mkdir()
        with mock.patch.dict(os.environ, {"HOME": temp.name}), mock.patch.object(disks, "ROOT", srv), \
                mock.patch.object(disks, "mounts", return_value=mounted), mock.patch.object(disks, "mounted", return_value=True), \
                mock.patch.object(disks, "responds", return_value=True), mock.patch.object(rescue.run, "sudo_prepare"):
            photos.mark(mounted[0], mounted[1])
            outcome = run_in_pty(lambda: rescue.rescue(lambda: [], lambda items: None, lambda uuid: None, app.disk_change), [b"\r"])
        self.assertEqual(outcome.code, 1)
        self.assertIn("está montado e respondendo", outcome.screen)


if __name__ == "__main__":
    unittest.main()
