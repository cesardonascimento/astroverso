import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "packages"))

from kit import config, container, routes, ui
from kit.testing import run_in_pty
from manager.apps import load

APP = load(ROOT / "apps" / "nextcloud")
assert APP.module is not None, APP.problem
app = APP.module
nextcloud = app.nextcloud


class FakeHost:
    Container = container.Container
    Volume = container.Volume
    NETWORK = "astroverso"

    def __init__(self) -> None:
        self.calls: list[tuple] = []
        self.running: set[str] = set()
        self.rejections = 1
        self.maintenance = False
        self.setup_errors: dict = {}

    def record(self, *call) -> None:
        self.calls.append(call)

    def prepare(self):
        self.record("prepare")

    def start(self, spec, timeout=180):
        self.record("start", spec.name, timeout)
        self.running.add(spec.name)

    def active(self, name):
        return name in self.running

    def remove(self, name, image=None):
        self.record("remove", name)
        self.running.discard(name)

    def remove_image(self, image):
        self.record("remove_image", image)

    def exec(self, name, args, user="", input=None):
        self.record("exec", *args[2:])
        return ""

    def exec_output(self, name, args, user="", env=None):
        command = args[2:]
        if command[0] == "status":
            return 0, json.dumps({"installed": True, "maintenance": self.maintenance, "versionstring": "35.0.3"})
        if command[0] == "user:resetpassword":
            self.record("password", command[-1], (env or {}).get("OC_PASS"))
            if self.rejections:
                self.rejections -= 1
                return 1, "Password needs to be at least 10 characters long.\n"
            return 0, "Successfully reset password\n"
        if command[0] == "setupchecks":
            return 1, json.dumps({"system": self.setup_errors})
        if command[0] == "config:app:get":
            return 0, "1764000000\n"
        return 0, ""


class FakeRun:
    def __init__(self, host: FakeHost) -> None:
        self.host = host

    def capture(self, args, sudo=False, input=None, timeout=None):
        if args[:3] == ["podman", "unshare", "stat"]:
            return "1000"
        if args[:3] == ["podman", "network", "inspect"]:
            return "10.89.0.0/24 "
        if args[:3] == ["podman", "unshare", "find"]:
            return ""
        return ""

    def cmd(self, args, **_):
        self.host.record("cmd", *args[:3])

    def succeeds(self, args, **_):
        return False


class NextcloudTest(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.home = Path(temp.name)
        patch = mock.patch.dict(os.environ, {"HOME": str(self.home)})
        patch.start()
        self.addCleanup(patch.stop)
        ui.set_app("nextcloud")
        config.home().mkdir()
        (config.home() / "astroverso.env").write_text("DOMAIN=casa.com\n")
        self.host = FakeHost()
        for patch in (
            mock.patch.object(nextcloud, "container", self.host),
            mock.patch.object(app, "container", self.host),
            mock.patch.object(app.accounts, "container", self.host),
            mock.patch.object(nextcloud, "run", FakeRun(self.host)),
            mock.patch.object(nextcloud, "DEFAULT_FILES", self.home / "Nextcloud"),
            mock.patch.object(nextcloud.time, "sleep"),
            mock.patch.object(__import__("kit.disks").disks, "mounts", return_value=[]),
            mock.patch.object(app.accounts, "units", mock.Mock(active=mock.Mock(return_value=False))),
            mock.patch.object(__import__("kit.backup").backup, "units", mock.Mock(active=mock.Mock(return_value=False))),
            mock.patch.object(app.watch, "change", side_effect=lambda *a, **k: app.changes.Change(
                "watch", a[1], a[2], lambda: False, lambda: self.host.record("watch_on"), lambda: self.host.record("watch_off"))),
        ):
            patch.start()
            self.addCleanup(patch.stop)

    def test_fresh_install(self) -> None:
        keys = [b"\n", b"\n", b"curta\n", b"curta\n", b"\r", b"\n", b"Senha-boa-e-longa-2026\n", b"Senha-boa-e-longa-2026\n", b"\n", b"\n", b"\n", b"\n"]
        outcome = run_in_pty(lambda: (app.install(reuse=False), self.host.calls)[1], keys, columns=160)
        self.assertEqual(outcome.code, 0, outcome.screen)
        calls = [tuple(call) for call in outcome.result]
        self.assertEqual([call[1] for call in calls if call[0] == "start"], [nextcloud.DB, nextcloud.REDIS, nextcloud.NAME, nextcloud.CRON])
        self.assertIn(("start", nextcloud.NAME, 1500), calls)
        self.assertEqual([call for call in calls if call[0] == "password"], [
            ("password", "astroverso", "curta"), ("password", "astroverso", "Senha-boa-e-longa-2026")])
        self.assertIn(("exec", "config:system:set", "trusted_proxies", "0", "--value", "10.89.0.0/24"), calls)
        self.assertIn(("exec", "config:system:set", "overwrite.cli.url", "--value", "https://nextcloud.casa.com"), calls)
        self.assertIn(("exec", "background:cron"), calls)
        self.assertIn(("exec", "maintenance:repair", "--include-expensive"), calls)
        self.assertIn(("cmd", "podman", "unshare", "chown"), calls)
        self.assertIn(("watch_on",), calls)
        self.assertIn("o Nextcloud recusou a senha: Password needs to be at least 10 characters long.", outcome.screen)
        self.assertNotIn("Senha-boa", outcome.screen)
        self.assertEqual(json.loads((routes.folder() / "nextcloud.json").read_text()),
                         [{"host": "nextcloud.casa.com", "target": "http://astroverso-nextcloud:80"}])
        self.assertEqual(config.load("nextcloud")["FILES"], str(self.home / "Nextcloud"))
        self.assertIn("ServerName https://nextcloud.casa.com:443", nextcloud.site_file().read_text())
        self.assertIn("${APACHE_LOG_DIR}", nextcloud.site_file().read_text())
        self.assertEqual((nextcloud.secrets_folder() / "db_password").stat().st_mode & 0o777, 0o644)

    def test_reinstall_asks_nothing(self) -> None:
        config.save("nextcloud", {"HOST": "nextcloud.casa.com", "ADMIN_USER": "dono", "FILES": str(self.home / "Nextcloud"), "CHANGE_WATCH": "yes", "CHANGE_MAILBOXES": "yes", "CHANGE_BACKUP": "yes", "CHANGE_BACKUP_FILES": "yes"})
        (nextcloud.html() / "config").mkdir(parents=True)
        (nextcloud.html() / "config" / "config.php").write_text("<?php")
        outcome = run_in_pty(lambda: (app.install(reuse=True), self.host.calls)[1], [], columns=160)
        self.assertEqual(outcome.code, 0, outcome.screen)
        self.assertFalse(any(call[0] == "password" for call in outcome.result))
        self.assertNotIn(["exec", "maintenance:repair", "--include-expensive"], outcome.result)
        self.assertIn("https://nextcloud.casa.com (usuário dono)", outcome.screen)

    def test_specs(self) -> None:
        db, redis, main, cron = nextcloud.specs()
        self.assertEqual(main.requires, [nextcloud.DB, nextcloud.REDIS])
        self.assertEqual((cron.entrypoint, cron.stop_signal, cron.requires), ("/cron.sh", "SIGTERM", [nextcloud.NAME]))
        self.assertIn('Exec=valkey-server --save "" --appendonly no', container.render(redis))
        self.assertIn("HealthStartPeriod=15m", container.render(main))
        self.assertTrue(all(volume.options == "z" or "z" in volume.options for volume in main.volumes))

    def test_remove_keeps_files_by_default(self) -> None:
        config.save("nextcloud", {"FILES": str(self.home / "Nextcloud")})
        (self.home / "Nextcloud").mkdir()
        with mock.patch.object(sys, "stdout", io.StringIO()):
            routes.publish("nextcloud", [routes.Route("nextcloud.casa.com", "http://astroverso-nextcloud:80")])
        outcome = run_in_pty(lambda: (app.remove(), self.host.calls)[1], [b"\n"], columns=160)
        self.assertEqual(outcome.code, 0, outcome.screen)
        calls = [tuple(call) for call in outcome.result]
        self.assertEqual([call[1] for call in calls if call[0] == "remove"], [nextcloud.CRON, nextcloud.NAME, nextcloud.REDIS, nextcloud.DB])
        self.assertEqual([call[1] for call in calls if call[0] == "remove_image"], [nextcloud.DB_IMAGE, nextcloud.REDIS_IMAGE, nextcloud.IMAGE])
        self.assertIn("a pasta dos arquivos ficou", outcome.screen)
        self.assertTrue((self.home / "Nextcloud").exists())
        self.assertFalse((routes.folder() / "nextcloud.json").exists())

    def test_collect(self) -> None:
        self.assertEqual(list(app.collect({})), ["containers"])
        self.host.running = {spec.name for spec in nextcloud.specs()}
        self.host.maintenance = True
        self.host.setup_errors = {"Cron": {"severity": "error", "description": "Cron parado"}, "Ok": {"severity": "success"}}
        found = app.collect({})
        self.assertEqual(sorted(found), ["check:Cron", "maintenance"])
        self.assertEqual(found["check:Cron"].text, "Cron parado")

    def test_validate_folder(self) -> None:
        with self.assertRaises(ValueError):
            nextcloud.validate_folder("relativa")
        with self.assertRaises(ValueError):
            nextcloud.validate_folder(str(self.home))
        with self.assertRaises(ValueError):
            nextcloud.validate_folder(str(config.home() / "x"))
        self.assertEqual(nextcloud.validate_folder(str(self.home / "Arquivos")), str(self.home / "Arquivos"))

    def test_accounts_sync(self) -> None:
        from kit import mailboxes
        secret = self.home / "senha"
        secret.write_text("segredo-imap")
        with mock.patch.object(sys, "stdout", io.StringIO()):
            mailboxes.publish("mail", [mailboxes.Mailbox("inbox", "inbox@casa.com", "astroverso-mail", 31143, "inbox", str(secret), 31587)])
        calls: list[tuple] = []
        exported = [{"id": 7, "email": "velha@casa.com", "name": "Astroverso Velha"}, {"id": 8, "email": "eu@gmail.com", "name": "Pessoal"}]

        def occ_output(*args, env=None):
            calls.append(args)
            if args[0] == "app:list":
                return 0, json.dumps({"enabled": {}, "disabled": {}})
            if args[0] == "mail:account:export":
                return 0, json.dumps(exported)
            return 0, ""

        def exec_output(name, args, user="", env=None, input=None, timeout=None):
            calls.append(("php", env, input))
            return 0, ""

        self.host.running.add(nextcloud.NAME)
        with mock.patch.object(nextcloud, "occ_output", side_effect=occ_output), \
                mock.patch.object(self.host, "exec_output", side_effect=exec_output), mock.patch.object(sys, "stdout", io.StringIO()):
            app.accounts.sync()
        self.assertIn(("app:install", "mail"), calls)
        php = next(call for call in calls if call[0] == "php")
        self.assertEqual(php[1], {"ASTROVERSO_SECRET": "segredo-imap"})
        self.assertIn('json_decode(\'["occ", "mail:account:create", "astroverso", "Astroverso Inbox", "inbox@casa.com"', php[2])
        self.assertEqual(app.accounts._literal("a'b\\c"), "'a\\'b\\\\c'")
        self.assertNotIn("segredo-imap", php[2])
        self.assertIn(("mail:account:delete", "7"), calls)
        self.assertNotIn(("mail:account:delete", "8"), calls)

    def test_actions(self) -> None:
        self.assertEqual([(a.id, a.remote) for a in app.actions()],
                         [("summary", True), ("changes", False), ("password", False), ("repair", True), ("mailboxes", True), ("watch", True), ("backup-now", True), ("restore-version", False),
                          ("backup-files", True), ("restore-files", False)])
        self.assertEqual([item.id for item in app.items()][-2:], ["backup", "backup-files"])

    def test_backup_files(self) -> None:
        with mock.patch.object(app.kit_backup, "run_data", return_value=True) as run_data, \
                mock.patch.object(app.kit_backup, "targets", return_value=["x"]):
            self.assertTrue(app.backup_files())
        args, kwargs = run_data.call_args
        self.assertEqual(args, ("nextcloud", "arquivos", nextcloud.files(), ["x"], "backup-files"))
        self.assertEqual((kwargs["unshare"], kwargs["missing"], kwargs["exclude"]), (True, [], ("appdata_*/preview",)))


if __name__ == "__main__":
    unittest.main()
