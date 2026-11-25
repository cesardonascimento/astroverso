import base64
import io
import json
import os
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock

from kit import mail, mailboxes


class Handler(BaseHTTPRequestHandler):
    received: list[dict] = []

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
        self.answer(200 if self.headers.get("X-Astroverso-Chave") == "boa" else 401, {"ok": True} if self.headers.get("X-Astroverso-Chave") == "boa" else {"erro": "chave inválida"})

    def do_POST(self) -> None:
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        Handler.received.append(body)
        sent = [item for item in body["para"] if item.endswith("@confirmado.com")]
        errors = [{"para": item, "erro": "destination address is not a verified address"} for item in body["para"] if item not in sent]
        self.answer(200 if sent else 502, {"enviados": sent, "erros": errors})


class MailTest(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        for patch in (mock.patch.dict(os.environ, {"HOME": temp.name}), mock.patch.object(sys, "stdout", io.StringIO())):
            patch.start()
            self.addCleanup(patch.stop)
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        self.url = f"http://127.0.0.1:{server.server_port}"
        Handler.received = []

    def test_not_configured(self) -> None:
        self.assertEqual(mail.send("a@b.com", "oi"), [])
        self.assertEqual(Handler.received, [])

    def test_check(self) -> None:
        mail.check(self.url, "boa")
        with self.assertRaisesRegex(mail.MailError, "401 chave inválida"):
            mail.check(self.url, "ruim")

    def test_send(self) -> None:
        mail.save(self.url + "/", "boa")
        self.assertEqual(mail.settings_file().stat().st_mode & 0o777, 0o600)
        sent = mail.send(["eu@confirmado.com", "outro@x.com"], "Contas", "texto", "<b>html</b>",
                         [mail.Attachment("qr.png", "image/png", b"\x89PNG", "qr")])
        self.assertEqual(sent, ["eu@confirmado.com"])
        body = Handler.received[0]
        self.assertEqual((body["assunto"], body["texto"], body["html"]), ("Contas", "texto", "<b>html</b>"))
        self.assertEqual(body["anexos"], [{"nome": "qr.png", "tipo": "image/png", "base64": base64.b64encode(b"\x89PNG").decode(), "cid": "qr"}])
        self.assertIn("não entregue a outro@x.com", sys.stdout.getvalue())
        self.assertEqual(mail.send("outro@x.com", "Só erro"), [])

    def test_failure(self) -> None:
        mail.save("http://127.0.0.1:1", "x")
        self.assertEqual(mail.send("a@b.com", "oi"), [])
        self.assertIn("e-mail não enviado", sys.stdout.getvalue())

    def test_mailboxes(self) -> None:
        box = mailboxes.Mailbox("inbox", "inbox@casa.com", "astroverso-mail", 31143, "inbox", "/tmp/senha", 31587)
        mailboxes.publish("mail", [box])
        self.assertEqual((mailboxes.folder() / "mail.json").stat().st_mode & 0o777, 0o600)
        loaded = mailboxes.load()
        self.assertEqual(loaded, [mailboxes.Mailbox(**{**box.__dict__, "app": "mail"})])
        mailboxes.withdraw("mail")
        self.assertEqual(mailboxes.load(), [])


if __name__ == "__main__":
    unittest.main()
