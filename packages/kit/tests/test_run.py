import io
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from kit import run, ui

PY = sys.executable


class RunTest(unittest.TestCase):
    def setUp(self) -> None:
        ui.set_app("teste")
        self.out = io.StringIO()
        self.err = io.StringIO()
        patches = [mock.patch.object(sys, "stdout", self.out), mock.patch.object(sys, "stderr", self.err)]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)

    def test_cmd_streams_with_prefix(self) -> None:
        run.cmd([PY, "-c", "import sys; print('um', flush=True); print('dois', file=sys.stderr)"])
        self.assertEqual(self.out.getvalue(), "[teste]       um\n[teste]       dois\n")

    def test_cmd_quiet_shows_only_on_error(self) -> None:
        run.cmd([PY, "-c", "print('nada')"], quiet=True)
        self.assertEqual(self.out.getvalue(), "")
        with self.assertRaises(SystemExit):
            run.cmd([PY, "-c", "print('detalhe'); raise SystemExit(3)"], quiet=True)
        self.assertIn("[teste]       detalhe", self.err.getvalue())
        self.assertIn("comando falhou (código 3)", self.err.getvalue())

    def test_cmd_input(self) -> None:
        run.cmd([PY, "-c", "import sys; print(sys.stdin.read().upper())"], input="segredo")
        self.assertIn("SEGREDO", self.out.getvalue())

    def test_cmd_timeout(self) -> None:
        with self.assertRaises(SystemExit):
            run.cmd([PY, "-c", "import time; time.sleep(5)"], timeout=0.3)
        self.assertIn("o comando passou de 0.3 s", self.err.getvalue())

    def test_missing_command(self) -> None:
        with self.assertRaises(SystemExit):
            run.cmd(["comando-que-nao-existe"])
        with self.assertRaises(SystemExit):
            run.capture(["comando-que-nao-existe"])
        self.assertEqual(self.err.getvalue().count("comando não encontrado: comando-que-nao-existe"), 2)
        self.assertFalse(run.succeeds(["comando-que-nao-existe"]))

    def test_capture(self) -> None:
        self.assertEqual(run.capture([PY, "-c", "print('a'); print('b')"]), "a\nb")
        self.assertEqual(run.capture([PY, "-c", "import sys; print(sys.stdin.read())"], input="x"), "x")
        with self.assertRaises(SystemExit):
            run.capture([PY, "-c", "import sys; print('motivo', file=sys.stderr); raise SystemExit(2)"])
        self.assertIn("[teste]       motivo", self.err.getvalue())
        with self.assertRaises(SystemExit):
            run.capture([PY, "-c", "import time; time.sleep(5)"], timeout=0.3)

    def test_output(self) -> None:
        code, text = run.output([PY, "-c", "import os, sys; print('saída', flush=True); print(os.environ['EXTRA'], file=sys.stderr); sys.exit(3)"],
                                env={"EXTRA": "erro"})
        self.assertEqual((code, text), (3, "saída\nerro\n"))
        self.assertEqual(run.output(["comando-que-nao-existe"])[0], 127)
        code, text = run.output([PY, "-c", "import time; print('antes', flush=True); time.sleep(5)"], timeout=0.5)
        self.assertEqual(code, 124)
        self.assertIn("passou de 0.5 s", text)

    def test_succeeds(self) -> None:
        self.assertTrue(run.succeeds([PY, "-c", "pass"]))
        self.assertFalse(run.succeeds([PY, "-c", "raise SystemExit(1)"]))
        self.assertFalse(run.succeeds([PY, "-c", "import time; time.sleep(5)"], timeout=0.3))
        self.assertEqual(self.out.getvalue(), "")

    def test_sudo_args(self) -> None:
        with mock.patch.object(run, "_has_tty", return_value=True):
            self.assertEqual(run._args(["dnf", "install"], True), ["sudo", "dnf", "install"])
        with mock.patch.object(run, "_has_tty", return_value=False):
            self.assertEqual(run._args(["dnf", "install"], True), ["sudo", "-n", "dnf", "install"])
        self.assertEqual(run._args(["ls"], False), ["ls"])

    def test_sudo_prepare(self) -> None:
        with mock.patch.object(run, "succeeds", return_value=True), mock.patch("subprocess.run") as called:
            run.sudo_prepare("instalar")
        called.assert_not_called()
        with mock.patch.object(run, "succeeds", return_value=False), mock.patch.object(run, "_has_tty", return_value=False):
            with self.assertRaises(SystemExit):
                run.sudo_prepare("instalar")
        self.assertIn("rode num terminal", self.err.getvalue())
        with mock.patch.object(run, "succeeds", return_value=False), mock.patch.object(run, "_has_tty", return_value=True), \
                mock.patch("subprocess.run", return_value=mock.Mock(returncode=1)):
            with self.assertRaises(SystemExit):
                run.sudo_prepare("instalar")
        self.assertIn("permissão de administrador necessária: instalar", self.out.getvalue())
        self.assertIn("a senha do sudo não foi aceita", self.err.getvalue())


if __name__ == "__main__":
    unittest.main()
