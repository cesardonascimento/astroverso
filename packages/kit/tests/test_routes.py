import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from kit import config, routes, units


class RoutesTest(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.home = Path(temp.name)
        for patch in (mock.patch.dict(os.environ, {"HOME": str(self.home)}), mock.patch.object(sys, "stdout", io.StringIO())):
            patch.start()
            self.addCleanup(patch.stop)

    def test_publish_load_withdraw(self) -> None:
        routes.publish("nuvem", [routes.Route("nuvem.casa.com", "http://astroverso-nuvem:80")])
        path = routes.folder() / "nuvem.json"
        self.assertEqual(json.loads(path.read_text()), [{"host": "nuvem.casa.com", "target": "http://astroverso-nuvem:80"}])
        self.assertEqual(routes.folder().stat().st_mode & 0o777, 0o700)
        self.assertEqual([item.name for item in config.home().iterdir() if item.name.endswith(".tmp")], [])
        self.assertFalse((config.home() / "nuvem").exists())
        (routes.folder() / "ruim.json").write_text("{")
        (routes.folder() / "outro.json").write_text(json.dumps([{"host": "a.casa.com"}, {"host": "b.casa.com", "target": "http://b"}]))
        self.assertEqual(routes.load(), [
            routes.Route("nuvem.casa.com", "http://astroverso-nuvem:80", "nuvem"), routes.Route("b.casa.com", "http://b", "outro"),
        ])
        routes.withdraw("nuvem")
        self.assertFalse(path.exists())

    def test_publish_unchanged_keeps_file(self) -> None:
        routes.publish("nuvem", [routes.Route("nuvem.casa.com", "http://x")])
        before = (routes.folder() / "nuvem.json").stat().st_mtime_ns
        out = io.StringIO()
        with mock.patch.object(sys, "stdout", out):
            routes.publish("nuvem", [routes.Route("nuvem.casa.com", "http://x")])
        self.assertEqual((routes.folder() / "nuvem.json").stat().st_mtime_ns, before)
        self.assertEqual(out.getvalue(), "")

    def test_invalid_app(self) -> None:
        with mock.patch.object(sys, "stderr", io.StringIO()), self.assertRaises(SystemExit):
            routes.publish("../fora", [])


class UnitsTest(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.calls: list[list[str]] = []
        self.running: set[str] = set()
        for patch in (
            mock.patch.dict(os.environ, {"HOME": temp.name}),
            mock.patch.object(sys, "stdout", io.StringIO()),
            mock.patch.object(units.run, "cmd", side_effect=self.cmd),
            mock.patch.object(units.run, "succeeds", side_effect=self.succeeds),
        ):
            patch.start()
            self.addCleanup(patch.stop)

    def cmd(self, args, **_):
        self.calls.append(list(args[2:]))
        if args[2] in ("enable", "restart"):
            self.running.add(args[-1])

    def succeeds(self, args, **_):
        self.calls.append(list(args[2:]))
        return args[2] != "is-active" or args[-1] in self.running

    def test_install_idempotent_and_remove(self) -> None:
        files = {"a.path": "[Path]\n", "a.service": "[Service]\n"}
        units.install(files, ["a.path"])
        self.assertEqual((units.folder() / "a.path").read_text(), "[Path]\n")
        self.assertIn(["daemon-reload"], self.calls)
        self.assertIn(["enable", "--now", "a.path"], self.calls)
        self.calls.clear()
        units.install(files, ["a.path"])
        self.assertEqual(self.calls, [["is-active", "-q", "a.path"]])
        self.calls.clear()
        units.install({**files, "a.path": "[Path]\nX=1\n"}, ["a.path"])
        self.assertEqual(self.calls, [["daemon-reload"], ["is-active", "-q", "a.path"], ["restart", "a.path"]])
        self.calls.clear()
        units.remove(["a.path", "a.service", "b.timer"])
        self.assertFalse((units.folder() / "a.path").exists())
        self.assertIn(["disable", "--now", "a.service"], self.calls)
        self.assertNotIn(["disable", "--now", "b.timer"], self.calls)
        self.assertEqual(self.calls[-1], ["daemon-reload"])


if __name__ == "__main__":
    unittest.main()
