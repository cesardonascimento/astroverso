import io
import os
import shutil
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "packages"))

from kit import config, disks, folders, ui
from kit.testing import run_in_pty
from manager.apps import load

APP = load(ROOT / "apps" / "disks")
assert APP.module is not None, APP.problem
photos = APP.module.photos

SOURCE = "1111aaaa-0000-0000-0000-000000000000"
TARGET = "2222bbbb-0000-0000-0000-000000000000"
TOOLS = shutil.which("rsync") and shutil.which("podman")


class PhotosTest(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.home = Path(temp.name)
        self.source = self.home / "srv" / "storage"
        self.target = self.home / "srv" / "storage-vault"
        self.source.mkdir(parents=True)
        self.target.mkdir(parents=True)
        self.disks = [disks.Disk(SOURCE, self.source, "ext4", ""), disks.Disk(TARGET, self.target, "ext4", "")]
        self.sent: list[tuple] = []
        for patch in (
            mock.patch.dict(os.environ, {"HOME": str(self.home)}),
            mock.patch.object(disks, "mounts", side_effect=lambda fstab=None: list(self.disks)),
            mock.patch.object(disks, "mounted", return_value=True),
            mock.patch.object(disks, "responds", return_value=True),
            mock.patch.object(photos.discord, "notify", side_effect=lambda *a, **k: self.sent.append((a, k)) or True),
        ):
            patch.start()
            self.addCleanup(patch.stop)
        ui.set_app("disks")

    def files(self, count: int) -> None:
        (self.source / "nextcloud").mkdir(exist_ok=True)
        for i in range(count):
            (self.source / "nextcloud" / f"{i:02d}.txt").write_text(f"arquivo {i}")

    def pair(self) -> None:
        photos.mark(self.disks[1], self.disks[0])
        photos.save_pairs([{"source": SOURCE, "target": TARGET}])

    def test_mark_hides_disk(self) -> None:
        self.pair()
        self.assertEqual(disks.photo_of(self.target)["source_name"], "storage")
        self.assertEqual(disks.photo_disks(), [self.disks[1]])
        self.assertTrue(disks.in_photo_disk(self.target / "atual" / "x"))
        self.assertFalse(disks.in_photo_disk(self.source / "x"))
        self.assertNotIn(self.target, folders.suggestions())
        self.assertIn(self.source, folders.suggestions())

    @unittest.skipUnless(TOOLS, "sem rsync ou podman")
    def test_shoot_history_and_guard(self) -> None:
        self.files(20)
        self.pair()
        with mock.patch.object(sys, "stdout", io.StringIO()):
            self.assertTrue(photos.run_all())
        current = self.target / "atual" / "nextcloud"
        self.assertEqual(len(list(current.iterdir())), 20)
        self.assertEqual(self.sent[-1][0][:2], ("disks", "info"))
        (self.source / "nextcloud" / "00.txt").write_text("mudou")
        (self.source / "nextcloud" / "01.txt").unlink()
        self.assertEqual(photos.shoot({"source": SOURCE, "target": TARGET}), "")
        today = self.target / "versoes" / date.today().isoformat() / "nextcloud"
        self.assertEqual((current / "00.txt").read_text(), "mudou")
        self.assertFalse((current / "01.txt").exists())
        self.assertEqual(sorted(path.name for path in today.iterdir()), ["00.txt", "01.txt"])
        self.assertEqual((today / "00.txt").read_text(), "arquivo 0")
        for i in range(2, 8):
            (self.source / "nextcloud" / f"{i:02d}.txt").unlink()
        problem = photos.shoot({"source": SOURCE, "target": TARGET})
        self.assertIn("tiraria 6 de 19 arquivos", problem)
        self.assertTrue((current / "02.txt").exists())
        self.assertEqual(photos.states()[TARGET]["blocked"], 6)
        outcome = run_in_pty(photos.release, [b"\r", b"s\n"])
        self.assertEqual(outcome.code, 0, outcome.screen)
        self.assertIn("6 arquivo(s) sairiam", outcome.screen)
        self.assertFalse((current / "02.txt").exists())
        self.assertEqual(photos.states()[TARGET]["blocked"], 0)

    def test_missing_disk_does_nothing(self) -> None:
        self.pair()
        with mock.patch.object(disks, "responds", return_value=False), mock.patch.object(sys, "stdout", io.StringIO()):
            self.assertFalse(photos.run_all())
        self.assertIn("não está montado ou não responde", photos.states()[TARGET]["error"])
        self.assertFalse((self.target / "atual").exists())
        self.assertEqual(self.sent[-1][1]["actions"], (("Tentar de novo", "disks:photos-now"),))

    def test_prune_and_room(self) -> None:
        today = date.today()
        for day in (today, today - timedelta(days=30), today - timedelta(days=31), today - timedelta(days=90)):
            (self.target / "versoes" / day.isoformat()).mkdir(parents=True)
        (self.target / "versoes" / "outra").mkdir()
        with mock.patch.object(photos, "_remove", side_effect=shutil.rmtree):
            self.assertEqual(photos.prune(self.target, today), 2)
            self.assertEqual(sorted(path.name for path in (self.target / "versoes").iterdir()),
                             [(today - timedelta(days=30)).isoformat(), today.isoformat(), "outra"])
            with mock.patch.object(disks, "usage", return_value=(95, 100)):
                self.assertEqual(photos.make_room(self.target), 1)
            self.assertEqual([path.name for path in photos.history(self.target)], [today.isoformat()])

    def test_add_and_drop(self) -> None:
        (self.target / "atual").mkdir()
        with mock.patch.object(disks, "usage", return_value=(10, 100)), mock.patch.object(photos.units, "install") as install:
            outcome = run_in_pty(lambda: (photos.add(), photos.pairs())[1], [b"\r", b"\r", b"s\n"], columns=160)
        self.assertEqual(outcome.code, 0, outcome.screen)
        self.assertEqual(outcome.result, [{"source": SOURCE, "target": TARGET}])
        self.assertIn("já tem uma pasta atual/", outcome.screen)
        self.assertTrue((self.target / disks.PHOTO).exists())
        outcome = run_in_pty(lambda: (photos.drop(), photos.pairs())[1], [b" ", b"\r", b"s\n"])
        self.assertEqual(outcome.result, [])
        self.assertFalse((self.target / disks.PHOTO).exists())

    def test_collect(self) -> None:
        self.pair()
        photos.record(TARGET, last="2020-01-01T03:00", error="o rsync falhou")
        found = photos.collect()
        self.assertIn("sem rodar há", found[f"photo:{TARGET}"].title)
        photos.record(TARGET, blocked=5)
        self.assertIn("parada", photos.collect()[f"photo:{TARGET}"].title)


if __name__ == "__main__":
    unittest.main()
