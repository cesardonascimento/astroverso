import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "packages"))

from kit import config, container, mail, mailboxes, ui
from kit.testing import run_in_pty
from manager.apps import load

APP = load(ROOT / "apps" / "mail")
assert APP.module is not None, APP.problem
app = APP.module
mailbox = app.mailbox
cloudflare = app.cloudflare


class FakeCloudflare:
    CloudflareError = cloudflare.CloudflareError
    WORKER = cloudflare.WORKER
    KV_TITLE = cloudflare.KV_TITLE

    def __init__(self) -> None:
        self.calls: list[tuple] = []
        self.mx_records: list[str] = []
        self.kv: dict[str, bytes] = {}
        self.verified: list[dict] = []
        self.extra_workers = ["astroverso-antigo", cloudflare.WORKER]
        self.extra_kv = [{"id": "kv-velho", "title": "astroverso-antigo"}, {"id": "kv1", "title": cloudflare.KV_TITLE}]

    def record(self, *call):
        self.calls.append(call)

    def verify(self, token):
        return token == "token-bom"

    def zone(self, token, domain):
        return "zona1", "conta1", "casa.com"

    def mx(self, token, zone_id, domain):
        return self.mx_records

    def routing_enable(self, token, zone_id, domain, zone_name):
        self.record("routing_enable", domain)
        self.mx_records = ["route1.mx.cloudflare.net"]

    def wait_mx(self, token, zone_id, domain, seconds=120):
        return bool(self.mx_records)

    def kv_ensure(self, token, account, title=cloudflare.KV_TITLE):
        self.record("kv_ensure")
        return "kv1", True

    def worker_publish(self, token, account, kv, allowed, sender, key):
        self.record("worker_publish", kv, allowed, sender, bool(key))

    def workers_dev(self, token, account):
        return "https://astroverso-mail.teste.workers.dev"

    def rule_ensure(self, token, zone_id, address):
        self.record("rule_ensure", address)

    def addresses(self, token, account):
        return self.verified

    def address_add(self, token, account, email):
        self.record("address_add", email)

    def kv_get(self, token, account, kv, key):
        return self.kv.get(key)

    def kv_remove(self, token, account, kv, key):
        self.kv.pop(key, None)

    def kv_keys(self, token, account, kv):
        return list(self.kv)

    def kv_list(self, token, account):
        return self.extra_kv

    def workers(self, token, account):
        return self.extra_workers

    def worker_delete(self, token, account, name):
        self.record("worker_delete", name)

    def kv_delete(self, token, account, kv):
        self.record("kv_delete", kv)

    def rule_delete(self, token, zone_id, address):
        self.record("rule_delete", address)

    def routing_disable(self, token, zone_id, domain, zone_name):
        self.record("routing_disable", domain)


class FakeContainer:
    Container = container.Container
    Volume = container.Volume

    def __init__(self) -> None:
        self.calls: list[tuple] = []
        self.running = False
        self.saved: list[tuple] = []

    def prepare(self):
        self.calls.append(("prepare",))

    def start(self, spec, timeout=180):
        self.calls.append(("start", spec.name))
        self.running = True

    def active(self, name):
        return self.running

    def remove(self, name, image=None):
        self.calls.append(("remove", name))
        self.running = False

    def exec_output(self, name, args, user="", env=None, input=None, timeout=None):
        if args[:2] == ["doveadm", "save"]:
            self.saved.append((tuple(args[2:]), input))
            return 0, ""
        if args[:2] == ["doveadm", "search"]:
            return 0, "id1 1\n" if "Quarentena" in args else ""
        return 0, ""


class MailAppTest(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.home = Path(temp.name)
        patch = mock.patch.dict(os.environ, {"HOME": str(self.home)})
        patch.start()
        self.addCleanup(patch.stop)
        ui.set_app("mail")
        config.home().mkdir()
        (config.home() / "astroverso.env").write_text("DOMAIN=casa.com\n")
        self.cf = FakeCloudflare()
        self.box = FakeContainer()
        fake_run = mock.Mock()
        fake_run.capture.return_value = "$6$hash"
        for patch in (
            mock.patch.object(app, "cloudflare", self.cf),
            mock.patch.object(mailbox, "cloudflare", self.cf),
            mock.patch.object(app, "container", self.box),
            mock.patch.object(mailbox, "container", self.box),
            mock.patch.object(mailbox, "run", fake_run),
            mock.patch.object(app, "units", mock.Mock(active=mock.Mock(return_value=False))),
            mock.patch.object(app.watch, "change", side_effect=lambda *a, **k: app.changes.Change("watch", a[1], a[2], lambda: False, lambda: None, lambda: None)),
            mock.patch.object(mailbox.time, "sleep"),
        ):
            patch.start()
            self.addCleanup(patch.stop)

    def test_server_install(self) -> None:
        self.cf.kv = {"inbox.1764000000000.abc-1": b"Subject: Ola\r\n\r\ncorpo\xe7\r\n", "quarentena.1764000000001.abc-2": b"Subject: spam\r\n\r\nx\r\n", "campainha": b"1"}
        keys = [b"\r", b"\n", b"gmail.com, @Empresa.com.br\n", b"token-ruim\n", b"token-bom\n", b"\n", b"\n", b"n\n"]
        outcome = run_in_pty(lambda: (app.install(reuse=False), self.cf.calls, [list(args) for args, _ in self.box.saved], sorted(self.cf.kv))[1:], keys, columns=200)
        self.assertEqual(outcome.code, 0, outcome.screen)
        calls, saved, left = outcome.result
        values = config.load("mail")
        self.assertEqual((values["MODE"], values["MAIL_ADDRESS"], values["ALLOWED_DOMAINS"]), ("server", "inbox@casa.com", "gmail.com,empresa.com.br"))
        self.assertEqual(values["SEND_URL"], "https://astroverso-mail.teste.workers.dev")
        self.assertIn(["routing_enable", "casa.com"], calls)
        self.assertIn(["worker_publish", "kv1", "gmail.com,empresa.com.br", "inbox@casa.com", True], calls)
        self.assertIn(["rule_ensure", "inbox@casa.com"], calls)
        self.assertEqual(saved, [["-u", "inbox"], ["-u", "inbox", "-m", "Quarentena"]])
        self.assertEqual(left, ["campainha"])
        self.assertEqual(mail.settings()["MAIL_URL"], "https://astroverso-mail.teste.workers.dev")
        [box] = mailboxes.load()
        self.assertEqual((box.address, box.host, box.port, box.user), ("inbox@casa.com", mailbox.NAME, 31143, "inbox"))
        self.assertEqual(mailbox.password_file().stat().st_mode & 0o777, 0o600)
        self.assertIn("a Cloudflare não aceitou esse token", outcome.screen)
        self.assertIn("docs/cloudflare.md#criar-o-token", outcome.screen)
        self.assertIn("docs/encaminhamento.md", outcome.screen)
        self.assertIn("Buscar os e-mails de 5 em 5 minutos, das 08:00 às 20:00? [S/n]", outcome.screen)
        self.assertNotIn("token-bom", outcome.screen)

    def test_existing_mx_stops(self) -> None:
        self.cf.mx_records = ["aspmx.l.google.com"]
        keys = [b"\r", b"\n", b"gmail.com\n", b"token-bom\n"]
        outcome = run_in_pty(lambda: app.install(reuse=False), keys, columns=200)
        self.assertNotEqual(outcome.code, 0)
        self.assertIn("casa.com já recebe e-mail por aspmx.l.google.com", outcome.screen)
        self.assertIn("docs/cloudflare.md#email-routing", outcome.screen)

    def test_scheduled_fetch_uses_doorbell(self) -> None:
        config.save("mail", {"CLOUDFLARE_API_TOKEN": "t", "ACCOUNT_ID": "a", "KV_ID": "k"})
        self.box.running = True
        self.cf.kv = {"inbox.1764000000000.abc-1": b"Subject: x\r\n\r\ny\r\n"}
        with mock.patch.object(sys, "stdout", io.StringIO()):
            self.assertEqual(app.mailbox.fetch(config.load("mail"), force=False), 0)
            self.assertIn("inbox.1764000000000.abc-1", self.cf.kv)
            self.cf.kv["campainha"] = b"1"
            self.assertEqual(app.mailbox.fetch(config.load("mail"), force=False), 1)
        self.assertEqual(self.cf.kv, {})
        self.assertTrue(mailbox.last_fetch()["ok"])

    def test_fetch_failure_recorded(self) -> None:
        config.save("mail", {"CLOUDFLARE_API_TOKEN": "t", "ACCOUNT_ID": "a", "KV_ID": "k"})
        self.cf.kv = {"inbox.1764000000000.abc-1": b"x"}
        with mock.patch.object(sys, "stdout", io.StringIO()), mock.patch.object(sys, "stderr", io.StringIO()), self.assertRaises(SystemExit):
            app.mailbox.fetch(config.load("mail"), force=True)
        self.assertFalse(mailbox.last_fetch()["ok"])
        self.assertIn("parada", mailbox.last_fetch()["error"])
        found = app.collect({})
        self.assertEqual(list(found), ["container"])

    def test_cleanup_lists_only_others(self) -> None:
        config.save("mail", {"CLOUDFLARE_API_TOKEN": "t", "ACCOUNT_ID": "a", "KV_ID": "kv1"})
        outcome = run_in_pty(lambda: (app.cleanup(), self.cf.calls)[1], [b" ", b"\x1b[B", b" ", b"\r", b"s\n"], columns=160)
        self.assertEqual(outcome.code, 0, outcome.screen)
        self.assertIn("Worker: astroverso-antigo", outcome.screen)
        self.assertIn("KV: astroverso-antigo", outcome.screen)
        self.assertNotIn("Worker: astroverso-mail", outcome.screen)
        self.assertEqual(outcome.result, [["worker_delete", "astroverso-antigo"], ["kv_delete", "kv-velho"]])

    def test_client_mode(self) -> None:
        with mock.patch.object(app.mail, "check", side_effect=[mail.MailError("401 chave inválida"), None]):
            keys = [b"\x1b[B", b"\r", b"https://astroverso-mail.x.workers.dev\n", b"ruim\n", b"https://astroverso-mail.x.workers.dev\n", b"boa\n"]
            outcome = run_in_pty(lambda: app.install(reuse=False), keys, columns=200)
        self.assertEqual(outcome.code, 0, outcome.screen)
        self.assertIn("o Worker não aceitou: 401 chave inválida", outcome.screen)
        self.assertEqual(mail.settings(), {"MAIL_URL": "https://astroverso-mail.x.workers.dev", "MAIL_KEY": "boa"})
        self.assertEqual([a.id for a in app.actions()], ["summary", "test"])

    def test_remove_keeps_mail_by_default(self) -> None:
        config.save("mail", {"MODE": "server", "CLOUDFLARE_API_TOKEN": "t", "ACCOUNT_ID": "a", "KV_ID": "kv1", "ZONE_ID": "z",
                             "ZONE_NAME": "casa.com", "MAIL_ADDRESS": "inbox@casa.com"})
        mailbox.vmail().mkdir(parents=True)
        (mailbox.vmail() / "carta").write_text("oi")
        with mock.patch.object(app, "run", mock.Mock()) as fake_run:
            outcome = run_in_pty(lambda: (app.remove(), self.cf.calls)[1], [b"\n"], columns=160)
        self.assertEqual(outcome.code, 0, outcome.screen)
        self.assertIn(["rule_delete", "inbox@casa.com"], outcome.result)
        self.assertIn(["worker_delete", cloudflare.WORKER], outcome.result)
        self.assertIn(["kv_delete", "kv1"], outcome.result)
        self.assertIn(["routing_disable", "casa.com"], outcome.result)
        self.assertIn("os e-mails ficaram em", outcome.screen)
        self.assertTrue((mailbox.vmail() / "carta").exists())

    def test_actions(self) -> None:
        config.save("mail", {"MODE": "server"})
        ids = [(a.id, a.remote, a.menu) for a in app.actions()]
        self.assertIn(("fetch", True, True), ids)
        self.assertIn(("fetch-scheduled", False, False), ids)
        self.assertIn(("reprocess-recent", True, False), ids)


if __name__ == "__main__":
    unittest.main()
