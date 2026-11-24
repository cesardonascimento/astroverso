import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from kit import config, ui, validate
from kit.testing import run_in_pty


class ConfigTest(unittest.TestCase):
    def setUp(self) -> None:
        ui.set_app("teste")
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        for patch in (
            mock.patch.dict(os.environ, {"HOME": str(self.home)}),
            mock.patch.object(sys, "stdout", io.StringIO()),
            mock.patch.object(sys, "stderr", io.StringIO()),
        ):
            patch.start()
            self.addCleanup(patch.stop)
        self.assertEqual(config.home(), self.home / ".astroverso")

    def test_state_permissions(self) -> None:
        folder = config.state("network")
        self.assertEqual(folder, self.home / ".astroverso" / "network")
        self.assertEqual(folder.stat().st_mode & 0o777, 0o700)
        self.assertEqual(folder.parent.stat().st_mode & 0o777, 0o700)

    def test_save_and_load(self) -> None:
        self.assertEqual(config.load("network"), {})
        config.save("network", {"A": "1", "B": "dois=2"})
        config.save("network", {"A": None, "C": "três"})
        self.assertEqual(config.load("network"), {"B": "dois=2", "C": "três"})
        env = config.env_file("network")
        self.assertEqual(env.stat().st_mode & 0o777, 0o600)
        self.assertEqual(env.read_text(), "B=dois=2\nC=três\n")
        self.assertEqual([p.name for p in env.parent.iterdir()], [".env"])

    def test_save_rejects(self) -> None:
        with self.assertRaises(SystemExit):
            config.save("network", {"A": "linha\noutra"})
        with self.assertRaises(SystemExit):
            config.save("network", {"minúscula": "x"})
        with self.assertRaises(SystemExit):
            config.state("../fora")
        self.assertFalse(config.env_file("network").exists())

    def test_reuse(self) -> None:
        self.assertFalse(config.reuse("network"))
        config.save("network", {"A": "1"})
        outcome = run_in_pty(lambda: config.reuse("network"), [b"\n"])
        self.assertEqual(outcome.result, True)
        self.assertIn("usar a configuração já salva? sim", outcome.screen)
        self.assertEqual(run_in_pty(lambda: config.reuse("network"), [b"n\n"]).result, False)

    def test_domain(self) -> None:
        outcome = run_in_pty(config.domain, [b"nada\n", b"https://Casa.COM/\n"])
        self.assertEqual(outcome.result, "casa.com")
        self.assertIn("domínio inválido", outcome.screen)
        self.assertEqual((config.home() / "astroverso.env").read_text(), "DOMAIN=casa.com\n")
        self.assertEqual(run_in_pty(config.domain, []).result, "casa.com")

    def test_purge(self) -> None:
        folder = config.state("network")
        (folder / "data").mkdir()
        (folder / "data" / "x").write_text("x")
        config.state("outro")
        config.purge("network")
        self.assertFalse(folder.exists())
        self.assertTrue((config.home() / "outro").exists())
        config.purge("network")

    def test_purge_refuses(self) -> None:
        target = self.home / "importante"
        target.mkdir()
        config.home().mkdir()
        (config.home() / "atalho").symlink_to(target)
        with self.assertRaises(SystemExit):
            config.purge("atalho")
        with self.assertRaises(SystemExit):
            config.purge("")
        self.assertTrue(target.exists())
        self.assertTrue(config.home().exists())


class ValidateTest(unittest.TestCase):
    def check(self, function, good: dict[str, str], bad: list[str]) -> None:
        for value, expected in good.items():
            self.assertEqual(function(value), expected, value)
        for value in bad:
            with self.assertRaises(ValueError, msg=value):
                function(value)

    def test_domain(self) -> None:
        self.check(validate.domain, {"casa.com": "casa.com", " *.Casa.Com. ": "casa.com", "http://a.b.co/": "a.b.co"},
                   ["casa", "casa..com", "-a.com", "a_b.com", "", "casa.c"])

    def test_ipv4(self) -> None:
        self.check(validate.ipv4, {"192.168.0.10": "192.168.0.10", " 10.0.0.1 ": "10.0.0.1"},
                   ["256.1.1.1", "1.2.3", "a.b.c.d", "01.2.3.4", ""])

    def test_port(self) -> None:
        self.check(validate.port, {"80": "80", "065535": "65535"}, ["0", "65536", "-1", "x", ""])

    def test_name(self) -> None:
        self.check(validate.name, {"Servidor-2": "servidor-2"}, ["2abc", "a_b", "", "a" * 64])

    def test_email(self) -> None:
        self.check(validate.email, {" nome@casa.com ": "nome@casa.com"}, ["nome", "nome@casa", "@casa.com"])


if __name__ == "__main__":
    unittest.main()
