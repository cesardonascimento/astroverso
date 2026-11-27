import io
import os
import socket
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "packages"))

from kit import ui
from kit.testing import run_in_pty
from manager.apps import load

APP = load(ROOT / "apps" / "wol")
assert APP.module is not None, APP.problem
app = APP.module


class WolTest(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        ui.set_app("wol")
        for patch in (
            mock.patch.dict(os.environ, {"HOME": temp.name}),
            mock.patch.object(__import__("kit.vault").vault, "units", mock.Mock(active=mock.Mock(return_value=False))),
        ):
            patch.start()
            self.addCleanup(patch.stop)

    def test_mac(self) -> None:
        self.assertEqual(app.mac("60-CF-84-A0-38-04"), "60:cf:84:a0:38:04")
        self.assertEqual(app.mac("60cf84a03804"), "60:cf:84:a0:38:04")
        with self.assertRaises(ValueError):
            app.mac("60:cf:84")

    def test_magic_packet(self) -> None:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as listener:
            listener.bind(("127.0.0.1", 0))
            listener.settimeout(5)
            port = listener.getsockname()[1]
            with mock.patch.object(app, "PORT", port), mock.patch.object(app, "targets", return_value=["127.0.0.1"]):
                app.send("60:cf:84:a0:38:04")
            data = listener.recv(1024)
        self.assertEqual(len(data), 102)
        self.assertEqual(data[:6], b"\xff" * 6)
        self.assertEqual(data[6:], bytes.fromhex("60cf84a03804") * 16)

    def test_add_machine_reads_mac(self) -> None:
        def output(args, timeout=None, env=None, input=None):
            return 0, "192.168.0.20 dev eth0 lladdr 60:cf:84:a0:38:04 REACHABLE\n"

        with mock.patch.object(app.run, "succeeds", return_value=True), mock.patch.object(app.run, "output", side_effect=output):
            outcome = run_in_pty(lambda: (app.add_machine(), app.machines())[1], [b"Jogos\n", b"192.168.0.20\n"], columns=160)
        self.assertEqual(outcome.code, 0, outcome.screen)
        self.assertEqual(outcome.result, [{"name": "jogos", "ip": "192.168.0.20", "mac": "60:cf:84:a0:38:04"}])
        self.assertIn("docs/wake-on-lan.md", outcome.screen)
        self.assertEqual(app.registry_file().stat().st_mode & 0o777, 0o600)

    def test_add_machine_asks_mac_when_off(self) -> None:
        with mock.patch.object(app.run, "succeeds", return_value=False), mock.patch.object(app.run, "output", return_value=(0, "")):
            outcome = run_in_pty(lambda: (app.add_machine(), app.machines())[1], [b"pc\n", b"192.168.0.21\n", b"zz\n", b"60cf84a03805\n"], columns=160)
        self.assertEqual(outcome.code, 0, outcome.screen)
        self.assertIn("MAC inválido", outcome.screen)
        self.assertEqual(outcome.result[0]["mac"], "60:cf:84:a0:38:05")

    def test_wake_waits_for_ping(self) -> None:
        app.save_machines([{"name": "pc", "ip": "192.168.0.21", "mac": "60:cf:84:a0:38:05"}])
        answers = iter([False, False, True])
        sent: list[str] = []
        with mock.patch.object(app, "online", side_effect=lambda ip: next(answers)), mock.patch.object(app, "send", side_effect=sent.append), \
                mock.patch.object(app.time, "sleep"), mock.patch.object(sys, "stdout", io.StringIO()) as out:
            self.assertTrue(app.wake("pc"))
        self.assertEqual(sent, ["60:cf:84:a0:38:05", "60:cf:84:a0:38:05"])
        self.assertIn("pc ligou em", out.getvalue())
        with mock.patch.object(app, "online", return_value=True), mock.patch.object(sys, "stdout", io.StringIO()) as out:
            self.assertTrue(app.wake("pc"))
        self.assertIn("já está ligada", out.getvalue())
        with mock.patch.object(app, "online", return_value=False), mock.patch.object(app, "send"), mock.patch.object(app, "WAIT", 0), \
                mock.patch.object(sys, "stderr", io.StringIO()), mock.patch.object(sys, "stdout", io.StringIO()):
            self.assertFalse(app.wake("pc"))

    def test_actions_per_machine(self) -> None:
        app.save_machines([{"name": "pc", "ip": "1.1.1.1", "mac": "60:cf:84:a0:38:05"}, {"name": "jogos", "ip": "1.1.1.2", "mac": "60:cf:84:a0:38:04"}])
        found = [(a.id, a.remote, a.menu) for a in app.actions()]
        self.assertEqual(found[:6], [("summary", True, True), ("wake", False, True), ("machines", False, True), ("changes", False, True),
                                     ("backup-now", True, True), ("restore-version", False, True)])
        self.assertEqual(found[6:], [("ligar-jogos", True, False), ("ligar-pc", True, False)])
        with mock.patch.object(app, "wake", return_value=False) as wake:
            with self.assertRaises(SystemExit):
                next(a for a in app.actions() if a.id == "ligar-pc").run()
        wake.assert_called_once_with("pc")


if __name__ == "__main__":
    unittest.main()
