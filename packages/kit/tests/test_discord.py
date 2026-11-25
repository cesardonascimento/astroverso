import io
import json
import os
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

from kit import discord


class Handler(BaseHTTPRequestHandler):
    received: list[tuple[str, str, str, dict]] = []

    def log_message(self, *_):
        pass

    def answer(self, code: int, body: dict) -> None:
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        if self.headers.get("Authorization") != "Bearer chave-boa":
            self.answer(401, {"erro": "chave inválida"})
            return
        self.answer(200, {"cliente": "servidor"})

    def do_POST(self) -> None:
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        Handler.received.append(("POST", self.path, self.headers.get("Authorization", ""), body))
        self.answer(200, {"mensagem_id": "1", "canal_id": "2"})


class DiscordTest(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        for patch in (mock.patch.dict(os.environ, {"HOME": temp.name}), mock.patch.object(sys, "stdout", io.StringIO())):
            patch.start()
            self.addCleanup(patch.stop)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        Handler.received = []

    def test_not_configured_is_silent(self) -> None:
        self.assertFalse(discord.configured())
        self.assertFalse(discord.notify("rede", "erro", "teste"))
        self.assertEqual(sys.stdout.getvalue(), "")

    def test_save_and_notify(self) -> None:
        discord.save(self.url + "/", "chave-boa")
        self.assertEqual(discord.settings_file().stat().st_mode & 0o777, 0o600)
        self.assertEqual(discord.settings()["DISCORD_URL"], self.url)
        self.assertTrue(discord.notify("rede", "aviso", "Cadeado vence logo", "faltam 10 dias", {"Validade": "01/12"}))
        self.assertEqual(Handler.received, [("POST", "/v1/mensagens", "Bearer chave-boa", {
            "app": "rede", "nivel": "aviso", "titulo": "Cadeado vence logo", "texto": "faltam 10 dias",
            "campos": {"Validade": "01/12"},
        })])
        discord.forget()
        self.assertFalse(discord.configured())

    def test_whoami(self) -> None:
        self.assertEqual(discord.whoami(self.url, "chave-boa"), "servidor")
        with self.assertRaisesRegex(discord.DiscordError, "401 chave inválida"):
            discord.whoami(self.url, "chave-ruim")

    def test_failure_warns(self) -> None:
        discord.save("http://127.0.0.1:1", "x")
        self.assertFalse(discord.notify("rede", "info", "teste"))
        self.assertIn("aviso não enviado ao Discord", sys.stdout.getvalue())
        with self.assertRaises(ValueError):
            discord.notify("rede", "grave", "teste")


if __name__ == "__main__":
    unittest.main()
