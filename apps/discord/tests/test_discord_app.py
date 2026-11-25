import hashlib
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

from kit import config, container, discord, routes, ui
from kit.testing import run_in_pty
from manager.apps import load

APP = load(ROOT / "apps" / "discord")
assert APP.module is not None, APP.problem
app = APP.module
server = app.server
client = app.client

BOT_ID = "111111111111111111"
GUILD = "222222222222222222"
OWNER = "333333333333333333"


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

    def start(self, spec, timeout=180):
        self.record("start", spec.name, str(spec.env_file))
        self.started = True

    def restart(self, spec, timeout=180):
        self.record("restart", spec.name)

    def active(self, name):
        return self.started

    def remove(self, name, image=None):
        self.record("remove", name)

    def remove_image(self, image):
        self.record("remove_image", image)

    def unit(self, name):
        return f"{name}.service"

    def capture(self, args, sudo=False, input=None, timeout=None):
        return "localhost/astroverso-discord:velha\n" if args[:2] == ["podman", "images"] else ""

    def succeeds(self, args, sudo=False, timeout=None):
        return True


class FakeDiscord:
    def __init__(self) -> None:
        self.invited = False
        self.guild_checks = 0

    def __call__(self, token, method, path, payload=None):
        if token != "token-bom":
            return 401, {}
        if path == "users/@me" and method == "GET":
            return 200, {"id": BOT_ID, "username": "astro"}
        if path == "users/@me" and method == "PATCH":
            return 200, {}
        if path == "applications/@me":
            return 200, {"flags": 1 << 19}
        if path == "users/@me/guilds":
            self.guild_checks += 1
            return 200, ([{"id": GUILD, "name": "Casa"}] if self.guild_checks > 1 else [])
        if path == f"guilds/{GUILD}":
            return 200, {"owner_id": OWNER}
        return 404, {}


class DiscordAppTest(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.home = Path(temp.name)
        patch = mock.patch.dict(os.environ, {"HOME": str(self.home)})
        patch.start()
        self.addCleanup(patch.stop)
        ui.set_app("discord")
        config.home().mkdir()
        (config.home() / "astroverso.env").write_text("DOMAIN=casa.com\n")
        self.sent: list[tuple] = []

    def use(self, host: FakeHost) -> FakeHost:
        fake_net = mock.Mock(hostname=mock.Mock(return_value="servidor"))
        for patch in (
            mock.patch.object(server, "container", host),
            mock.patch.object(server, "run", host),
            mock.patch.object(server, "net", fake_net),
            mock.patch.object(client, "net", fake_net),
            mock.patch.object(app, "net", fake_net),
            mock.patch.object(server, "_discord", FakeDiscord()),
            mock.patch.object(server, "health", return_value={"ok": True, "clientes": {"servidor": {"visto_ha_s": 30}}}),
            mock.patch.object(server.time, "sleep"),
            mock.patch.object(app.agent, "install"),
            mock.patch.object(app.agent, "remove"),
            mock.patch.object(client.units, "active", return_value=True),
            mock.patch.object(discord, "whoami", side_effect=self.whoami),
            mock.patch.object(discord, "notify", side_effect=lambda *args, **_: self.sent.append(args) or True),
        ):
            patch.start()
            self.addCleanup(patch.stop)
        return host

    def whoami(self, url="", key=""):
        values = discord.settings()
        key = key or values.get("DISCORD_KEY", "")
        if key == "chave-ruim":
            raise discord.DiscordError("401 chave inválida")
        return "servidor" if key else ""

    def test_server_install(self) -> None:
        host = self.use(FakeHost())
        keys = [b"\r", b"token-ruim\n", b"token-bom\n", b"\n", b"\n"]
        outcome = run_in_pty(lambda: (app.install(), host.calls, self.sent)[1:], keys, columns=200)
        self.assertEqual(outcome.code, 0, outcome.screen)
        calls, sent = outcome.result
        values = config.load("discord")
        self.assertEqual(values["MODE"], "server")
        self.assertEqual(values["DISCORD_TOKEN"], "token-bom")
        self.assertEqual(values["DISCORD_GUILD"], GUILD)
        self.assertEqual(values["DISCORD_USERS"], OWNER)
        self.assertEqual(values["DISCORD_MESSAGE_CONTENT"], "yes")
        key = server.client_key("servidor")
        self.assertEqual(values["DISCORD_CLIENTS"], f"servidor={hashlib.sha256(key.encode()).hexdigest()}")
        self.assertEqual((server.keys_folder() / "servidor.key").stat().st_mode & 0o777, 0o600)
        self.assertEqual(discord.settings(), {"DISCORD_URL": "https://discord.casa.com", "DISCORD_KEY": key})
        self.assertEqual(json.loads((routes.folder() / "discord.json").read_text()),
                         [{"host": "discord.casa.com", "target": "http://astroverso-discord:8080"}])
        self.assertIn(["build", server.image(), {"PYTHON_VERSION": server.PYTHON_VERSION, "DISCORD_PY_VERSION": server.DISCORD_PY_VERSION}], calls)
        self.assertIn(["start", server.NAME, str(config.env_file("discord"))], calls)
        self.assertIn(["remove_image", "localhost/astroverso-discord:velha"], calls)
        self.assertEqual(sent[0][:2], ["discord", "sucesso"])
        self.assertIn(f"client_id={BOT_ID}", outcome.screen)
        self.assertIn("docs/discord.md#criar-o-bot", outcome.screen)
        self.assertIn("docs/discord.md#convidar-o-bot", outcome.screen)
        self.assertIn("o Discord recusou esse token", outcome.screen)
        self.assertIn("servidor do Discord: Casa", outcome.screen)
        self.assertNotIn("token-bom", outcome.screen)
        self.assertNotIn(key, outcome.screen)

    def test_reuse_asks_nothing(self) -> None:
        host = self.use(FakeHost())
        config.save("discord", {"MODE": "server", "DISCORD_TOKEN": "token-bom", "DISCORD_GUILD": GUILD, "DISCORD_USERS": OWNER})
        server._discord.guild_checks = 5
        outcome = run_in_pty(lambda: app.install(reuse=True), [], columns=200)
        self.assertEqual(outcome.code, 0, outcome.screen)
        self.assertIn("token salvo continua válido", outcome.screen)
        self.assertNotIn("token do bot", outcome.screen)
        self.assertNotIn("Autorizar mais alguém", outcome.screen)
        self.assertNotIn("Esta máquina", outcome.screen.split("Resumo")[0])

    def test_client_install(self) -> None:
        self.use(FakeHost())
        keys = [b"\x1b[B", b"\r", b"\n", b"chave-ruim\n", b"\n", b"chave-boa\n"]
        outcome = run_in_pty(lambda: (app.install(), self.sent)[1], keys, columns=200)
        self.assertEqual(outcome.code, 0, outcome.screen)
        self.assertEqual(config.load("discord"), {"MODE": "client"})
        self.assertEqual(discord.settings(), {"DISCORD_URL": "https://discord.casa.com", "DISCORD_KEY": "chave-boa"})
        self.assertIn("o bot não aceitou: 401 chave inválida", outcome.screen)
        self.assertIn("ligada ao bot como servidor", outcome.screen)
        self.assertEqual(outcome.result[0][:2], ["discord", "sucesso"])
        self.assertNotIn("chave-boa", outcome.screen)
        self.assertEqual([action.id for action in app.actions()], ["summary", "changes", "test", "agent"])

    def test_add_client_and_actions(self) -> None:
        host = self.use(FakeHost())
        config.save("discord", {"MODE": "server"})
        with mock.patch.object(sys, "stdout", io.StringIO()):
            server._ensure_keys(["servidor"])
        self.assertEqual([action.id for action in app.actions()], ["summary", "changes", "test", "agent", "key", "add-client"])
        outcome = run_in_pty(lambda: (server.add_client(), host.calls)[1], [b"servidor\n", b"studio\n"], columns=200)
        self.assertEqual(outcome.code, 0, outcome.screen)
        self.assertIn("o cliente servidor já existe", outcome.screen)
        self.assertEqual(server.client_names(), ["servidor", "studio"])
        self.assertIn(["restart", server.NAME], outcome.result)
        self.assertIn(f"chave de studio: {server.client_key('studio')}", outcome.screen)

    def test_remove_server(self) -> None:
        host = self.use(FakeHost())
        config.save("discord", {"MODE": "server"})
        discord.save("https://discord.casa.com", "x")
        with mock.patch.object(sys, "stdout", io.StringIO()):
            routes.publish("discord", [routes.Route("discord.casa.com", "http://astroverso-discord:8080")])
            app.remove()
        self.assertIn(("remove", server.NAME), host.calls)
        self.assertIn(("remove_image", "localhost/astroverso-discord:velha"), host.calls)
        self.assertFalse((routes.folder() / "discord.json").exists())
        self.assertFalse(discord.settings_file().exists())
        self.assertFalse((config.home() / "discord").exists())

    def test_summary(self) -> None:
        host = self.use(FakeHost())
        host.started = True
        config.save("discord", {"MODE": "server", "DISCORD_USERS": OWNER, "DISCORD_MESSAGE_CONTENT": "no"})
        with mock.patch.object(sys, "stdout", io.StringIO()):
            server._ensure_keys(["servidor", "studio"])
        discord.save("https://discord.casa.com", server.client_key("servidor"))
        out = io.StringIO()
        with mock.patch.object(sys, "stdout", out):
            app.summary()
        text = out.getvalue()
        self.assertIn("✔ conectado", text)
        self.assertIn("! desligada", text)
        self.assertIn("✔ agora há pouco", text)
        self.assertIn("○ nunca apareceu", text)
        self.assertIn("✔ ligada como servidor", text)


if __name__ == "__main__":
    unittest.main()
