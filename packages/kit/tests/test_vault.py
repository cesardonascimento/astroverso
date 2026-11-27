import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from kit import config, ui, vault
from kit.testing import run_in_pty

LOCAL = vault.Destination("aaaa1111", "/srv/backup-1")
CLOUD = vault.Destination("bbbb2222", "/srv/dados/sincronizado/Backups", "drive (duas vias)")


class FakeRestic:
    def __init__(self) -> None:
        self.calls: list[tuple] = []
        self.snapshots: dict[str, list[dict]] = {}
        self.fail: set[str] = set()

    def __call__(self, *args, destination, values=None, timeout=None, unshare=False):
        self.calls.append((destination.id, unshare, *args))
        found = self.snapshots.setdefault(destination.id, [])
        if args[0] == "backup":
            if destination.id in self.fail:
                return 1, "Fatal: unable to save snapshot: connection refused\n"
            folder = Path(args[1])
            config_file = folder / "config.txt"
            found.append({"id": f"{destination.id}-{len(found)}", "time": f"2026-11-2{len(found)}T01:10:00Z", "paths": [str(folder)],
                          "tags": [a for i, a in enumerate(args) if i and args[i - 1] == "--tag"],
                          "content": config_file.read_text() if config_file.exists() else ""})
            return 0, ""
        if args[0] == "snapshots":
            return 0, json.dumps(found)
        if args[0] == "restore":
            snapshot = next(item for item in found if item["id"] == args[1].split(":")[0])
            Path(args[3]).mkdir(parents=True, exist_ok=True)
            Path(args[3], "config.txt").write_text(snapshot["content"])
            return 0, ""
        return 0, ""


class BackupTest(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.home = Path(temp.name)
        ui.set_app("teste")
        self.restic = FakeRestic()
        self.sent: list[tuple] = []
        for patch in (
            mock.patch.dict(os.environ, {"HOME": temp.name}),
            mock.patch.object(vault, "restic", self.restic),
            mock.patch.object(vault, "_clean", side_effect=lambda folder: __import__("shutil").rmtree(folder, ignore_errors=True)),
            mock.patch.object(vault.net, "hostname", return_value="servidor"),
            mock.patch.object(vault.discord, "notify", side_effect=lambda *a, **k: self.sent.append((a, k)) or True),
        ):
            patch.start()
            self.addCleanup(patch.stop)

    def link(self) -> None:
        vault.save("https://vault.casa.com/", "servidor", "acesso", "repo")
        vault.save_destinations([LOCAL, CLOUD])
        config.state("nuvem")

    def test_not_configured_does_nothing(self) -> None:
        with mock.patch.object(sys, "stdout", io.StringIO()):
            self.assertFalse(vault.run_backup("nuvem", lambda folder: None))
        self.assertEqual(self.restic.calls, [])

    def test_link_code(self) -> None:
        code = vault.link_code("https://vault.casa.com", "notebook", [LOCAL, CLOUD])
        self.assertTrue(code.startswith(vault.CODE))
        self.assertEqual(vault.read_code(f"  {code[:20]}\n{code[20:]} "), ("https://vault.casa.com", "notebook", [LOCAL, CLOUD]))
        with self.assertRaises(ValueError):
            vault.read_code(code[:-10])
        with self.assertRaises(ValueError):
            vault.read_code("outra-coisa")
        with self.assertRaises(ValueError):
            vault.read_code(vault.link_code("https://vault.casa.com", "notebook", [vault.Destination("../outro", "/x")]))
        with self.assertRaises(ValueError):
            vault.read_code(vault.link_code("http://vault.casa.com", "notebook", [LOCAL]))
        self.assertEqual(vault.tag_text("Fotos, 2025"), "Fotos_ 2025")

    def test_backup_goes_to_chosen_destinations(self) -> None:
        self.link()
        self.assertEqual(vault.settings_file().stat().st_mode & 0o777, 0o600)
        self.assertEqual(vault.destinations_file().stat().st_mode & 0o777, 0o600)
        env = vault.environment(CLOUD)
        self.assertEqual(env["RESTIC_REPOSITORY"], "rest:https://vault.casa.com/servidor/bbbb2222/")
        self.assertEqual((env["RESTIC_REST_PASSWORD"], env["RESTIC_PASSWORD"]), ("acesso", "repo"))
        with mock.patch.object(sys, "stdout", io.StringIO()):
            self.assertFalse(vault.run_backup("nuvem", lambda folder: None))
            self.assertIn("nenhuma pasta de destino escolhida", self.sent[-1][0][3])
            config.save("nuvem", {vault.TARGETS: "bbbb2222,sumiu"})
            self.assertFalse(vault.run_backup("nuvem", lambda folder: (folder / "config.txt").write_text("v1")))
        self.assertIn("a pasta de destino sumiu não existe mais", self.sent[-1][0][3])
        self.assertEqual([call[0] for call in self.restic.calls], ["bbbb2222"])
        call = self.restic.calls[0][2:]
        self.assertEqual([call[i + 1] for i, item in enumerate(call) if item == "--tag"], ["astroverso", "app:nuvem"])
        self.assertFalse(Path(call[1]).exists())
        config.save("nuvem", {vault.TARGETS: "aaaa1111,bbbb2222"})
        with mock.patch.object(sys, "stdout", io.StringIO()):
            self.assertTrue(vault.run_backup("nuvem", lambda folder: (folder / "config.txt").write_text("v2")))
        self.assertEqual(self.sent[-1][0][:3], ("vault", "info", "Backup do nuvem feito em servidor"))
        self.assertIn("/srv/backup-1, /srv/dados/sincronizado/Backups", self.sent[-1][0][3])

    def test_failures_notify_with_retry(self) -> None:
        self.link()
        config.save("nuvem", {vault.TARGETS: "aaaa1111,bbbb2222"})
        with mock.patch.object(sys, "stdout", io.StringIO()):
            self.assertFalse(vault.run_backup("nuvem", lambda folder: (_ for _ in ()).throw(SystemExit(1))))
            self.restic.fail = {"bbbb2222"}
            self.assertFalse(vault.run_backup("nuvem", lambda folder: (folder / "config.txt").write_text("x")))
        self.assertEqual(self.sent[0][0][1], "erro")
        self.assertIn("o backup do app falhou", self.sent[0][0][3])
        self.assertIn("em /srv/dados/sincronizado/Backups: Fatal: unable to save snapshot: connection refused", self.sent[1][0][3])
        self.assertNotIn("backup-1", self.sent[1][0][3])
        self.assertEqual(self.sent[1][1]["actions"], (("Tentar de novo", "nuvem:backup-now"),))

    def test_choose_asks_once(self) -> None:
        with mock.patch.object(sys, "stdout", io.StringIO()):
            self.assertFalse(vault.choose("nuvem", vault.TARGETS, "do nuvem"))
        self.link()
        outcome = run_in_pty(lambda: (vault.choose("nuvem", vault.TARGETS, "do nuvem"), config.load("nuvem").get(vault.TARGETS)),
                             [b"\x1b[B", b" ", b"\r"], columns=160)
        self.assertEqual(outcome.code, 0, outcome.screen)
        self.assertEqual(outcome.result, [True, "aaaa1111,bbbb2222"])
        self.assertIn("☁ drive (duas vias)", outcome.screen)
        self.assertTrue(run_in_pty(lambda: vault.choose("nuvem", vault.TARGETS, "do nuvem"), []).result)

    def test_data_backup(self) -> None:
        self.link()
        folder = self.home / "fotos"
        with mock.patch.object(sys, "stdout", io.StringIO()):
            self.assertFalse(vault.run_data("nuvem", "fotos", folder, [LOCAL], "backup-data"))
            self.assertIn("indisponível", self.sent[-1][0][3])
            folder.mkdir()
            with mock.patch.object(vault.disks, "available", return_value=False):
                self.assertFalse(vault.run_data("nuvem", "fotos", folder, [LOCAL], "backup-data"))
            self.assertTrue(vault.run_data("nuvem", "fotos", folder, [LOCAL], "backup-data", unshare=True))
        destination, unshare, *args = self.restic.calls[-1]
        self.assertEqual((destination, unshare, args[1]), ("aaaa1111", True, str(folder)))
        self.assertIn("dados:fotos", args)
        self.assertEqual(self.sent[-1][0][2], "Backup de fotos (nuvem) feito em servidor")
        self.assertEqual(vault.versions("nuvem", LOCAL), [])
        self.assertEqual(len(vault.versions("nuvem", LOCAL, "fotos")), 1)

    def test_restore_takes_safety_copy(self) -> None:
        self.link()
        config.save("nuvem", {vault.TARGETS: "aaaa1111"})
        with mock.patch.object(sys, "stdout", io.StringIO()):
            vault.run_backup("nuvem", lambda folder: (folder / "config.txt").write_text("antiga"))

        def scenario():
            seen = {}
            vault.restore("nuvem", lambda folder: (folder / "config.txt").write_text("atual"),
                           lambda folder: seen.setdefault("texto", (folder / "config.txt").read_text()))
            return seen, [item["tags"] for item in self.restic.snapshots["aaaa1111"]]

        outcome = run_in_pty(scenario, [b"\r", b"\r", b"s\n"], columns=140)
        self.assertEqual(outcome.code, 0, outcome.screen)
        seen, tags = outcome.result
        self.assertEqual(seen, {"texto": "antiga"})
        self.assertEqual(tags[-1], ["astroverso", "app:nuvem", "antes-da-restauracao"])

    def test_restore_data_into_new_folder(self) -> None:
        self.link()
        folder = self.home / "fotos"
        folder.mkdir()
        with mock.patch.object(sys, "stdout", io.StringIO()):
            vault.run_data("nuvem", "fotos", folder, [CLOUD], "backup-data")
        busy = self.home / "ocupada"
        busy.mkdir()
        (busy / "x").write_text("x")
        target = self.home / "volta"
        outcome = run_in_pty(lambda: (vault.restore_data("nuvem", "fotos"), self.restic.calls)[1], [b"\x1b[B", b"\r", b"\r", f"{busy}\n".encode(), f"{target}\n".encode()], columns=160)
        self.assertEqual(outcome.code, 0, outcome.screen)
        self.assertIn("essa pasta já tem arquivos", outcome.screen)
        self.assertTrue((target / "config.txt").exists())
        restore = next(call for call in outcome.result if call[2] == "restore")
        self.assertEqual(restore[0], "bbbb2222")

    def test_change_and_units(self) -> None:
        change = vault.change("nuvem")
        self.assertEqual(change.id, "backup")
        self.assertIn(f"01:{vault.minute('nuvem'):02d}", change.label)
        text = vault.units_text("nuvem")["astroverso-nuvem-backup.service"]
        self.assertIn(f"ExecStart={vault.COMMAND} nuvem action backup-now", text)
        self.assertNotIn("Nice", text)
        self.assertIn("Persistent=true", vault.units_text("nuvem")["astroverso-nuvem-backup.timer"])
        data = vault.data_change("nuvem", "files", "Backup dos arquivos", "Os arquivos.", "backup-files", "BACKUP_FILES_TO", "dos arquivos")
        self.assertEqual(data.id, "backup-files")
        self.assertIn("02:", data.label)
        texts = vault.units_text("nuvem", "files", "backup-files", 2, "dos arquivos")
        self.assertIn("nuvem action backup-files", texts["astroverso-nuvem-backup-files.service"])

    def test_translated_errors(self) -> None:
        values = dict(zip(vault.KEYS, ("https://b", "u", "p", "r")))
        with mock.patch.object(vault, "restic", return_value=(1, "unexpected HTTP response (401): 401 Unauthorized")):
            self.assertEqual(vault.ensure_repository(values, LOCAL), "o servidor recusou o usuário ou a senha de acesso")
        with mock.patch.object(vault, "restic", return_value=(1, "Fatal: wrong password or no key found")):
            self.assertEqual(vault.ensure_repository(values, LOCAL), "a senha do repositório não confere")


if __name__ == "__main__":
    unittest.main()
