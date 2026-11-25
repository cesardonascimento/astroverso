import io
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "packages"))

from kit import ui
from kit.app import Action
from manager.apps import LoadedApp, load

APP = load(ROOT / "apps" / "discord")
assert APP.module is not None, APP.problem
agent = APP.module.agent


def fake_app(name: str, actions: list[Action], description: str = "Um app") -> LoadedApp:
    module = types.SimpleNamespace(DESCRIPTION=description, actions=lambda: actions)
    return LoadedApp(name, module=module)


class AgentTest(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        ui.set_app("discord")
        for patch in (mock.patch.dict(os.environ, {"HOME": temp.name}), mock.patch.object(sys, "stdout", io.StringIO())):
            patch.start()
            self.addCleanup(patch.stop)

    def test_manifest_only_remote_actions_of_installed_apps(self) -> None:
        apps = [
            fake_app("rede", [Action("summary", "Resumo da rede", print, remote=True),
                              Action("devices", "Aparelhos", print),
                              Action("reset", "Zerar", print, remote=True, confirm=True)], "Rede da casa"),
            fake_app("nuvem", [Action("summary", "Resumo", print, remote=True)]),
            LoadedApp("quebrado", problem="falta status"),
        ]
        with mock.patch.object(agent, "discover", return_value=apps), \
                mock.patch.object(agent, "installed", side_effect=lambda app: app.name == "rede"):
            manifest = agent.manifest()
        self.assertEqual(manifest["catalogo"], [
            {"id": "rede:summary", "descricao": "rede: Resumo da rede", "confirmar": False, "tipo": "host"},
            {"id": "rede:reset", "descricao": "rede: Zerar", "confirmar": True, "tipo": "host"},
        ])
        self.assertEqual(manifest["ajuda"][0]["grupo"], "rede — Rede da casa")
        self.assertEqual(manifest["canais"], [])

    def test_execute(self) -> None:
        output = "[rede]     ok: tudo certo\n[rede]       linha da tabela\n"
        with mock.patch.object(agent.run, "output", return_value=(0, output)) as runner:
            answer = agent.execute("rede:summary", {"rede:summary"})
        runner.assert_called_once_with([str(agent.COMMAND), "rede", "action", "summary"], timeout=agent.TIMEOUT, env={"NO_COLOR": "1"})
        self.assertEqual(answer, {"ok": True, "saida": "ok: tudo certo\nlinha da tabela"})
        with mock.patch.object(agent.run, "output", return_value=(1, "[rede]     erro: falhou\n")):
            self.assertEqual(agent.execute("rede:summary", {"rede:summary"}), {"ok": False, "saida": "erro: falhou"})
        self.assertFalse(agent.execute("rede:apagar", {"rede:summary"})["ok"])

    def test_handle_answers_every_event(self) -> None:
        sent = []
        with mock.patch.object(agent.discord, "request", side_effect=lambda *args, **_: sent.append(args) or {}), \
                mock.patch.object(agent.run, "output", return_value=(0, "feito")):
            agent.handle({"id": "e1", "tipo": "comando", "acao": "rede:summary"}, {"rede:summary"})
            agent.handle({"id": "e2", "tipo": "botao", "custom_id": "x"}, set())
            agent.handle({"id": "e3", "tipo": "mensagem"}, set())
        self.assertEqual(sent, [
            ("POST", "/v1/eventos/e1/resposta", {"ok": True, "saida": "feito"}),
            ("POST", "/v1/eventos/e2/resposta", {"texto": "este botão não é mais usado"}),
            ("POST", "/v1/eventos/e3/resposta", {}),
        ])

    def test_serve_publishes_and_dispatches(self) -> None:
        calls = []
        events = [[{"id": "e1", "tipo": "comando", "acao": "rede:summary"}]]

        def request(method, path, payload=None, **_):
            calls.append((method, path.split("?")[0]))
            if method == "GET":
                if events:
                    return {"eventos": events.pop()}
                raise agent.discord.DiscordError("caiu")
            return {}

        def stop(_):
            raise KeyboardInterrupt

        manifest = {"catalogo": [{"id": "rede:summary"}], "ajuda": [], "canais": [], "botoes": []}
        with mock.patch.object(agent.discord, "configured", return_value=True), \
                mock.patch.object(agent.discord, "request", side_effect=request), \
                mock.patch.object(agent, "manifest", return_value=manifest), \
                mock.patch.object(agent, "handle") as handle, \
                mock.patch.object(agent.threading, "Thread", side_effect=lambda target, args, daemon: types.SimpleNamespace(start=lambda: target(*args))), \
                mock.patch.object(agent.time, "sleep", side_effect=stop), \
                self.assertRaises(KeyboardInterrupt):
            agent.serve()
        self.assertEqual(calls, [("PUT", "/v1/cliente"), ("GET", "/v1/eventos"), ("GET", "/v1/eventos")])
        handle.assert_called_once_with({"id": "e1", "tipo": "comando", "acao": "rede:summary"}, {"rede:summary"})

    def test_unit(self) -> None:
        text = agent.unit_text()[f"{agent.NAME}.service"]
        self.assertIn(f"ExecStart={ROOT}/astroverso discord action agent\n", text)
        self.assertIn("Restart=always", text)


if __name__ == "__main__":
    unittest.main()
