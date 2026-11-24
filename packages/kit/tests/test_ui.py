import io
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from kit import ui
from kit.testing import ANSI, run_in_pty


class FakeTty(io.StringIO):
    def isatty(self) -> bool:
        return True


def run(code: str, keys: list[bytes], lines: int = 24) -> tuple[object, str]:
    outcome = run_in_pty(lambda: eval(code, {"ui": ui, "check_port": check_port}), keys, lines)
    return outcome.result, outcome.screen


def check_port(value: str) -> str:
    if not value.isdigit() or not 1 <= int(value) <= 65535:
        raise ValueError("porta entre 1 e 65535")
    return value


class LogTest(unittest.TestCase):
    def setUp(self) -> None:
        ui.set_app("teste")

    def test_plain_output_without_terminal(self) -> None:
        out = io.StringIO()
        with mock.patch.object(sys, "stdout", out):
            ui.step("etapa")
            ui.ok("feito")
            ui.warn("cuidado")
            ui.info("texto")
            ui.prefixed("a\nb")
        self.assertEqual(
            out.getvalue(),
            "[teste] ==> etapa\n[teste]     ok: feito\n[teste]     aviso: cuidado\n"
            "[teste]     texto\n[teste]       a\n[teste]       b\n",
        )

    def test_colors_on_terminal(self) -> None:
        out = FakeTty()
        with mock.patch.object(sys, "stdout", out), mock.patch.dict(os.environ, {"COLORTERM": "truecolor"}):
            os.environ.pop("NO_COLOR", None)
            ui.ok("feito")
        self.assertIn("\x1b[", out.getvalue())
        self.assertIn("✔", out.getvalue())

    def test_no_color(self) -> None:
        out = FakeTty()
        with mock.patch.object(sys, "stdout", out), mock.patch.dict(os.environ, {"NO_COLOR": "1"}):
            ui.ok("feito")
        self.assertEqual(out.getvalue(), "[teste]     ok: feito\n")

    def test_error_and_fail(self) -> None:
        err = io.StringIO()
        with mock.patch.object(sys, "stderr", err), self.assertRaises(SystemExit) as raised:
            ui.fail("quebrou")
        self.assertEqual(raised.exception.code, 1)
        self.assertEqual(err.getvalue(), "[teste]     erro: quebrou\n")

    def test_sudo_prompt(self) -> None:
        ui.set_app("outro")
        self.assertIn("[outro]", os.environ["SUDO_PROMPT"])


class PromptTest(unittest.TestCase):
    def test_ask_default(self) -> None:
        result, screen = run('ui.ask("nome", default="padrão")', [b"\n"])
        self.assertEqual(result, "padrão")
        self.assertIn("? nome padrão", screen)

    def test_ask_validator_repeats(self) -> None:
        result, screen = run('ui.ask("porta", validate=check_port)', [b"abc\n", b"80\n"])
        self.assertEqual(result, "80")
        self.assertIn("porta entre 1 e 65535", screen)

    def test_secret_confirmation(self) -> None:
        result, screen = run('ui.secret("senha")', [b"um\n", b"dois\n", b"tres\n", b"tres\n"])
        self.assertEqual(result, "tres")
        self.assertIn("os valores não conferem", screen)
        self.assertNotIn("tres", screen)

    def test_secret_once(self) -> None:
        result, _ = run('ui.secret("chave", confirm=False)', [b"abc\n"])
        self.assertEqual(result, "abc")

    def test_confirm(self) -> None:
        self.assertEqual(run('ui.confirm("seguir?")', [b"talvez\n", b"s\n"])[0], True)
        self.assertEqual(run('ui.confirm("seguir?", default=True)', [b"\n"])[0], True)
        self.assertEqual(run('ui.confirm("seguir?")', [b"\n"])[0], False)

    def test_ask_list(self) -> None:
        result, _ = run('ui.ask_list("item")', [b"a\n", b"b\n", b"\n"])
        self.assertEqual(result, ["a", "b"])

    def test_without_terminal(self) -> None:
        with mock.patch("os.open", side_effect=OSError), mock.patch.object(sys, "stderr", io.StringIO()):
            with self.assertRaises(SystemExit):
                ui.ask("nome")


class MenuTest(unittest.TestCase):
    def test_menu_arrows(self) -> None:
        result, screen = run('ui.menu("O que?", ["a", "b", "c"])', [b"\x1b[B", b"\x1b[B", b"\x1b[A", b"\r"])
        self.assertEqual(result, 1)
        self.assertIn("? O que? b", screen)

    def test_menu_number_and_wrap(self) -> None:
        self.assertEqual(run('ui.menu("O que?", ["a", "b", "c"])', [b"3", b"\r"])[0], 2)
        self.assertEqual(run('ui.menu("O que?", ["a", "b", "c"])', [b"\x1b[A", b"\r"])[0], 2)

    def test_menu_details(self) -> None:
        result, screen = run('ui.menu("Qual?", ["curto", "comprido"], details=["um", "dois"])', [b"\r"])
        self.assertEqual(result, 0)
        self.assertIn("1. curto     um", screen)
        self.assertIn("2. comprido  dois", screen)

    def test_menu_esc_back(self) -> None:
        self.assertEqual(run('ui.menu("O que?", ["a", "Voltar"])', [b"\x1b"])[0], 1)

    def test_menu_esc_ignored_and_unknown_keys(self) -> None:
        self.assertEqual(run('ui.menu("O que?", ["a", "b"])', [b"\x1b", b"\x1b[C", b"\r"])[0], 0)

    def test_menu_scroll(self) -> None:
        items = [f"item {i}" for i in range(30)]
        result, screen = run(f"ui.menu('Muitos', {items!r})", [b"\x1b[F", b"\r"], lines=10)
        self.assertEqual(result, 29)
        self.assertIn("30 de 30", screen)

    def test_checklist(self) -> None:
        result, _ = run('ui.checklist("Quais?", ["a", "b", "c"], selected=[0])', [b"\x1b[B", b" ", b"\r"])
        self.assertEqual(result, [0, 1])

    def test_checklist_all(self) -> None:
        self.assertEqual(run('ui.checklist("Quais?", ["a", "b"], all_option=True)', [b" ", b"\r"])[0], [0, 1])
        self.assertEqual(run('ui.checklist("Quais?", ["a", "b"], selected=[0, 1])', [b"a", b"\r"])[0], [])

    def test_checklist_cancel(self) -> None:
        result, screen = run('ui.checklist("Quais?", ["a"], selected=[0], cancel=True)', [b"\x1b"])
        self.assertIsNone(result)
        self.assertIn("cancelado", screen)

    def test_terminal_restored(self) -> None:
        code = '(ui.menu("O que?", ["a"]), bool(__import__("termios").tcgetattr(0)[3] & __import__("termios").ECHO))[1]'
        self.assertEqual(run(code, [b"\r"])[0], True)


class BannerTest(unittest.TestCase):
    def test_banner_layouts(self) -> None:
        for columns in (140, 90, 40):
            out = FakeTty()
            out.fileno = lambda: 1
            with mock.patch.object(sys, "stdout", out), mock.patch.dict(os.environ, {"COLORTERM": "truecolor"}), \
                    mock.patch("os.get_terminal_size", return_value=os.terminal_size((columns, 40))):
                os.environ.pop("NO_COLOR", None)
                ui.banner()
            text = ANSI.sub("", out.getvalue())
            self.assertTrue(all(len(line) <= columns for line in text.splitlines()), columns)

    def test_banner_silent_without_terminal(self) -> None:
        out = io.StringIO()
        with mock.patch.object(sys, "stdout", out):
            ui.banner()
        self.assertEqual(out.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
