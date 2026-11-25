import io
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "packages"))

from kit import config, ui
from manager.apps import load

APP = load(ROOT / "apps" / "network")
assert APP.module is not None, APP.problem
watch = APP.module.watch


class World:
    def __init__(self) -> None:
        self.ip = "192.168.0.10"
        self.adguard = True
        self.caddy = True
        self.expires: datetime | None = datetime.now(timezone.utc) + timedelta(days=60)
        self.token_problem = ""
        self.connected = True
        self.routes = ["192.168.0.10/32"]
        self.key_expiry = ""
        self.peers = {"a": {"HostName": "pc", "Online": True, "Active": True, "CurAddr": "192.168.0.9:41641", "Relay": "sao"}}
        self.sent: list[tuple] = []
        self.delivered = True

    def status(self) -> dict:
        me = {"PrimaryRoutes": self.routes}
        if self.key_expiry:
            me["KeyExpiry"] = self.key_expiry
        return {"BackendState": "Running" if self.connected else "Stopped", "Self": me, "Peer": self.peers}

    def notify(self, app, level, title, text="", fields=None):
        self.sent.append((level, title))
        return self.delivered


class WatchTest(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        ui.set_app("network")
        self.world = world = World()
        for patch in (
            mock.patch.dict(os.environ, {"HOME": temp.name}),
            mock.patch.object(sys, "stdout", io.StringIO()),
            mock.patch.object(watch.net, "lan_ip", side_effect=lambda: world.ip),
            mock.patch.object(watch.adguard, "installed", side_effect=lambda: world.adguard),
            mock.patch.object(watch.caddy, "installed", side_effect=lambda: world.caddy),
            mock.patch.object(watch.caddy, "expiry", side_effect=lambda domain: world.expires),
            mock.patch.object(watch.caddy, "saved_token", return_value="token"),
            mock.patch.object(watch.caddy, "check_token", side_effect=lambda token, domain: world.token_problem),
            mock.patch.object(watch.tailscale, "status", side_effect=world.status),
            mock.patch.object(watch.discord, "configured", return_value=True),
            mock.patch.object(watch.discord, "notify", side_effect=world.notify),
        ):
            patch.start()
            self.addCleanup(patch.stop)
        config.home().mkdir()
        (config.home() / "astroverso.env").write_text("DOMAIN=casa.com\n")
        config.save("network", {"SERVER_IP": "192.168.0.10"})

    def run_check(self) -> list[tuple]:
        self.world.sent = []
        watch.check()
        return self.world.sent

    def test_healthy_sends_nothing(self) -> None:
        self.assertEqual(watch.collect(), {})
        self.assertEqual(self.run_check(), [])

    def test_problem_once_then_resolved(self) -> None:
        self.world.adguard = False
        self.assertEqual(self.run_check(), [("erro", "AdGuard parado")])
        self.assertEqual(self.run_check(), [])
        self.world.adguard = True
        self.assertEqual(self.run_check(), [("sucesso", "AdGuard parado: resolvido")])
        self.assertEqual(self.run_check(), [])

    def test_failed_delivery_retries(self) -> None:
        self.world.caddy = False
        self.world.delivered = False
        self.assertEqual(self.run_check(), [("erro", "Caddy parado")])
        self.world.delivered = True
        self.assertEqual(self.run_check(), [("erro", "Caddy parado")])
        self.assertEqual(self.run_check(), [])

    def test_certificate_levels(self) -> None:
        self.world.expires = datetime.now(timezone.utc) + timedelta(days=10, hours=1)
        self.assertEqual(self.run_check(), [("aviso", "Cadeado vence em 10 dias")])
        self.world.expires = datetime.now(timezone.utc) + timedelta(days=9, hours=1)
        self.assertEqual(self.run_check(), [])
        self.world.expires = datetime.now(timezone.utc) + timedelta(days=2, hours=1)
        self.assertEqual(self.run_check(), [("erro", "Cadeado vence em 2 dias")])
        self.world.expires = None
        self.assertEqual(self.run_check(), [("erro", "Cadeado inválido ou vencido")])
        problem = watch.collect()["certificate"]
        self.assertIn("docs/cloudflare.md#quando-o-cadeado-demora", problem.text)

    def test_token_ignores_offline(self) -> None:
        self.world.token_problem = "a Cloudflare não respondeu: confira a internet desta máquina"
        self.assertEqual(watch.collect(), {})
        self.world.token_problem = "a Cloudflare não aceitou esse token (copiado pela metade, apagado ou desativado?)"
        self.assertEqual(watch.collect()["token"].level, "erro")

    def test_ip_route_tailscale(self) -> None:
        self.world.ip = "192.168.0.50"
        found = watch.collect()
        self.assertEqual(found["ip"].title, "IP do servidor mudou de 192.168.0.10 para 192.168.0.50")
        self.world.ip = "192.168.0.10"
        self.world.routes = []
        self.assertIn("route", watch.collect())
        self.world.connected = False
        found = watch.collect()
        self.assertEqual(list(found), ["tailscale"])

    def test_key_expiry(self) -> None:
        moment = datetime.now(timezone.utc) + timedelta(days=5, hours=1)
        self.world.key_expiry = moment.isoformat().replace("+00:00", "Z")
        problem = watch.collect()["key"]
        self.assertEqual((problem.level, problem.title), ("aviso", "Chave do servidor no Tailscale vence em 5 dias"))
        self.assertIn("docs/tailscale.md#desligar-a-expiração-da-chave", problem.text)

    def test_relay_only_judged_when_active(self) -> None:
        peer = self.world.peers["a"]
        peer["CurAddr"] = ""
        self.assertEqual(self.run_check(), [("info", "pc está por relay")])
        peer["Active"] = False
        peer["CurAddr"] = "192.168.0.9:41641"
        self.assertEqual(self.run_check(), [])
        peer["Active"] = True
        self.assertEqual(self.run_check(), [("sucesso", "pc está por relay: resolvido")])

    def test_without_discord_only_prints(self) -> None:
        self.world.adguard = False
        with mock.patch.object(watch.discord, "configured", return_value=False):
            self.assertEqual(self.run_check(), [])
        self.assertIn("Discord não configurado", sys.stdout.getvalue())
        self.assertFalse(watch.state_file().exists())

    def test_units(self) -> None:
        units = watch.units_text()
        self.assertIn("OnUnitActiveSec=1h", units[f"{watch.NAME}.timer"])
        self.assertIn(f"ExecStart={ROOT}/astroverso network action watch\n", units[f"{watch.NAME}.service"])


if __name__ == "__main__":
    unittest.main()
