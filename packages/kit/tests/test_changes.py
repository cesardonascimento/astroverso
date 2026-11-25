import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from kit import changes, config, ui
from kit.testing import run_in_pty


def build(state: dict[str, bool], log: list[str]) -> list[changes.Change]:
    def item(name: str, danger: bool = False) -> changes.Change:
        def apply() -> None:
            state[name] = True
            log.append(f"+{name}")

        def undo() -> None:
            state[name] = False
            log.append(f"-{name}")

        return changes.Change(name, f"Ligar {name}", f"Explica {name}.", lambda: state[name], apply, undo, danger)

    return [item("tampa", danger=True), item("tela")]


class ChangesTest(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        patch = mock.patch.dict(os.environ, {"HOME": temp.name})
        patch.start()
        self.addCleanup(patch.stop)
        ui.set_app("teste")

    def test_install_asks_each_with_default_yes(self) -> None:
        def scenario():
            state, log = {"tampa": False, "tela": True}, []
            changes.install("teste", build(state, log), reuse=False)
            return state, log, config.load("teste")

        outcome = run_in_pty(scenario, [b"n\n", b"n\n"])
        self.assertEqual(outcome.code, 0, outcome.screen)
        state, log, saved = outcome.result
        self.assertEqual(log, ["-tela"])
        self.assertEqual(saved, {"CHANGE_TAMPA": "no", "CHANGE_TELA": "no"})
        self.assertIn("Explica tampa.", outcome.screen)
        self.assertIn("Ligar tampa? [S/n]", outcome.screen)
        self.assertIn("pode não funcionar direito", outcome.screen)

        outcome = run_in_pty(scenario, [b"\n", b"s\n"])
        self.assertEqual(outcome.result[1], [])
        self.assertIn("Ligar tampa? [s/N]", outcome.screen)

    def test_reuse_does_not_ask(self) -> None:
        config.save("teste", {"CHANGE_TAMPA": "yes", "CHANGE_TELA": "no"})

        def scenario():
            state, log = {"tampa": False, "tela": True}, []
            changes.install("teste", build(state, log), reuse=True)
            return log

        outcome = run_in_pty(scenario, [])
        self.assertEqual(outcome.result, ["+tampa", "-tela"])
        self.assertNotIn("?", outcome.screen)

    def test_manage_with_danger_confirmation(self) -> None:
        def scenario():
            state, log = {"tampa": True, "tela": False}, []
            changes.manage("teste", build(state, log))
            return log, config.load("teste")

        outcome = run_in_pty(scenario, [b" ", b"\x1b[B", b" ", b"\r", b"n\n"])
        self.assertEqual(outcome.code, 0, outcome.screen)
        log, saved = outcome.result
        self.assertEqual(log, ["+tela"])
        self.assertEqual(saved, {"CHANGE_TELA": "yes"})
        self.assertIn("⚠ Ligar tampa", outcome.screen)
        self.assertIn("é importante para o teste. Desfazer mesmo?", outcome.screen)

        outcome = run_in_pty(scenario, [b" ", b"\r", b"s\n"])
        self.assertEqual(outcome.result[0], ["-tampa"])

    def test_undo_all_and_rows(self) -> None:
        state, log = {"tampa": True, "tela": True}, []
        items = build(state, log)
        rows = changes.rows(items)
        self.assertEqual(rows[0][0], "⚠ Ligar tampa")
        self.assertEqual(rows[1][1].text, "aplicada")
        changes.undo_all(items)
        self.assertEqual(log, ["-tela", "-tampa"])


if __name__ == "__main__":
    unittest.main()
