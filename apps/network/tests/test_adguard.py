import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "packages"))

from kit import config, container, ui
from kit.testing import run_in_pty
from manager.apps import load

APP = load(ROOT / "apps" / "network")
assert APP.module is not None, APP.problem
adguard = APP.module.adguard


class FakeHost:
    Container = container.Container
    Volume = container.Volume

    def __init__(self, split: str = "192.168.0.10") -> None:
        self.calls: list[tuple] = []
        self.split = split
        self.started = False

    def record(self, *call) -> None:
        self.calls.append(call)

    def prepare(self):
        self.record("prepare")

    def once(self, image, args, input=None):
        self.record("once", image, tuple(args), input)
        return "$2a$14$hashdeteste"

    def start(self, spec, timeout=180):
        self.record("start", spec.name)
        self.started = True

    def active(self, name):
        return self.started

    def remove(self, name, image=None):
        self.record("remove", name, image)

    def remove_image(self, image):
        self.record("remove_image", image)

    def sysctl_set(self, name, values):
        self.record("sysctl_set", name, dict(values))

    def sysctl_remove(self, name):
        self.record("sysctl_remove", name)

    def firewall_open(self, items):
        self.record("open", *items)

    def firewall_close(self, items):
        self.record("close", *items)

    def firewall_allowed(self, item):
        return True

    def resolver_route(self, name, domain, server):
        self.record("resolver", name, domain, server)

    def resolver_route_remove(self, name):
        self.record("resolver_remove", name)

    def sudo_prepare(self, reason):
        self.record("sudo")

    def succeeds(self, args, sudo=False, timeout=None):
        return True

    def capture(self, args, sudo=False, input=None, timeout=None):
        if args == ["tailscale", "dns", "status"]:
            return f"Split DNS Routes:\n  - casa.com                 -> {self.split}\n  - ts.net.  -> 199.247.155.53\n"
        raise AssertionError(args)


class AdGuardTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        patch = mock.patch.dict(os.environ, {"HOME": str(self.home), "LANG": "pt_BR.UTF-8"})
        patch.start()
        self.addCleanup(patch.stop)
        ui.set_app("network")

    def use(self, host: FakeHost, resolves: bool = True, connected: bool = True) -> FakeHost:
        fake_net = mock.Mock(lan_ip=mock.Mock(return_value="192.168.0.10"))
        for patch in (
            mock.patch.object(adguard, "container", host),
            mock.patch.object(adguard, "distro", host),
            mock.patch.object(adguard, "run", host),
            mock.patch.object(adguard, "net", fake_net),
            mock.patch.object(adguard, "resolves", return_value=resolves),
            mock.patch.object(adguard.tailscale, "connected", return_value=connected),
        ):
            patch.start()
            self.addCleanup(patch.stop)
        return host

    def test_render(self) -> None:
        text = adguard.render("dono", "$2a$14$abc", "casa.com", "192.168.0.10")
        self.assertIn("  address: 0.0.0.0:8080\n", text)
        self.assertIn("  - name: 'dono'\n    password: '$2a$14$abc'\n", text)
        self.assertIn("language: 'pt-br'", text)
        self.assertIn("  bind_hosts:\n    - 192.168.0.10\n    - 127.0.0.1\n  port: 53\n", text)
        self.assertIn("rewrites: [{domain: '*.casa.com', answer: '192.168.0.10', enabled: true}]", text)
        self.assertNotIn("${", text)

    def test_fresh_install(self) -> None:
        host = self.use(FakeHost())
        keys = [b"casa.com\n", b"\n", b"senha1\n", b"senha1\n", b"s\n"]
        outcome = run_in_pty(lambda: (adguard.install(reuse=False), host.calls)[1], keys, columns=120)
        self.assertEqual(outcome.code, 0, outcome.screen)
        calls = [tuple(call) for call in outcome.result]
        self.assertEqual(calls[0], ("sudo",))
        self.assertEqual(calls[1], ("prepare",))
        self.assertEqual(calls[2][:3], ("once", adguard.HASHER, ["caddy", "hash-password"]))
        self.assertEqual(calls[2][3], "senha1\n")
        self.assertIn(("sysctl_set", "network", {"net.ipv4.ip_unprivileged_port_start": "53"}), calls)
        self.assertIn(("open", "dns"), calls)
        self.assertIn(("start", adguard.NAME), calls)
        self.assertIn(("resolver", "network", "casa.com", "127.0.0.1"), calls)
        self.assertEqual(config.saved_domain(), "casa.com")
        self.assertEqual(config.load("network"), {
            "ADGUARD_USER": "astroverso", "ADGUARD_PASSWORD_HASH": "$2a$14$hashdeteste", "ROUTER_DNS": "yes",
        })
        conf = adguard.conf_file().read_text()
        self.assertIn("password: '$2a$14$hashdeteste'", conf)
        self.assertIn("'*.casa.com', answer: '192.168.0.10'", conf)
        self.assertEqual(adguard.conf_file().stat().st_mode & 0o777, 0o600)
        self.assertIn("Split DNS do Tailscale: casa.com → 192.168.0.10", outcome.screen)
        self.assertIn("como secundário (assim os aparelhos nunca ficam sem DNS)", outcome.screen)
        self.assertIn("docs/roteador.md#reservar-o-ip-e-apontar-o-dns", outcome.screen)
        self.assertNotIn("senha1", outcome.screen)

    def test_reuse_keeps_configuration(self) -> None:
        host = self.use(FakeHost())
        config.home().mkdir()
        (config.home() / "astroverso.env").write_text("DOMAIN=casa.com\n")
        config.save("network", {"ADGUARD_USER": "dono", "ADGUARD_PASSWORD_HASH": "$2a$h", "ROUTER_DNS": "no"})
        adguard.conf_file().parent.mkdir(parents=True)
        adguard.conf_file().write_text("editado pelo painel")
        outcome = run_in_pty(lambda: (adguard.install(reuse=True), host.calls)[1], [], columns=120)
        self.assertEqual(outcome.code, 0, outcome.screen)
        self.assertFalse(any(call[0] == "once" for call in outcome.result))
        self.assertEqual(adguard.conf_file().read_text(), "editado pelo painel")
        self.assertNotIn("?", outcome.screen.replace("? usar", ""))

    def test_split_dns_pending(self) -> None:
        self.use(FakeHost(split="192.168.0.99"))
        config.home().mkdir()
        (config.home() / "astroverso.env").write_text("DOMAIN=casa.com\n")
        config.save("network", {"ADGUARD_USER": "dono", "ADGUARD_PASSWORD_HASH": "$2a$h", "ROUTER_DNS": "yes"})
        outcome = run_in_pty(lambda: adguard.install(reuse=True), [b"s\n", b"n\n"], columns=120)
        self.assertEqual(outcome.code, 0, outcome.screen)
        self.assertIn("ainda manda casa.com para 192.168.0.99", outcome.screen)
        self.assertIn("Split DNS pendente", outcome.screen)
        self.assertIn("docs/tailscale.md#split-dns", outcome.screen)
        self.assertNotIn("Restrict to domain", outcome.screen)

    def test_remove(self) -> None:
        host = self.use(FakeHost())
        with mock.patch.object(sys, "stdout", io.StringIO()):
            adguard.remove()
        self.assertEqual(host.calls, [
            ("sudo",), ("remove", adguard.NAME, adguard.IMAGE), ("remove_image", adguard.HASHER),
            ("resolver_remove", "network"), ("close", "dns"), ("sysctl_remove", "network"),
        ])

    def test_summary(self) -> None:
        host = self.use(FakeHost())
        host.started = True
        config.home().mkdir()
        (config.home() / "astroverso.env").write_text("DOMAIN=casa.com\n")
        config.save("network", {"ADGUARD_USER": "dono", "ROUTER_DNS": "no"})
        out = io.StringIO()
        with mock.patch.object(sys, "stdout", out):
            adguard.summary()
        text = out.getvalue()
        self.assertIn("*.casa.com → 192.168.0.10", text)
        self.assertIn("✔ casa.com → 192.168.0.10", text)
        self.assertIn("! pendente", text)
        self.assertIn("https://adguard.casa.com (usuário dono)", text)


if __name__ == "__main__":
    unittest.main()
