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

from kit import config, container, ui
from kit.testing import run_in_pty
from manager.apps import load

APP = load(ROOT / "apps" / "network")
assert APP.module is not None, APP.problem
caddy = APP.module.caddy


class FakeHost:
    Container = container.Container
    Volume = container.Volume

    def __init__(self) -> None:
        self.calls: list[tuple] = []
        self.started = False

    def record(self, *call) -> None:
        self.calls.append(call)

    def prepare(self):
        self.record("prepare")

    def build(self, image, file, args=None):
        self.record("build", image, dict(args or {}))

    def remove_image(self, image):
        self.record("remove_image", image)

    def start(self, spec, timeout=180):
        self.record("start", spec.name, str(spec.env_file))
        self.started = True

    def active(self, name):
        return self.started

    def exec(self, name, args):
        self.record("exec", name, tuple(args))
        return ""

    def remove(self, name, image=None):
        self.record("remove", name, image)

    def unit(self, name):
        return f"{name}.service"

    def firewall_open(self, items):
        self.record("open", *items)

    def firewall_close(self, items):
        self.record("close", *items)

    def firewall_allowed(self, item):
        return True

    def sudo_prepare(self, reason):
        self.record("sudo")

    def capture(self, args, sudo=False, input=None, timeout=None):
        return ""


def answers(good: str):
    def api(token, path):
        if token != good:
            return {"success": False}
        if path == "user/tokens/verify":
            return {"success": True, "result": {"status": "active"}}
        if path == "zones?name=casa.com":
            return {"success": True, "result_info": {"count": 1}}
        return {"success": True, "result_info": {"count": 0}}
    return api


class CaddyTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        patch = mock.patch.dict(os.environ, {"HOME": str(self.home)})
        patch.start()
        self.addCleanup(patch.stop)
        ui.set_app("network")
        config.home().mkdir()
        (config.home() / "astroverso.env").write_text("DOMAIN=casa.com\n")

    def use(self, host: FakeHost, certificate: str = "24/02/2027") -> FakeHost:
        for patch in (
            mock.patch.object(caddy, "container", host),
            mock.patch.object(caddy, "distro", host),
            mock.patch.object(caddy, "run", host),
            mock.patch.object(caddy, "_api", side_effect=answers("bom")),
            mock.patch.object(caddy, "certificate", return_value=certificate),
            mock.patch.object(caddy.time, "sleep"),
        ):
            patch.start()
            self.addCleanup(patch.stop)
        return host

    def test_check_token(self) -> None:
        with mock.patch.object(caddy, "_api", side_effect=answers("bom")):
            self.assertEqual(caddy.check_token("bom", "casa.com"), "")
            self.assertEqual(caddy.check_token("bom", "sub.casa.com"), "")
            self.assertIn("não aceitou", caddy.check_token("ruim", "casa.com"))
            self.assertIn("não enxerga a zona", caddy.check_token("bom", "outro.com"))
        with mock.patch.object(caddy, "_api", return_value=None):
            self.assertIn("não respondeu", caddy.check_token("bom", "casa.com"))

    def test_render(self) -> None:
        caddy._save_devices([
            {"name": "roteador", "ip": "192.168.0.1", "port": 443, "https": True},
            {"name": "n8n", "ip": "192.168.0.20", "port": 5678, "https": False},
        ])
        caddy.routes_folder().mkdir()
        (caddy.routes_folder() / "nuvem.json").write_text(json.dumps([
            {"host": "nuvem.casa.com", "target": "http://astroverso-nuvem:80"},
            {"host": "fotos.outro.com", "target": "http://astroverso-nuvem:80"},
        ]))
        text = caddy.render("casa.com")
        self.assertTrue(text.startswith("{\n\tacme_dns cloudflare {env.CLOUDFLARE_API_TOKEN}\n}\n\n*.casa.com {\n"))
        self.assertIn("\t@route1 host adguard.casa.com\n\thandle @route1 {\n\t\treverse_proxy http://host.containers.internal:8080\n\t}\n", text)
        self.assertIn("@route2 host nuvem.casa.com", text)
        self.assertIn("reverse_proxy https://192.168.0.1:443 {\n\t\t\ttransport http {\n\t\t\t\ttls_insecure_skip_verify", text)
        self.assertIn("reverse_proxy http://192.168.0.20:5678", text)
        self.assertIn("\thandle {\n\t\tabort\n\t}\n}\n", text)
        self.assertIn("\nfotos.outro.com {\n\treverse_proxy http://astroverso-nuvem:80\n}\n", text)
        origins = {host: origin for host, _, origin in caddy.routes("casa.com")}
        self.assertEqual(origins["adguard.casa.com"], "network")
        self.assertEqual(origins["nuvem.casa.com"], "app nuvem")
        self.assertEqual(origins["roteador.casa.com"], "aparelho da rede")

    def test_fresh_install(self) -> None:
        host = self.use(FakeHost())
        keys = [b"ruim\n", b"bom\n", b"\n"]
        outcome = run_in_pty(lambda: (caddy.install(reuse=False), host.calls)[1], keys, columns=120)
        self.assertEqual(outcome.code, 0, outcome.screen)
        calls = [tuple(call) for call in outcome.result]
        self.assertEqual(calls[:3], [("sudo",), ("prepare",), ("open", "http", "https", "443/udp")])
        self.assertEqual(calls[3][:2], ("build", caddy.IMAGE))
        self.assertIn(("remove_image", caddy.BUILDER), calls)
        self.assertIn(("start", caddy.NAME, str(caddy.env_file())), calls)
        self.assertEqual(caddy.env_file().read_text(), "CLOUDFLARE_API_TOKEN=bom\n")
        self.assertEqual(caddy.env_file().stat().st_mode & 0o777, 0o600)
        self.assertIn("adguard.casa.com", caddy.caddyfile().read_text())
        self.assertIn("não aceitou esse token", outcome.screen)
        self.assertIn("cadeado válido para *.casa.com", outcome.screen)
        self.assertIn("https://adguard.casa.com", outcome.screen)
        self.assertNotIn("ruim", outcome.screen)
        self.assertNotRegex(outcome.screen, r"\bbom\b")

    def test_reuse_with_valid_token(self) -> None:
        self.use(FakeHost())
        caddy._save_token("bom")
        outcome = run_in_pty(lambda: caddy.install(reuse=True), [], columns=120)
        self.assertEqual(outcome.code, 0, outcome.screen)
        self.assertIn("token da Cloudflare salvo continua válido", outcome.screen)
        self.assertNotIn("Criar endereços", outcome.screen)

    def test_add_device(self) -> None:
        host = self.use(FakeHost())
        host.started = True
        keys = [b"\r", b"adguard\n", b"roteador\n", b"192.168.0.1\n", b"443\n", b"\x1b[B", b"\r", b"\x1b"]
        outcome = run_in_pty(lambda: (caddy.manage_devices(), host.calls)[1], keys, columns=120)
        self.assertEqual(outcome.code, 0, outcome.screen)
        self.assertIn("o nome adguard já está em uso", outcome.screen)
        self.assertEqual(caddy.devices(), [{"name": "roteador", "ip": "192.168.0.1", "port": 443, "https": True}])
        self.assertIn(["exec", caddy.NAME, ["caddy", "reload", "--config", "/etc/caddy/Caddyfile", "--adapter", "caddyfile"]],
                      outcome.result)
        self.assertIn("roteador.casa.com", caddy.caddyfile().read_text())

    def test_remove(self) -> None:
        host = self.use(FakeHost())
        with mock.patch.object(sys, "stdout", io.StringIO()):
            caddy.remove()
        self.assertEqual(host.calls, [
            ("sudo",), ("remove", caddy.NAME, caddy.IMAGE), ("remove_image", caddy.BASE),
            ("remove_image", caddy.BUILDER), ("close", "http", "https", "443/udp"),
        ])

    def test_summary(self) -> None:
        host = self.use(FakeHost(), certificate="")
        host.started = True
        out = io.StringIO()
        with mock.patch.object(sys, "stdout", out):
            caddy.summary()
        text = out.getvalue()
        self.assertIn("! ainda não emitido", text)
        self.assertIn("https://adguard.casa.com", text)
        self.assertIn("! falta", text)


if __name__ == "__main__":
    unittest.main()
