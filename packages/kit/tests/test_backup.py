import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from kit import backup, ui
from kit.testing import run_in_pty


class FakeRestic:
    def __init__(self) -> None:
        self.calls: list[tuple] = []
        self.snapshots: list[dict] = []
        self.fail = False

    def __call__(self, *args, values=None, timeout=None):
        self.calls.append(args)
        if args[0] == "backup":
            if self.fail:
                return 1, "Fatal: unable to save snapshot: connection refused\n"
            folder = Path(args[1])
            self.snapshots.append({"id": f"s{len(self.snapshots)}", "time": f"2026-11-2{len(self.snapshots)}T01:10:00Z",
                                   "paths": [str(folder)], "tags": [a for i, a in enumerate(args) if i and args[i - 1] == "--tag"],
                                   "content": (folder / "config.txt").read_text()})
            return 0, ""
        if args[0] == "snapshots":
            return 0, json.dumps(self.snapshots)
        if args[0] == "restore":
            snapshot = next(item for item in self.snapshots if item["id"] == args[1].split(":")[0])
            Path(args[3], "config.txt").write_text(snapshot["content"])
            return 0, ""
        return 0, ""


class BackupTest(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        ui.set_app("teste")
        self.restic = FakeRestic()
        self.sent: list[tuple] = []
        for patch in (
            mock.patch.dict(os.environ, {"HOME": temp.name}),
            mock.patch.object(backup, "restic", self.restic),
            mock.patch.object(backup, "_clean", side_effect=lambda folder: __import__("shutil").rmtree(folder, ignore_errors=True)),
            mock.patch.object(backup.net, "hostname", return_value="servidor"),
            mock.patch.object(backup.discord, "notify", side_effect=lambda *a, **k: self.sent.append((a, k)) or True),
        ):
            patch.start()
            self.addCleanup(patch.stop)

    def test_not_configured_does_nothing(self) -> None:
        with mock.patch.object(sys, "stdout", io.StringIO()):
            self.assertFalse(backup.run_backup("nuvem", lambda folder: None))
        self.assertEqual(self.restic.calls, [])

    def test_backup_and_notify(self) -> None:
        backup.save("https://backup.casa.com/", "servidor", "acesso", "repo")
        self.assertEqual(backup.settings_file().stat().st_mode & 0o777, 0o600)
        env = backup.environment()
        self.assertEqual(env["RESTIC_REPOSITORY"], "rest:https://backup.casa.com/servidor/")
        self.assertEqual((env["RESTIC_REST_PASSWORD"], env["RESTIC_PASSWORD"]), ("acesso", "repo"))
        with mock.patch.object(sys, "stdout", io.StringIO()):
            self.assertTrue(backup.run_backup("nuvem", lambda folder: (folder / "config.txt").write_text("v1")))
        call = self.restic.calls[0]
        self.assertEqual(call[0], "backup")
        self.assertIn("--host", call)
        self.assertEqual([call[i + 1] for i, item in enumerate(call) if item == "--tag"], ["astroverso", "app:nuvem"])
        self.assertFalse(Path(call[1]).exists())
        self.assertEqual(self.sent[0][0][:3], ("backup", "info", "Backup do nuvem feito em servidor"))

    def test_failures_notify_with_retry(self) -> None:
        backup.save("https://backup.casa.com", "servidor", "a", "r")
        with mock.patch.object(sys, "stdout", io.StringIO()):
            self.assertFalse(backup.run_backup("nuvem", lambda folder: (_ for _ in ()).throw(SystemExit(1))))
            self.restic.fail = True
            self.assertFalse(backup.run_backup("nuvem", lambda folder: (folder / "config.txt").write_text("x")))
        self.assertEqual(self.sent[0][0][1], "erro")
        self.assertIn("o backup do app falhou", self.sent[0][0][3])
        self.assertIn("connection refused", self.sent[1][0][3])
        self.assertEqual(self.sent[1][1]["actions"], (("Tentar de novo", "nuvem:backup-now"),))

    def test_restore_takes_safety_copy(self) -> None:
        backup.save("https://backup.casa.com", "servidor", "a", "r")
        with mock.patch.object(sys, "stdout", io.StringIO()):
            backup.run_backup("nuvem", lambda folder: (folder / "config.txt").write_text("antiga"))

        def scenario():
            seen = {}
            backup.restore("nuvem", lambda folder: (folder / "config.txt").write_text("atual"),
                           lambda folder: seen.setdefault("texto", (folder / "config.txt").read_text()))
            return seen, [item["tags"] for item in self.restic.snapshots]

        outcome = run_in_pty(scenario, [b"\r", b"s\n"], columns=140)
        self.assertEqual(outcome.code, 0, outcome.screen)
        seen, tags = outcome.result
        self.assertEqual(seen, {"texto": "antiga"})
        self.assertEqual(tags[-1], ["astroverso", "app:nuvem", "antes-da-restauracao"])

    def test_change_and_units(self) -> None:
        change = backup.change("nuvem")
        self.assertEqual(change.id, "backup")
        self.assertIn(f"01:{backup.minute('nuvem'):02d}", change.label)
        text = backup.units_text("nuvem")["astroverso-nuvem-backup.service"]
        self.assertIn(f"ExecStart={backup.COMMAND} nuvem action backup-now", text)
        self.assertIn("Persistent=true", backup.units_text("nuvem")["astroverso-nuvem-backup.timer"])

    def test_translated_errors(self) -> None:
        values = dict(zip(backup.KEYS, ("https://b", "u", "p", "r")))
        with mock.patch.object(backup, "restic", return_value=(1, "unexpected HTTP response (401): 401 Unauthorized")):
            self.assertEqual(backup.ensure_repository(values), "o servidor recusou o usuário ou a senha de acesso")
        with mock.patch.object(backup, "restic", return_value=(1, "Fatal: wrong password or no key found")):
            self.assertEqual(backup.ensure_repository(values), "a senha do repositório não confere")


if __name__ == "__main__":
    unittest.main()
