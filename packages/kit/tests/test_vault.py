import base64
import io
import os
import shutil
import sys
import tarfile
import tempfile
import threading
import unittest
import urllib.parse
from datetime import date, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

from kit import config, ui, vault
from kit.testing import run_in_pty

PREFIX = "/remote.php/dav/files/dono"
REAL_PACK, REAL_UNPACK = vault.pack, vault.unpack


class FakeDav(BaseHTTPRequestHandler):
    root: Path
    token = "Basic " + base64.b64encode(b"dono:app").decode()

    def log_message(self, *args: object) -> None:
        pass

    def _path(self) -> Path | None:
        path = urllib.parse.unquote(urllib.parse.urlparse(self.path).path)
        if not path.startswith(PREFIX):
            return None
        return self.root / path[len(PREFIX):].strip("/")

    def _reply(self, code: int, body: bytes = b"") -> None:
        self.send_response(code)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _auth(self) -> Path | None:
        self.rfile.read(int(self.headers.get("Content-Length") or 0)) if self.command != "PUT" else None
        if self.headers.get("Authorization") != self.token:
            self._reply(401)
            return None
        target = self._path()
        if target is None:
            self._reply(404)
        return target

    def do_PROPFIND(self) -> None:
        target = self._auth()
        if target is None:
            return
        if not target.exists():
            return self._reply(404)
        own = urllib.parse.urlparse(self.path).path.rstrip("/")
        items = [own] + [f"{own}/{urllib.parse.quote(child.name)}" for child in sorted(target.iterdir())] if target.is_dir() else [own]
        body = "".join(f"<d:response><d:href>{href}</d:href></d:response>" for href in items)
        self._reply(207, f'<?xml version="1.0"?><d:multistatus xmlns:d="DAV:">{body}</d:multistatus>'.encode())

    def do_MKCOL(self) -> None:
        target = self._auth()
        if target is None:
            return
        if target.exists():
            return self._reply(405)
        if not target.parent.exists():
            return self._reply(409)
        target.mkdir()
        self._reply(201)

    def do_PUT(self) -> None:
        data = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        target = self._auth()
        if target is None:
            return
        if not target.parent.is_dir():
            return self._reply(409)
        target.write_bytes(data)
        self._reply(201)

    def do_GET(self) -> None:
        target = self._auth()
        if target is None:
            return
        self._reply(200, target.read_bytes()) if target.is_file() else self._reply(404)

    def do_DELETE(self) -> None:
        target = self._auth()
        if target is None:
            return
        if not target.exists():
            return self._reply(404)
        shutil.rmtree(target) if target.is_dir() else target.unlink()
        self._reply(204)


def fake_pack(folder: Path, target: Path, key: str) -> str:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as archive:
        archive.add(folder, arcname=".")
    target.write_bytes(key.encode() + b"\n" + buffer.getvalue())
    return ""


def fake_unpack(source: Path, target: Path, key: str) -> str:
    head, _, body = source.read_bytes().partition(b"\n")
    if head.decode() != key:
        return "a senha dos backups não abriu o arquivo"
    with tarfile.open(fileobj=io.BytesIO(body)) as archive:
        archive.extractall(target, filter="data")
    return ""


class VaultTest(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.home = Path(temp.name)
        self.cloud = self.home / "nuvem"
        self.cloud.mkdir()
        handler = type("Handler", (FakeDav,), {"root": self.cloud})
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        ui.set_app("teste")
        self.sent: list[tuple] = []
        for patch in (
            mock.patch.dict(os.environ, {"HOME": temp.name}),
            mock.patch.object(vault, "pack", fake_pack),
            mock.patch.object(vault, "unpack", fake_unpack),
            mock.patch.object(vault, "_clean", side_effect=lambda folder: shutil.rmtree(folder, ignore_errors=True)),
            mock.patch.object(vault.net, "hostname", return_value="servidor"),
            mock.patch.object(vault.discord, "notify", side_effect=lambda *a, **k: self.sent.append((a, k)) or True),
        ):
            patch.start()
            self.addCleanup(patch.stop)

    def link(self, password: str = "app") -> None:
        vault.save(self.url + "/", "dono", password, "Backups/", "chave")
        config.state("nuvem")

    def save_config(self, text: str) -> None:
        (config.state("nuvem") / "config.txt").write_text(text)

    def backup(self, folder: Path) -> None:
        shutil.copy2(config.state("nuvem") / "config.txt", folder / "config.txt")

    def test_not_configured(self) -> None:
        with mock.patch.object(sys, "stdout", io.StringIO()):
            self.assertFalse(vault.run_backup("nuvem", self.backup))
        self.assertFalse(vault.configured())

    def test_clean_folder(self) -> None:
        self.assertEqual(vault.clean_folder(" Backups/casa/ "), "/Backups/casa")
        for bad in ("", "/", "a/../b"):
            with self.assertRaises(ValueError):
                vault.clean_folder(bad)

    def test_verify(self) -> None:
        values = dict(zip(vault.KEYS, (self.url, "dono", "app", "/Backups/casa", "-")))
        self.assertEqual(vault.verify(values), "")
        self.assertTrue((self.cloud / "Backups" / "casa").is_dir())
        values["VAULT_PASSWORD"] = "errada"
        self.assertEqual(vault.verify(values), "o Nextcloud recusou o usuário ou a senha de app")
        values["VAULT_URL"] = "http://127.0.0.1:1"
        self.assertIn("não respondeu", vault.verify(values))

    def test_backup_and_restore(self) -> None:
        self.link()
        self.assertEqual(vault.settings()["VAULT_FOLDER"], "/Backups")
        self.assertEqual(vault.settings_file().stat().st_mode & 0o777, 0o600)
        self.save_config("primeira")
        with mock.patch.object(sys, "stdout", io.StringIO()) as out:
            self.assertTrue(vault.run_backup("nuvem", self.backup))
        today = date.today().isoformat()
        sent = self.cloud / "Backups" / "servidor" / today / "nuvem.tar.zst.gpg"
        self.assertTrue(sent.is_file())
        self.assertIn("backup do nuvem enviado", out.getvalue())
        self.assertEqual(self.sent[-1][0][:2], ("vault", "info"))
        self.assertFalse((config.home() / ".backups" / "nuvem").exists())
        self.assertEqual(vault.versions("nuvem"), [(today, "nuvem.tar.zst.gpg")])
        self.save_config("segunda")
        outcome = run_in_pty(lambda: (vault.restore("nuvem", self.backup, lambda folder: self.save_config(
            (folder / "config.txt").read_text() + "!")), (config.state("nuvem") / "config.txt").read_text())[1], [b"\r", b"s\n"])
        self.assertEqual(outcome.code, 0, outcome.screen)
        self.assertEqual(outcome.result, "primeira!")
        self.assertTrue((sent.parent / "nuvem-antes-da-restauracao.tar.zst.gpg").is_file())
        self.assertEqual([name for _, name in vault.versions("nuvem")], ["nuvem-antes-da-restauracao.tar.zst.gpg", "nuvem.tar.zst.gpg"])

    def test_wrong_key_and_failures(self) -> None:
        self.link()
        self.save_config("x")
        with mock.patch.object(sys, "stdout", io.StringIO()):
            self.assertTrue(vault.run_backup("nuvem", self.backup))
        values = vault.settings()
        vault.save(values["VAULT_URL"], "dono", "app", "/Backups", "outra")
        outcome = run_in_pty(lambda: vault.restore("nuvem", self.backup, lambda folder: None), [b"\r", b"s\n"])
        self.assertEqual(outcome.code, 1)
        self.assertIn("a senha dos backups não abriu o arquivo", outcome.screen)
        vault.save(values["VAULT_URL"], "dono", "errada", "/Backups", "chave")
        with mock.patch.object(sys, "stdout", io.StringIO()) as out:
            self.assertFalse(vault.run_backup("nuvem", self.backup))
        self.assertIn("recusou o usuário ou a senha de app", out.getvalue())
        self.assertEqual(self.sent[-1][0][:2], ("vault", "erro"))
        self.assertEqual(self.sent[-1][1]["actions"], (("Tentar de novo", "nuvem:backup-now"),))
        with mock.patch.object(sys, "stdout", io.StringIO()) as out:
            self.assertFalse(vault.run_backup("nuvem", lambda folder: ui.fail("sem banco"), notify=False))
        self.assertIn("o backup do app falhou", out.getvalue())

    def test_prune(self) -> None:
        self.link()
        folder = self.cloud / "Backups" / "servidor"
        today = date(2026, 11, 27)
        for day in (today, today - timedelta(days=90), today - timedelta(days=91), today - timedelta(days=400)):
            (folder / day.isoformat()).mkdir(parents=True)
        (folder / "outra-coisa").mkdir()
        self.assertEqual(vault.prune(vault.Dav(), "/Backups/servidor", today), 2)
        self.assertEqual(sorted(path.name for path in folder.iterdir()), ["2026-08-29", "2026-11-27", "outra-coisa"])

    def test_opened(self) -> None:
        self.link()
        self.save_config("parte")
        with mock.patch.object(sys, "stdout", io.StringIO()):
            vault.run_backup("nuvem", self.backup)

        def read() -> str:
            with vault.opened("nuvem") as found:
                assert found is not None
                return (found[0] / "config.txt").read_text() + "|" + found[1]

        outcome = run_in_pty(read, [b"\r"])
        self.assertEqual(outcome.result, "parte|" + date.today().strftime("%d/%m/%Y"))
        self.assertFalse((config.home() / ".backup-restore" / "nuvem").exists())

    def test_change_needs_vault(self) -> None:
        item = vault.change("nuvem")
        self.assertEqual(item.id, "backup")
        with mock.patch.object(vault.units, "install") as install, mock.patch.object(sys, "stdout", io.StringIO()) as out:
            item.apply()
            self.assertIn("instale o app vault", out.getvalue())
            install.assert_not_called()
            self.link()
            item.apply()
            install.assert_called_once()
        texts = vault.units_text("nuvem")
        self.assertIn(f"OnCalendar=*-*-* 01:{vault.minute('nuvem'):02d}:00", texts["astroverso-nuvem-backup.timer"])
        self.assertIn("nuvem action backup-now", texts["astroverso-nuvem-backup.service"])

    @unittest.skipUnless(shutil.which("gpg") and shutil.which("podman") and shutil.which("zstd"), "sem gpg, podman ou zstd")
    def test_real_pack(self) -> None:
        source = self.home / "origem"
        (source / "sub").mkdir(parents=True)
        (source / "sub" / "a.txt").write_text("conteúdo")
        target = self.home / "a.tar.zst.gpg"
        self.assertEqual(REAL_PACK(source, target, "senha"), "")
        self.assertNotIn(b"conte", target.read_bytes())
        back = self.home / "volta"
        back.mkdir()
        self.assertIn("senha dos backups", REAL_UNPACK(target, back, "errada"))
        self.assertEqual(REAL_UNPACK(target, back, "senha"), "")
        self.assertEqual((back / "sub" / "a.txt").read_text(), "conteúdo")


if __name__ == "__main__":
    unittest.main()
