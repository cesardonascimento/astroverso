import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "packages"))

from kit import config, ui, vault
from kit.testing import run_in_pty
from manager.apps import load

APP = load(ROOT / "apps" / "vault")
assert APP.module is not None, APP.problem
app = APP.module


class VaultAppTest(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.home = Path(temp.name)
        self.tries: list[dict] = []
        for patch in (
            mock.patch.dict(os.environ, {"HOME": str(self.home)}),
            mock.patch.object(app.distro, "install"),
            mock.patch.object(app.changes, "install"),
            mock.patch.object(app.changes, "undo_all"),
            mock.patch.object(vault, "verify", side_effect=self.verify),
            mock.patch.object(vault.net, "hostname", return_value="servidor"),
        ):
            patch.start()
            self.addCleanup(patch.stop)
        ui.set_app("vault")
        config.home().mkdir()
        (config.home() / "astroverso.env").write_text("DOMAIN=casa.com\n")

    def verify(self, values: dict) -> str:
        self.tries.append(dict(values))
        return "" if values["VAULT_PASSWORD"] == "certa" else "o Nextcloud recusou o usuário ou a senha de app"

    def test_install(self) -> None:
        keys = [b"\r", b"dono\n", b"\r", b"errada\n", b"certa\n", b"chave\n", b"chave\n"]
        outcome = run_in_pty(lambda: (app.install(False), vault.settings())[1], keys, columns=160)
        self.assertEqual(outcome.code, 0, outcome.screen)
        self.assertEqual(outcome.result, {"VAULT_URL": "https://nextcloud.casa.com", "VAULT_USER": "dono", "VAULT_PASSWORD": "certa",
                                          "VAULT_FOLDER": "/Backups", "VAULT_KEY": "chave"})
        self.assertIn("recusou o usuário", outcome.screen)
        self.assertIn("os backups vão para /Backups", outcome.screen)
        self.assertNotIn("chave", outcome.screen.replace("senha dos backups", ""))
        self.assertTrue(app.status())
        with mock.patch.object(sys, "stdout", io.StringIO()) as out:
            app.install(True)
        self.assertIn("continuam indo para /Backups", out.getvalue())

    def test_install_gives_up(self) -> None:
        outcome = run_in_pty(lambda: app.install(False), [b"\r", b"dono\n", b"\r", b"a\n", b"b\n", b"c\n"], columns=160)
        self.assertEqual(outcome.code, 1)
        self.assertIn("o Nextcloud não aceitou", outcome.screen)
        self.assertFalse(app.status())

    def test_change_key_and_remove(self) -> None:
        vault.save("https://nextcloud.casa.com", "dono", "certa", "/Backups", "velha")
        outcome = run_in_pty(lambda: (app.change_key(), vault.settings()["VAULT_KEY"])[1], [b"nova\n", b"nova\n"])
        self.assertEqual(outcome.result, "nova")
        self.assertIn("continuam abrindo só com a senha antiga", outcome.screen)
        config.save("vault", {})
        with mock.patch.object(sys, "stdout", io.StringIO()):
            app.remove()
        self.assertFalse(vault.settings_file().exists())
        self.assertFalse(app.status())

    def test_backup_restore(self) -> None:
        config.save("vault", {})
        folder = self.home / "copia"
        folder.mkdir()
        app.backup(folder)
        self.assertTrue((folder / ".env").exists())
        app.restore(folder)

    def test_actions(self) -> None:
        self.assertEqual([(a.id, a.remote) for a in app.actions()],
                         [("summary", True), ("changes", False), ("test", True), ("key", False), ("backup-now", True), ("restore-version", False)])
        self.assertEqual([item.id for item in app.items()], ["backup"])


if __name__ == "__main__":
    unittest.main()
