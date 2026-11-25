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

from kit import config, ui
from kit.testing import run_in_pty
from manager.apps import load

APP = load(ROOT / "apps" / "network")
assert APP.module is not None, APP.problem
network = APP.module
tailscale = network.tailscale

PEERS = {
    "a": {"HostName": "celular", "DNSName": "celular.rede.ts.net.", "TailscaleIPs": ["100.1.1.1"], "OS": "iOS",
          "Online": True, "CurAddr": "192.168.0.9:41641", "Relay": "sao"},
    "b": {"HostName": "pc", "DNSName": "pc.rede.ts.net.", "TailscaleIPs": ["100.1.1.2"], "OS": "windows",
          "Online": True, "CurAddr": "", "Relay": "sao"},
    "c": {"HostName": "velho", "DNSName": "velho.rede.ts.net.", "TailscaleIPs": ["100.1.1.3"], "OS": "linux",
          "Online": False, "CurAddr": "", "Relay": ""},
}


class FakeSystem:
    def __init__(self, installed: bool = False, running: bool = False, approve_after: int = 1) -> None:
        self.packages = {"tailscale"} if installed else set()
        self.running = running
        self.prefs = {"AdvertiseRoutes": None, "RouteAll": True, "OperatorUser": ""}
        self.approve_after = approve_after
        self.checks = 0
        self.calls: list[tuple[str, ...]] = []

    def state(self) -> dict:
        approved = self.prefs["AdvertiseRoutes"] == ["192.168.0.10/32"] and self.checks >= self.approve_after
        return {
            "BackendState": "Running" if self.running else "NeedsLogin",
            "CurrentTailnet": {"Name": "minha-rede"},
            "Self": {"DNSName": "servidor.rede.ts.net.", "TailscaleIPs": ["100.9.9.9"],
                     "PrimaryRoutes": ["192.168.0.10/32"] if approved else None},
            "Peer": PEERS,
        }

    def cmd(self, args, sudo=False, input=None, quiet=False, timeout=None):
        self.calls.append(tuple(args))
        if args[:2] == ["tailscale", "up"]:
            self.running = True
            self.prefs["RouteAll"] = False
        if args[:2] == ["tailscale", "set"]:
            for flag in args[2:]:
                if flag.startswith("--advertise-routes="):
                    self.prefs["AdvertiseRoutes"] = [flag.split("=", 1)[1]]
                if flag == "--accept-routes=false":
                    self.prefs["RouteAll"] = False
        if args[:2] == ["tailscale", "logout"]:
            self.running = False

    def capture(self, args, sudo=False, input=None, timeout=None):
        if args == ["tailscale", "status", "--json"]:
            self.checks += 1
            return json.dumps(self.state())
        if args == ["tailscale", "debug", "prefs"]:
            return json.dumps(self.prefs)
        raise AssertionError(args)

    def succeeds(self, args, sudo=False, timeout=None):
        return "tailscale" in self.packages

    def sudo_prepare(self, reason):
        self.calls.append(("sudo_prepare",))

    def installed(self, package):
        return package in self.packages

    def install(self, packages):
        self.calls.append(("install", *packages))
        self.packages.update(packages)

    def uninstall(self, packages):
        self.calls.append(("uninstall", *packages))
        self.packages.difference_update(packages)

    def service_enable(self, name):
        self.calls.append(("enable", name))

    def service_disable(self, name):
        self.calls.append(("disable", name))

    def firewall_open(self, items):
        self.calls.append(("open", *items))

    def firewall_close(self, items):
        self.calls.append(("close", *items))

    def firewall_allowed(self, item):
        return True


class NetworkTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        patch = mock.patch.dict(os.environ, {"HOME": str(self.home)})
        patch.start()
        self.addCleanup(patch.stop)
        ui.set_app("network")

    def use(self, system: FakeSystem) -> FakeSystem:
        fake_net = mock.Mock(lan_ip=mock.Mock(return_value="192.168.0.10"), hostname=mock.Mock(return_value="servidor"))
        for patch in (
            mock.patch.object(tailscale, "run", system),
            mock.patch.object(tailscale, "distro", system),
            mock.patch.object(tailscale, "net", fake_net),
            mock.patch.object(tailscale.time, "sleep"),
            mock.patch.object(tailscale.getpass, "getuser", return_value="dono"),
            mock.patch.object(network.adguard, "install"),
            mock.patch.object(network.adguard, "remove"),
            mock.patch.object(network.adguard, "summary"),
            mock.patch.object(network.adguard, "port_rows", return_value=[]),
            mock.patch.object(network.adguard, "installed", return_value=True),
            mock.patch.object(network.caddy, "install"),
            mock.patch.object(network.caddy, "remove"),
            mock.patch.object(network.caddy, "summary"),
            mock.patch.object(network.caddy, "port_rows", return_value=[]),
            mock.patch.object(network.caddy, "installed", return_value=True),
        ):
            patch.start()
            self.addCleanup(patch.stop)
        return system

    def test_fresh_install(self) -> None:
        system = self.use(FakeSystem(approve_after=4))
        outcome = run_in_pty(lambda: (network.install(), system.calls)[1], [b"\n", b"n\n"], columns=120)
        calls = [tuple(call) for call in outcome.result]
        self.assertEqual(outcome.code, 0, outcome.screen)
        self.assertEqual(calls[:4], [("sudo_prepare",), ("install", "tailscale"), ("enable", "tailscaled"), ("open", "41641/udp")])
        self.assertIn(("tailscale", "up", "--reset", "--accept-routes=false", "--operator=dono", "--hostname=servidor"), calls)
        self.assertIn(("tailscale", "set", "--advertise-routes=192.168.0.10/32"), calls)
        screen = outcome.screen
        self.assertIn("Falta aprovar o anúncio de 192.168.0.10/32", screen)
        self.assertIn("docs/tailscale.md#aprovar-a-rota-do-servidor", screen)
        self.assertIn("docs/roteador.md#redirecionar-a-porta-do-tailscale", screen)
        self.assertIn("192.168.0.10/32 aprovado no painel", screen)
        self.assertIn("redirecionamento pendente", screen)
        self.assertIn("conectado à rede minha-rede", screen)
        self.assertIn("relay sao", screen)
        self.assertIn("docs/outros-computadores.md", screen)
        self.assertNotIn("New-NetFirewallRule", screen)
        self.assertIn("pc está por relay", screen)
        self.assertNotIn("celular está por relay", screen)
        self.assertIn("celular", screen)
        self.assertEqual(config.load("network"), {"ROUTER_FORWARD": "no"})

    def test_already_connected_and_reuse(self) -> None:
        system = self.use(FakeSystem(installed=True, running=True, approve_after=0))
        system.prefs = {"AdvertiseRoutes": ["192.168.0.10/32"], "RouteAll": True, "OperatorUser": "dono"}
        config.save("network", {"ROUTER_FORWARD": "yes"})
        outcome = run_in_pty(lambda: (network.install(reuse=True), system.calls)[1], [], columns=120)
        calls = [tuple(call) for call in outcome.result]
        self.assertEqual(outcome.code, 0, outcome.screen)
        self.assertIn(("tailscale", "set", "--accept-routes=false", "--operator=dono"), calls)
        self.assertFalse(any(call[:2] == ("tailscale", "up") for call in calls))
        self.assertFalse(any("--advertise-routes" in " ".join(call) for call in calls))
        self.assertNotIn("Já fez esse redirecionamento", outcome.screen)

    def test_approval_left_pending(self) -> None:
        self.use(FakeSystem(approve_after=99))
        outcome = run_in_pty(lambda: network.install(reuse=False), [b"n\n", b"s\n"], columns=120)
        self.assertEqual(outcome.code, 0, outcome.screen)
        self.assertIn("aprovação pendente", outcome.screen)
        self.assertIn("falta aprovar no painel", outcome.screen)
        self.assertEqual(config.load("network"), {"ROUTER_FORWARD": "yes"})

    def test_remove(self) -> None:
        system = self.use(FakeSystem(installed=True, running=True))
        config.save("network", {"ROUTER_FORWARD": "yes"})
        with mock.patch.object(sys, "stdout", io.StringIO()):
            network.remove()
        self.assertEqual(system.calls, [
            ("sudo_prepare",), ("tailscale", "logout"), ("disable", "tailscaled"), ("close", "41641/udp"),
            ("uninstall", "tailscale"), ("rm", "-rf", "/var/lib/tailscale"),
        ])
        self.assertFalse(config.env_file("network").parent.exists())

    def test_status(self) -> None:
        self.use(FakeSystem())
        self.assertFalse(network.status())
        self.use(FakeSystem(installed=True, running=True))
        self.assertTrue(network.status())

    def test_backup_and_restore(self) -> None:
        self.use(FakeSystem(installed=True, running=True, approve_after=0))
        config.save("network", {"ROUTER_FORWARD": "yes"})
        folder = self.home / "backup"
        folder.mkdir()
        with mock.patch.object(network.adguard, "conf_file", return_value=self.home / "nada"), \
                mock.patch.object(network.caddy, "folder", return_value=self.home / "caddy"):
            network.backup(folder)
        self.assertEqual((folder / ".env").read_text(), "ROUTER_FORWARD=yes\n")
        config.env_file("network").unlink()
        with mock.patch.object(network, "install") as install, mock.patch.object(network.adguard, "conf_file", return_value=self.home / "nada"), \
                mock.patch.object(network.caddy, "folder", return_value=self.home / "caddy"):
            network.restore(folder)
        install.assert_called_once_with(reuse=True)
        self.assertEqual(config.load("network"), {"ROUTER_FORWARD": "yes"})
        self.assertEqual(config.env_file("network").stat().st_mode & 0o777, 0o600)

    def test_actions(self) -> None:
        self.use(FakeSystem(installed=True, running=True))
        self.assertEqual([action.id for action in network.actions()], ["summary", "reconnect", "router", "devices", "reload", "router-dns"])
        with mock.patch.object(sys, "stdout", io.StringIO()):
            tailscale.mark_router()
        self.assertEqual(config.load("network"), {"ROUTER_FORWARD": "yes"})


if __name__ == "__main__":
    unittest.main()
