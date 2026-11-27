import io
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "packages"))

from kit import clouds, config, disks, ui
from kit.testing import run_in_pty
from manager.apps import load

APP = load(ROOT / "apps" / "cloud")
assert APP.module is not None, APP.problem
app = APP.module
jobs = app.jobs
rclone = app.rclone
INSIDE = app.inside_nextcloud


class FakeRclone:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []
        self.replies: list[tuple[int, str]] = []

    def __call__(self, args, env=None, unshare=False, timeout=None):
        self.calls.append([*args, *(["<unshare>"] if unshare else []), *[f"{k}={v}" for k, v in (env or {}).items()]])
        if args[0] == "lsf":
            return 0, {"proton-1:": "Backups/\nFotos/\n", "proton-1:Fotos": "2025/\n"}.get(args[-1], "")
        return self.replies.pop(0) if self.replies else (0, "")


class CloudAppTest(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.home = Path(temp.name)
        ui.set_app("cloud")
        self.fake = FakeRclone()
        for patch in (
            mock.patch.dict(os.environ, {"HOME": str(self.home)}),
            mock.patch.object(rclone, "call", self.fake),
            mock.patch.object(rclone, "obscure", side_effect=lambda secret: f"obscuro({len(secret)})"),
            mock.patch.object(disks, "mounts", return_value=[]),
            mock.patch.object(jobs, "LOCKS", self.home / "locks"),
            mock.patch.object(app, "inside_nextcloud", return_value=False),
            mock.patch.object(__import__("kit.vault").vault, "units", mock.Mock(active=mock.Mock(return_value=False))),
        ):
            patch.start()
            self.addCleanup(patch.stop)

    def connect(self) -> None:
        rclone.set_section("proton-1", {"type": "protondrive", "username": "eu@exemplo.com"})
        jobs.save_accounts([jobs.Account("proton-1", "proton", "eu@exemplo.com")])

    def test_add_account(self) -> None:
        self.fake.replies = [(1, "401 Unauthorized"), (0, "[]")]
        keys = [b"\r", b"eu@exemplo.com\n", b"errada\n", b"\n", b"\n", b"123456\n", b"Senha-certa\n", b"s\n", b"caixa\n", b"\n", b"654321\n"]
        outcome = run_in_pty(lambda: (app.add_account(), self.fake.calls)[1], keys, columns=160)
        self.assertEqual(outcome.code, 0, outcome.screen)
        self.assertIn("o Proton recusou o login", outcome.screen)
        self.assertNotIn("Senha-certa", outcome.screen)
        self.assertEqual(jobs.accounts(), [jobs.Account("proton-1", "proton", "eu@exemplo.com")])
        text = rclone.conf().read_text()
        self.assertIn("[proton-1]", text)
        self.assertIn("password = obscuro(11)", text)
        self.assertIn("mailbox_password = obscuro(5)", text)
        self.assertEqual(rclone.conf().stat().st_mode & 0o777, 0o600)
        self.assertEqual(outcome.result[-1], ["lsjson", "--max-depth", "1", "proton-1:", "RCLONE_PROTONDRIVE_2FA=654321"])
        self.assertTrue(all("Senha" not in part for call in outcome.result for part in call))

    def test_add_sync_job(self) -> None:
        self.connect()
        local = self.home / "dados"
        keys = [b"\r", b"\x1b[B", b"\r", b"dados\n", b"\x1b[B", b"\r", b"\x1b[B", b"\r", b"\x1b[B", b"\r"]
        outcome = run_in_pty(app.add_job, keys, columns=160)
        self.assertEqual(outcome.code, 0, outcome.screen)
        [job] = jobs.jobs()
        self.assertEqual((job.kind, job.local, job.account, job.remote), ("sync", str(local), "proton-1", "Fotos/2025"))
        self.assertTrue(local.is_dir())
        self.assertEqual(clouds.mark(local / "x"), "Proton Drive (duas vias)")

    def test_sync_first_run_resyncs_and_recovers(self) -> None:
        self.connect()
        local = self.home / "dados"
        local.mkdir()
        job = jobs.Job("j1", "sync", str(local), "proton-1", "Fotos")
        jobs.save_jobs([job])
        (self.home / "locks").mkdir()
        (self.home / "locks" / "velha.lck").write_text("")
        with mock.patch.object(sys, "stdout", io.StringIO()):
            self.assertTrue(jobs.run_all(False))
            self.assertIn("--resync", self.fake.calls[-1])
            self.assertIn("<unshare>", self.fake.calls[-1])
            self.assertIn("--max-delete", self.fake.calls[-1])
            self.assertFalse((self.home / "locks" / "velha.lck").exists())
            self.fake.replies = [(2, "Bisync aborted. Must run --resync to recover."), (0, "")]
            self.assertTrue(jobs.run_job(job))
            self.assertNotIn("--resync", self.fake.calls[-2])
            self.assertIn("--resync", self.fake.calls[-1])
            self.fake.replies = [(1, "ERROR : too many deletes - 12%")]
            self.assertFalse(jobs.run_job(job))
            self.assertTrue(jobs.states()["j1"]["blocked"])
            self.assertEqual(sorted(app.collect({})), ["j1"])
            self.assertEqual(app.collect({})["j1"].kind, "blocked")
            with mock.patch.object(disks, "available", return_value=False):
                self.assertFalse(jobs.run_job(job))
            self.assertIn("indisponível", jobs.states()["j1"]["error"])

    def test_late(self) -> None:
        self.connect()
        job = jobs.Job("j2", "sync", str(self.home), "proton-1", "Fotos")
        jobs.save_jobs([job])
        jobs.state_file().write_text(__import__("json").dumps({"j2": {"ok": time.time() - 13 * 3600}}))
        self.assertEqual(app.collect({}), {})
        jobs.state_file().write_text(__import__("json").dumps({"j2": {"ok": time.time() - 15 * 3600}}))
        self.assertEqual(app.collect({})["j2"].kind, "late")

    def test_local_refuses_nextcloud_files(self) -> None:
        with mock.patch.object(app, "inside_nextcloud", return_value=True):
            with self.assertRaises(ValueError):
                app._local(str(self.home / "nextcloud" / "eu" / "files" / "proton"))
        markers = {str(self.home / "nc" / ".ncdata")}
        with mock.patch.object(app.run, "succeeds", side_effect=lambda args, timeout=None: args[-1] in markers):
            self.assertTrue(INSIDE(self.home / "nc" / "eu" / "files" / "proton"))
            self.assertFalse(INSIDE(self.home / "outra" / "pasta"))

    def test_sync_between_two_accounts(self) -> None:
        self.connect()
        rclone.set_section("nextcloud-1", {"type": "webdav", "vendor": "nextcloud"})
        jobs.save_accounts(jobs.accounts() + [jobs.Account("nextcloud-1", "nextcloud", "eu")])
        keys = [b"\x1b[B", b"\r", b"\r", b"\r", b"\x1b[B", b"\r"]
        self.fake.calls.clear()
        outcome = run_in_pty(app.add_job, keys, columns=160)
        self.assertEqual(outcome.code, 0, outcome.screen)
        [job] = jobs.jobs()
        self.assertEqual((job.local, job.account, job.remote, job.remote_source, job.source_account), ("nextcloud-1:", "proton-1", "Backups", True, "nextcloud-1"))
        self.assertIsNone(clouds.mark(Path("/nextcloud-1:")) or None)
        self.assertEqual(clouds.load(), [])
        job = jobs.Job("j9", "sync", "nextcloud-1:Proton", "proton-1", "")
        with mock.patch.object(sys, "stdout", io.StringIO()):
            self.assertTrue(jobs.run_job(job))
        args = self.fake.calls[-1]
        self.assertEqual(args[:3], ["bisync", "nextcloud-1:Proton", "proton-1:"])
        self.assertNotIn("<unshare>", args)
        self.assertEqual(args[args.index("--transfers") + 1], "2")
        rclone.drop_section("nextcloud-1")
        with mock.patch.object(sys, "stdout", io.StringIO()):
            self.assertFalse(jobs.run_job(job))
        self.assertIn("nextcloud-1 não está conectada", jobs.states()["j9"]["error"])

    def test_nextcloud_login(self) -> None:
        (config.home()).mkdir(exist_ok=True)
        (config.home() / "astroverso.env").write_text("DOMAIN=casa.com\n")
        self.fake.replies = [(0, "[]")]
        outcome = run_in_pty(lambda: app.jobs.nextcloud.login("nextcloud-1"), [b"\n", b"eu\n", b"senha-de-app\n"], columns=160)
        self.assertEqual(outcome.code, 0, outcome.screen)
        self.assertEqual(outcome.result, "eu")
        text = rclone.conf().read_text()
        self.assertIn("url = https://nextcloud.casa.com/remote.php/dav/files/eu", text)
        self.assertIn("vendor = nextcloud", text)
        self.assertIn("pass = obscuro(12)", text)
        self.assertNotIn("senha-de-app", outcome.screen)

    def test_nextcloud_from_vault(self) -> None:
        self.connect()
        vault = __import__("kit.vault").vault
        vault.save("https://nextcloud.casa.com", "eu", "senha-do-vault", "/Backups", "chave")
        self.fake.replies = [(0, "[]")]
        outcome = run_in_pty(lambda: app._nextcloud_account().id, [b"\n"], columns=160)
        self.assertEqual(outcome.code, 0, outcome.screen)
        self.assertEqual(outcome.result, "nextcloud-1")
        self.assertIn("Usar a mesma conexão do vault", outcome.screen)
        self.assertIn("pass = obscuro(14)", rclone.conf().read_text())
        self.assertEqual([item.provider for item in jobs.accounts()], ["proton", "nextcloud"])

    def test_install_without_account(self) -> None:
        installed: list[str] = []
        fake_units = mock.Mock(active=mock.Mock(return_value=False), install=lambda texts, start: installed.extend(start))
        with mock.patch.object(app, "units", fake_units), mock.patch.object(app.watch, "units", fake_units), \
                mock.patch.object(app.distro, "install") as install:
            outcome = run_in_pty(lambda: (app.install(reuse=False), installed, [call.args for call in install.call_args_list])[1:],
                                 [b"n\n", b"\n", b"\n", b"\n"], columns=160)
        self.assertEqual(outcome.code, 0, outcome.screen)
        self.assertEqual(outcome.result[0], ["astroverso-cloud-sync.timer", "astroverso-cloud-watch.timer"])
        self.assertEqual(outcome.result[1], [[["rclone"]]])
        self.assertIn("ligue o backup depois", outcome.screen)
        self.assertIn("Resumo da nuvem", outcome.screen)

    def test_backup_leaves_passwords_out(self) -> None:
        self.connect()
        config.save("cloud", {})
        folder = self.home / "copia"
        folder.mkdir()
        app.backup(folder)
        self.assertEqual(sorted(path.name for path in folder.iterdir()), [".env", "accounts.json"])

    def test_items_and_actions(self) -> None:
        self.assertEqual([(item.id, item.danger) for item in app.items()], [("sync", True), ("watch", False), ("backup", False)])
        self.assertIn("cloud action sync-timer", app._timer_units("sync")["astroverso-cloud-sync.service"])
        self.assertIn("OnCalendar=*-*-* 08,10,12,14,16,18,20:00:00", app._timer_units("sync")["astroverso-cloud-sync.timer"])
        self.assertEqual([(a.id, a.remote) for a in app.actions() if a.menu],
                         [("summary", True), ("accounts", False), ("jobs", False), ("sync", True), ("release", False),
                          ("changes", False), ("watch", True), ("backup-now", True), ("restore-version", False)])


if __name__ == "__main__":
    unittest.main()
