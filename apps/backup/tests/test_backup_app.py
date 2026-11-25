import io
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "packages"))

from kit import backup as kit_backup
from kit import config, container, routes, ui
from kit.testing import run_in_pty
from manager.apps import load

APP = load(ROOT / "apps" / "backup")
assert APP.module is not None, APP.problem
app = APP.module
server = app.server


class FakeContainer:
    Container = container.Container
    Volume = container.Volume

    def __init__(self) -> None:
        self.calls: list[tuple] = []
        self.running = False

    def prepare(self):
        self.calls.append(("prepare",))

    def start(self, spec, timeout=180):
        self.calls.append(("start", spec.name, tuple(spec.command)))
        self.running = True

    def restart(self, spec, timeout=180):
        self.calls.append(("restart", spec.name))

    def active(self, name):
        return self.running

    def remove(self, name, image=None):
        self.calls.append(("remove", name))


class FakeRun:
    def __init__(self, snapshots: dict[str, list[dict]]) -> None:
        self.snapshots = snapshots

    def capture(self, args, sudo=False, input=None, timeout=None):
        return "$apr1$abc$hash" if args[:2] == ["openssl", "passwd"] else ""

    def output(self, args, timeout=None, env=None, input=None):
        name = Path((env or {}).get("RESTIC_REPOSITORY", "")).name
        if args[:2] == ["restic", "snapshots"]:
            return 0, json.dumps(self.snapshots.get(name, []))
        return 0, ""


def snapshot(app_name: str, hours: float) -> dict:
    moment = datetime.now(timezone.utc) - timedelta(hours=hours)
    return {"time": moment.isoformat().replace("+00:00", "Z"), "tags": ["astroverso", f"app:{app_name}"]}


class BackupAppTest(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.home = Path(temp.name)
        patch = mock.patch.dict(os.environ, {"HOME": str(self.home)})
        patch.start()
        self.addCleanup(patch.stop)
        ui.set_app("backup")
        config.home().mkdir()
        (config.home() / "astroverso.env").write_text("DOMAIN=casa.com\n")
        self.box = FakeContainer()
        self.snapshots: dict[str, list[dict]] = {}
        for patch in (
            mock.patch.object(server, "container", self.box),
            mock.patch.object(app, "container", self.box),
            mock.patch.object(server, "run", FakeRun(self.snapshots)),
            mock.patch.object(server, "DEFAULT_REPOS", self.home / "Backups"),
            mock.patch.object(app.distro, "install"),
            mock.patch.object(app.net, "hostname", return_value="servidor"),
            mock.patch.object(kit_backup, "ensure_repository", return_value=""),
            mock.patch.object(kit_backup, "units", mock.Mock(active=mock.Mock(return_value=False))),
            mock.patch.object(server, "units", mock.Mock(active=mock.Mock(return_value=False))),
            mock.patch.object(app.watch, "change", side_effect=lambda *a, **k: app.changes.Change("watch", a[1], a[2], lambda: False, lambda: None, lambda: None)),
        ):
            patch.start()
            self.addCleanup(patch.stop)

    def test_server_install(self) -> None:
        keys = [b"\r", b"\n", b"\n", b"\n", b"\n", b"\n", b"\n"]
        outcome = run_in_pty(lambda: (app.install(reuse=False), self.box.calls)[1], keys, columns=200)
        self.assertEqual(outcome.code, 0, outcome.screen)
        calls = [tuple(call) for call in outcome.result]
        start = next(call for call in calls if call[0] == "start")
        self.assertIn("--append-only", start[2])
        self.assertIn("--private-repos", start[2])
        values = config.load("backup")
        self.assertEqual((values["MODE"], values["KEEP_DAILY"], values["KEEP_MONTHLY"]), ("server", "30", "12"))
        local = server.clients()["servidor"]
        self.assertEqual(kit_backup.settings(), {"BACKUP_URL": "https://backup.casa.com", "BACKUP_USER": "servidor",
                                                 "BACKUP_PASSWORD": local["PASSWORD"], "BACKUP_REPO_PASSWORD": local["REPO_PASSWORD"]})
        self.assertEqual((server.clients_folder() / "servidor.env").stat().st_mode & 0o777, 0o600)
        self.assertEqual(server.htpasswd().read_text(), "servidor:$apr1$abc$hash\n")
        self.assertEqual(json.loads((routes.folder() / "backup.json").read_text()), [{"host": "backup.casa.com", "target": "http://astroverso-backup:8080"}])
        self.assertIn("docs/senhas.md", outcome.screen)
        self.assertIn(f"senha do repositório: {local['REPO_PASSWORD']}", outcome.screen)

    def test_client_install(self) -> None:
        keys = [b"\x1b[B", b"\r", b"\n", b"\n", b"acesso\n", b"repo\n", b"\n"]
        outcome = run_in_pty(lambda: app.install(reuse=False), keys, columns=200)
        self.assertEqual(outcome.code, 0, outcome.screen)
        self.assertEqual(kit_backup.settings(), {"BACKUP_URL": "https://backup.casa.com", "BACKUP_USER": "servidor",
                                                 "BACKUP_PASSWORD": "acesso", "BACKUP_REPO_PASSWORD": "repo"})
        self.assertNotIn("repo\n", outcome.screen)

    def test_add_machine(self) -> None:
        config.save("backup", {"MODE": "server", "REPOS": str(self.home / "Backups")})
        with mock.patch.object(sys, "stdout", io.StringIO()):
            server.add("servidor")
        self.box.running = True
        outcome = run_in_pty(lambda: (app.add_machine(), self.box.calls)[1], [b"servidor\n", b"notebook\n"], columns=200)
        self.assertEqual(outcome.code, 0, outcome.screen)
        self.assertIn("a máquina servidor já está cadastrada", outcome.screen)
        self.assertEqual(sorted(server.clients()), ["notebook", "servidor"])
        self.assertIn(["restart", server.NAME], outcome.result)
        self.assertIn("usuário: notebook", outcome.screen)

    def test_collect(self) -> None:
        config.save("backup", {"MODE": "server", "REPOS": str(self.home / "Backups")})
        with mock.patch.object(sys, "stdout", io.StringIO()):
            server.add("servidor")
            server.add("notebook")
            server.add("novo")
        for name in ("servidor", "notebook", "novo"):
            (server.repos() / name).mkdir(parents=True)
        (server.repos() / "servidor" / "config").write_text("x")
        (server.repos() / "notebook" / "config").write_text("x")
        self.snapshots["servidor"] = [snapshot("nextcloud", 2), snapshot("network", 50), snapshot("antigo", 24 * 30)]
        self.snapshots["notebook"] = [snapshot("system", 40)]
        self.assertEqual(list(app.collect({})), ["server"])
        self.box.running = True
        found = app.collect({})
        self.assertEqual(sorted(found), ["app:servidor:network", "machine:notebook"])
        self.assertEqual(found["machine:notebook"].level, "erro")

    def test_actions(self) -> None:
        config.save("backup", {"MODE": "client"})
        self.assertEqual([a.id for a in app.actions()], ["summary", "changes", "backup-now", "restore-version"])
        config.save("backup", {"MODE": "server"})
        self.assertIn("add-machine", [a.id for a in app.actions()])


if __name__ == "__main__":
    unittest.main()
