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

from kit import config, routes, ui
from kit.testing import run_in_pty
from manager.apps import load

APP = load(ROOT / "apps" / "cockpit")
assert APP.module is not None, APP.problem
app = APP.module


class FakeDistro:
    def __init__(self, conf: Path) -> None:
        self.conf = conf
        self.calls: list[list[str]] = []
        self.services: set[str] = set()
        self.firewall = {"cockpit", "ssh"}

    def install(self, packages):
        self.calls.append(["install", *packages])

    def service_active(self, name):
        return name in self.services

    def service_enable(self, name):
        self.services.add(name)
        self.calls.append(["enable", name])

    def service_disable(self, name):
        self.services.discard(name)
        self.calls.append(["disable", name])

    def file_put(self, path, content, mode=None):
        self.conf.write_text(content)
        self.calls.append(["put", str(path), oct(mode)])
        return True

    def file_drop(self, path):
        self.conf.unlink(missing_ok=True)
        self.calls.append(["drop", str(path)])
        return True

    def firewall_allowed(self, item):
        return item in self.firewall

    def firewall_close(self, items):
        self.firewall -= set(items)
        self.calls.append(["close", *items])

    def firewall_open(self, items):
        self.firewall |= set(items)
        self.calls.append(["open", *items])


class CockpitTest(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.home = Path(temp.name)
        ui.set_app("cockpit")
        self.distro = FakeDistro(self.home / "cockpit.conf")
        self.user_socket: list[str] = []
        for patch in (
            mock.patch.dict(os.environ, {"HOME": str(self.home)}),
            mock.patch.object(app, "distro", self.distro),
            mock.patch.object(app, "CONF", self.home / "cockpit.conf"),
            mock.patch.object(app.net, "hostname", return_value="servidor"),
            mock.patch.object(app.run, "sudo_prepare"),
            mock.patch.object(app.run, "succeeds", return_value=False),
            mock.patch.object(app.run, "cmd", side_effect=lambda args, **k: self.user_socket.append(" ".join(args))),
            mock.patch.object(__import__("kit.vault").vault, "units", mock.Mock(active=mock.Mock(return_value=False))),
        ):
            patch.start()
            self.addCleanup(patch.stop)
        config.home().mkdir()
        (config.home() / "astroverso.env").write_text("DOMAIN=casa.com\n")

    def test_install(self) -> None:
        keys = [b"\n", b"\n", b"\n", b"\n", b"\n", b"\n"]
        outcome = run_in_pty(lambda: (app.install(reuse=False), self.distro.calls, self.user_socket)[1:], keys, columns=160)
        self.assertEqual(outcome.code, 0, outcome.screen)
        calls, user = outcome.result
        self.assertIn(["install", "cockpit", "cockpit-podman", "cockpit-storaged", "cockpit-files"], calls)
        self.assertIn(["enable", "cockpit.socket"], calls)
        self.assertIn(["close", "cockpit"], calls)
        self.assertIn(["put", str(self.home / "cockpit.conf"), "0o644"], calls)
        self.assertIn("systemctl --user enable --now -q podman.socket", user)
        text = (self.home / "cockpit.conf").read_text()
        self.assertIn("Origins = https://servidor.casa.com wss://servidor.casa.com", text)
        self.assertIn("ProtocolHeader = X-Forwarded-Proto", text)
        self.assertEqual(config.load("cockpit")["HOST"], "servidor.casa.com")
        self.assertEqual(json.loads((routes.folder() / "cockpit.json").read_text()),
                         [{"host": "servidor.casa.com", "target": "http://host.containers.internal:9090"}])
        self.assertIn("https://servidor.casa.com (login com o usuário e a senha do sistema)", outcome.screen)

    def test_changes_undo(self) -> None:
        config.save("cockpit", {"HOST": "painel.casa.com"})
        with mock.patch.object(sys, "stdout", io.StringIO()):
            for change in app.items()[:3]:
                change.apply()
            self.assertTrue(all(change.applied() for change in app.items()[:3]))
            app.changes.undo_all(app.items())
        self.assertFalse((self.home / "cockpit.conf").exists())
        self.assertIn("cockpit", self.distro.firewall)
        self.assertNotIn("cockpit.socket", self.distro.services)

    def test_items_and_actions(self) -> None:
        self.assertEqual([(item.id, item.danger) for item in app.items()],
                         [("socket", True), ("proxy", True), ("firewall", False), ("podman", False), ("backup", False)])
        self.assertEqual([(a.id, a.remote) for a in app.actions()],
                         [("summary", True), ("changes", False), ("backup-now", True), ("restore-version", False)])


if __name__ == "__main__":
    unittest.main()
