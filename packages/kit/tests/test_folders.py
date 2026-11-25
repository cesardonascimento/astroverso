import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from kit import clouds, disks, folders, ui
from kit.testing import run_in_pty


class FoldersTest(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.home = Path(temp.name)
        patch = mock.patch.dict(os.environ, {"HOME": str(self.home)})
        patch.start()
        self.addCleanup(patch.stop)
        ui.set_app("teste")

    def test_clouds_contract(self) -> None:
        clouds.publish("nuvem", [clouds.Linked(Path("/srv/dados/sincronizado"), "drive (duas vias)")])
        self.assertEqual(clouds.load(), [clouds.Linked(Path("/srv/dados/sincronizado"), "drive (duas vias)", "nuvem")])
        self.assertEqual(clouds.mark(Path("/srv/dados/sincronizado/Backups")), "drive (duas vias)")
        self.assertEqual(clouds.mark(Path("/srv/dados/sincronizado")), "drive (duas vias)")
        self.assertEqual(clouds.mark(Path("/srv/dados/sincronizadox")), "")
        clouds.withdraw("nuvem")
        self.assertEqual(clouds.load(), [])

    def test_pick_marks_disks_and_clouds(self) -> None:
        clouds.publish("nuvem", [clouds.Linked(Path("/srv/dados/sincronizado"), "drive (duas vias)")])
        found = [disks.Disk("u", Path("/srv/dados"), "ext4", "")]
        with mock.patch.object(disks, "mounts", return_value=found), mock.patch.object(disks, "responds", return_value=True):
            self.assertIn("☁ drive (duas vias)", folders.describe(Path("/srv/dados/sincronizado/x")))
            self.assertTrue(folders.describe(Path("/srv/dados/y")).startswith("disco dados"))
            outcome = run_in_pty(lambda: folders.pick("pasta", ""), [b"\x1b[B", b"\r", b"Backups\n"], columns=160)
        self.assertEqual(outcome.code, 0, outcome.screen)
        self.assertEqual(outcome.result, "/srv/dados/sincronizado/Backups")
        self.assertIn("☁ drive (duas vias)", outcome.screen)
        self.assertIn("disco do sistema", outcome.screen)
        self.assertEqual(folders.human(1024 ** 3 * 300), "300G")


if __name__ == "__main__":
    unittest.main()
