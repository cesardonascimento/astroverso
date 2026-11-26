import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "packages"))

from kit import config, ui
from kit.testing import run_in_pty
from manager.apps import load

APP = load(ROOT / "apps" / "devenv")
assert APP.module is not None, APP.problem
app = APP.module


class DevenvTest(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.home = Path(temp.name)
        ui.set_app("devenv")
        for patch in (
            mock.patch.dict(os.environ, {"HOME": str(self.home)}),
            mock.patch.object(app, "PROJECTS", self.home / "Projects"),
            mock.patch.object(__import__("kit.backup").backup, "units", mock.Mock(active=mock.Mock(return_value=False))),
        ):
            patch.start()
            self.addCleanup(patch.stop)

    def test_repo_validation_and_folders(self) -> None:
        self.assertEqual(app._repo(" git@github.com:conta/astroverso-devenv.git "), "git@github.com:conta/astroverso-devenv.git")
        self.assertEqual(app._repo("https://github.com/conta/dotfiles"), "https://github.com/conta/dotfiles")
        for bad in ("github.com/conta/x", "git@github.com", "rm -rf /"):
            with self.assertRaises(ValueError):
                app._repo(bad)
        config.save("devenv", {"DEVENV_REPO": "git@github.com:conta/astroverso-devenv.git", "DOTFILES_REPO": "https://github.com/conta/meus-dotfiles"})
        self.assertEqual(app.folder("DEVENV"), self.home / "Projects" / "astroverso-devenv")
        self.assertEqual(app.folder("DOTFILES"), self.home / "Projects" / "meus-dotfiles")

    def test_install_clones_and_runs_both(self) -> None:
        calls: list[list[str]] = []

        def output(args, env=None, timeout=None, input=None):
            calls.append(list(args))
            if args[:2] == ["git", "clone"]:
                target = Path(args[-1])
                (target / ".git").mkdir(parents=True)
                if "devenv" in target.name:
                    (target / "linux").mkdir()
                    (target / "linux" / "install.sh").write_text("#!/bin/sh\n")
            return 0, ""

        def cmd(args, sudo=False, input=None, quiet=False, timeout=None):
            calls.append(["cmd", *args])

        keys = [b"git@github.com:conta/astroverso-devenv.git\n", b"git@github.com:conta/astroverso-dotfiles.git\n", b"\n"]
        with mock.patch.object(app.run, "output", side_effect=output), mock.patch.object(app.run, "cmd", side_effect=cmd), \
                mock.patch.object(app.run, "sudo_prepare"), mock.patch.object(app.run, "succeeds", return_value=True), \
                mock.patch.object(app, "summary"):
            outcome = run_in_pty(lambda: (app.install(reuse=False), calls)[1], keys, columns=160)
        self.assertEqual(outcome.code, 0, outcome.screen)
        runs = [call[1] for call in outcome.result if call[0] == "cmd"]
        self.assertEqual(runs, [str(self.home / "Projects/astroverso-devenv/linux/install.sh"), str(self.home / "Projects/astroverso-dotfiles/install.sh")])
        self.assertEqual([call[1] for call in outcome.result if call[0] == "git"][:2], ["ls-remote", "ls-remote"])
        self.assertIn("ambiente aplicado", outcome.screen)

    def test_no_access_stops_with_hint(self) -> None:
        config.save("devenv", {"DEVENV_REPO": "git@github.com:conta/a.git", "DOTFILES_REPO": "git@github.com:conta/b.git"})
        with mock.patch.object(app.run, "output", return_value=(128, "Permission denied (publickey)")), \
                mock.patch.object(sys, "stdout", io.StringIO()) as out, mock.patch.object(sys, "stderr", io.StringIO()) as err:
            with self.assertRaises(SystemExit):
                app.apply()
        self.assertIn("Chave desta máquina para o GitHub", out.getvalue() + err.getvalue())

    def test_update_problems(self) -> None:
        config.save("devenv", {"DOTFILES_REPO": "git@github.com:conta/b.git"})
        seen: list[dict] = []

        def output(args, env=None, timeout=None, input=None):
            if args[0] == "loginctl":
                return 0, "no\n"
            seen.append(env or {})
            return 128, ""

        with mock.patch.object(app.run, "succeeds", return_value=False), mock.patch.object(app.run, "output", side_effect=output):
            problems = app.update_problems()
        self.assertEqual(len(problems), 3)
        self.assertEqual(seen[0]["SSH_AUTH_SOCK"], "")
        with mock.patch.object(app.run, "succeeds", return_value=True), mock.patch.object(app.run, "output", return_value=(0, "yes\n")):
            self.assertEqual(app.update_problems(), [])

    def test_actions(self) -> None:
        self.assertEqual([(a.id, a.remote) for a in app.actions()],
                         [("summary", True), ("update", False), ("check", True), ("changes", False), ("backup-now", True), ("restore-version", False)])


if __name__ == "__main__":
    unittest.main()
