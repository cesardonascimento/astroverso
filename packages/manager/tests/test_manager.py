import io
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from kit.testing import run_in_pty
from manager import cli
from manager.apps import ROOT, discover

APP = '''
from pathlib import Path
from kit import ui
from kit.app import Action

STATE = Path({state!r})
DESCRIPTION = "App de teste {name}"


def status():
    return STATE.exists()


def install():
    ui.ok("instalando")
    {install}
    STATE.write_text("ok")


def remove():
    STATE.unlink(missing_ok=True)


def backup(folder):
    (folder / "{name}.txt").write_text(STATE.read_text())


def restore(folder):
    STATE.write_text((folder / "{name}.txt").read_text())


def actions():
    return [Action("ping", "Responder pong", lambda: ui.ok("pong")), Action("oculta", "Ação oculta", lambda: ui.ok("escondida"), menu=False)]
'''


class ManagerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.apps = self.root / "apps"
        self.apps.mkdir()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def app(self, name: str, install: str = "pass", source: str | None = None) -> Path:
        folder = self.apps / name
        folder.mkdir()
        state = self.root / f"{name}.state"
        (folder / "app.py").write_text(source or APP.format(state=str(state), name=name, install=install))
        return state

    def run_cli(self, *args: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(sys, "stdout", out), mock.patch.object(sys, "stderr", err):
            try:
                code = cli.main(list(args), self.apps)
            except SystemExit as exit:
                code = exit.code
        return code, out.getvalue(), err.getvalue()

    def test_discover(self) -> None:
        self.app("bom")
        self.app("quebrado", source="DESCRIPTION = 'x'\ndef status(): return False\n")
        self.app("erro", source="raise RuntimeError('falhou')\n")
        (self.apps / "sem-app").mkdir()
        (self.apps / ".oculto").mkdir()
        apps = {app.name: app for app in discover(self.apps)}
        self.assertEqual(sorted(apps), ["bom", "erro", "quebrado"])
        self.assertIsNone(apps["bom"].problem)
        self.assertEqual(apps["quebrado"].problem, "falta install, remove, backup, restore")
        self.assertIn("falhou", apps["erro"].problem)

    def test_discover_order(self) -> None:
        for name, order in (("alfa", None), ("beta", 20), ("gama", 10), ("delta", None), ("eta", "x")):
            source = APP.format(state=str(self.root / name), name=name, install="pass")
            self.app(name, source=source + (f"\nORDER = {order!r}\n" if order is not None else ""))
        self.assertEqual([app.name for app in discover(self.apps)], ["gama", "beta", "alfa", "delta", "eta"])

    def test_app_with_modules(self) -> None:
        state = self.root / "pacote.state"
        source = APP.format(state=str(state), name="pacote", install="pass").replace(
            "from kit.app import Action", "from kit.app import Action\nfrom . import helper"
        ).replace('    ui.ok("instalando")', "    ui.ok(helper.TEXT)")
        folder = self.apps / "pacote"
        folder.mkdir()
        (folder / "app.py").write_text(source)
        (folder / "helper.py").write_text('TEXT = "veio do helper"\n')
        code, out, _ = self.run_cli("pacote", "install")
        self.assertEqual(code, 0, out)
        self.assertIn("veio do helper", out)

    def test_direct_commands(self) -> None:
        state = self.app("bom")
        self.assertEqual(self.run_cli("bom", "status")[0], 1)
        code, out, _ = self.run_cli("bom", "install")
        self.assertEqual(code, 0)
        self.assertIn("[bom]", out)
        self.assertTrue(state.exists())
        self.assertEqual(self.run_cli("bom", "status")[0], 0)
        self.assertEqual(self.run_cli("bom", "backup", str(self.root))[0], 0)
        state.write_text("mudou")
        self.assertEqual(self.run_cli("bom", "restore", str(self.root))[0], 0)
        self.assertEqual(state.read_text(), "ok")
        code, out, _ = self.run_cli("bom", "action", "ping")
        self.assertEqual((code, "pong" in out), (0, True))
        self.assertEqual(self.run_cli("bom", "action", "nada")[0], 1)
        self.assertIn("escondida", self.run_cli("bom", "action", "oculta")[1])
        self.assertEqual(self.run_cli("bom", "remove")[0], 0)
        self.assertFalse(state.exists())

    def test_direct_errors(self) -> None:
        self.app("falha", install="ui.fail('sem rede')")
        self.app("explode", install="raise RuntimeError('bug')")
        code, _, err = self.run_cli("falha", "install")
        self.assertEqual(code, 1)
        self.assertIn("[falha]     erro: sem rede", err)
        code, _, err = self.run_cli("explode", "install")
        self.assertEqual(code, 1)
        self.assertIn("falha inesperada: bug", err)
        self.assertIn("Traceback", err)
        self.assertEqual(self.run_cli("nenhum", "install")[0], 1)
        self.assertEqual(self.run_cli("falha")[0], 1)
        self.assertEqual(self.run_cli("falha", "status", "extra")[0], 1)

    def test_interactive_without_apps(self) -> None:
        outcome = run_in_pty(lambda: cli.main([], self.apps), [])
        self.assertEqual(outcome.code, 0)
        self.assertIn("nenhum app disponível ainda", outcome.screen)

    def test_interactive_install_manage_remove(self) -> None:
        first = self.app("primeiro")
        second = self.app("segundo", install="ui.fail('sem rede')")
        keys = [
            b"\r", b" ", b"\r",
            b"\x1b[B", b"\r", b"\r", b"\r", b"\x1b[B", b"\x1b[B", b"\r", b"s\n",
            b"\x1b",
        ]
        outcome = run_in_pty(lambda: cli.main([], self.apps), keys)
        screen = outcome.screen
        self.assertEqual(outcome.code, 0, screen)
        self.assertIn("Todos", screen)
        self.assertIn("App de teste primeiro", screen)
        self.assertIn("instalados: primeiro", screen)
        self.assertIn("falharam: segundo", screen)
        self.assertIn("pong", screen)
        self.assertNotIn("Ação oculta", screen)
        self.assertIn("primeiro removido", screen)
        self.assertFalse(first.exists())
        self.assertFalse(second.exists())

    def test_interactive_esc_cancels_install(self) -> None:
        state = self.app("pergunta", install="ui.ask('nome')")
        self.app("zeta")
        keys = [b"\r", b" ", b"\r", b"\x1b", b"\x1b"]
        outcome = run_in_pty(lambda: cli.main([], self.apps), keys)
        screen = outcome.screen
        self.assertEqual(outcome.code, 0, screen)
        self.assertIn("Esc cancela a instalação", screen)
        self.assertIn("instalação do pergunta cancelada", screen)
        self.assertIn("cancelados: pergunta, zeta", screen)
        self.assertIn("O que fazer? Sair", screen)
        self.assertFalse(state.exists())

    def test_interactive_ctrl_c_cancels_action(self) -> None:
        source = APP.format(state=str(self.root / "acao.state"), name="acao", install="pass").replace(
            'lambda: ui.ok("pong")', 'lambda: ui.ask("nome")'
        )
        state = self.app("acao", source=source)
        state.write_text("ok")
        keys = [b"\x1b[B", b"\r", b"\r", b"\r", b"\x03", b"\x1b", b"\x1b", b"\x1b"]
        outcome = run_in_pty(lambda: cli.main([], self.apps), keys)
        self.assertEqual(outcome.code, 0, outcome.screen)
        self.assertIn("ação Responder pong cancelada", outcome.screen)

    def test_direct_esc(self) -> None:
        self.app("pergunta", install="ui.ask('nome')")
        outcome = run_in_pty(lambda: cli.main(["pergunta", "install"], self.apps), [b"\x1b"])
        self.assertEqual(outcome.result, 130, outcome.screen)
        self.assertIn("interrompido", outcome.screen)

    def test_ensure_command(self) -> None:
        home = self.root / "home"
        with mock.patch.object(sys, "stdout", io.StringIO()) as out:
            cli.ensure_command(home)
            cli.ensure_command(home)
        link = home / ".local" / "bin" / "astroverso"
        self.assertEqual(link.resolve(), (ROOT / "astroverso").resolve())
        self.assertEqual(out.getvalue().count("comando astroverso criado"), 1)

    def test_entry_script(self) -> None:
        env = {**os.environ, "HOME": str(self.root)}
        done = subprocess.run([str(ROOT / "astroverso"), "--help"], capture_output=True, text=True, env=env)
        self.assertEqual(done.returncode, 0)
        self.assertIn("[astroverso]", done.stdout)
        self.assertFalse((self.root / ".local").exists())


if __name__ == "__main__":
    unittest.main()
