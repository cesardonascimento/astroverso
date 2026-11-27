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

from kit import config, container, discord, mail, mailboxes, routes, ui
from kit.testing import run_in_pty
from manager.apps import load

APP = load(ROOT / "apps" / "n8n")
assert APP.module is not None, APP.problem
app = APP.module
n8n = app.n8n
modules = app.modules
connections = app.connections


def make_module(base: Path, name: str, body: str = "print('oi')") -> Path:
    folder = base / name
    (folder / "tests").mkdir(parents=True)
    (folder / "Containerfile").write_text("FROM python\n")
    (folder / "service.py").write_text(body)
    (folder / "README.md").write_text("doc")
    (folder / "tests" / "test_x.py").write_text("teste")
    return folder


class N8nTest(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.home = Path(temp.name)
        ui.set_app("n8n")
        self.modules = self.home / "modules"
        self.modules.mkdir()
        for patch in (
            mock.patch.dict(os.environ, {"HOME": str(self.home)}),
            mock.patch.object(modules, "FOLDER", self.modules),
            mock.patch.object(config, "timezone", return_value="UTC"),
            mock.patch.object(__import__("kit.vault").vault, "units", mock.Mock(active=mock.Mock(return_value=False))),
        ):
            patch.start()
            self.addCleanup(patch.stop)
        config.home().mkdir()
        (config.home() / "astroverso.env").write_text("DOMAIN=casa.com\n")

    def test_modules_found_digest_and_spec(self) -> None:
        folder = make_module(self.modules, "contas")
        (self.modules / "Errado").mkdir()
        (self.modules / "Errado" / "Containerfile").write_text("x")
        make_module(self.modules, "runners")
        (self.modules / "sem-imagem").mkdir()
        with mock.patch.object(sys, "stdout", io.StringIO()):
            found = modules.found()
        self.assertEqual([item.name for item in found], ["contas"])
        before = modules.digest(folder)
        (folder / "README.md").write_text("doc nova")
        (folder / "tests" / "test_x.py").write_text("outro")
        self.assertEqual(modules.digest(folder), before)
        (folder / "service.py").write_text("print('mudou')")
        self.assertNotEqual(modules.digest(folder), before)
        spec = modules.spec(found[0])
        self.assertEqual((spec.name, spec.network), ("astroverso-n8n-contas", "astroverso"))
        self.assertEqual(spec.image, f"localhost/astroverso-n8n-contas:{modules.digest(folder)}")
        self.assertEqual(spec.ports, ())
        self.assertIn("/v1/saude", spec.health)
        self.assertEqual(found[0].url, "http://astroverso-n8n-contas:8080")

    def test_start_all_builds_and_drops_stale(self) -> None:
        make_module(self.modules, "contas")
        quadlets = self.home / "quadlets"
        quadlets.mkdir()
        for name in ("astroverso-n8n-contas", "astroverso-n8n-velho", "astroverso-n8n-runners", "astroverso-n8n"):
            (quadlets / f"{name}.container").write_text("x")
        calls: list[tuple] = []
        fake = mock.Mock(
            quadlets=lambda: quadlets, build=lambda image, file: calls.append(("build", image)),
            start=lambda spec: calls.append(("start", spec.name)), remove=lambda name: calls.append(("remove", name)),
            remove_image=lambda image: calls.append(("rmi", image)),
        )
        with mock.patch.object(modules, "container", fake), mock.patch.object(modules.run, "output", return_value=(0, "localhost/astroverso-n8n-contas:antigo\n")), \
                mock.patch.object(sys, "stdout", io.StringIO()):
            modules.start_all()
        self.assertEqual([call[0] for call in calls], ["build", "start", "rmi", "remove"])
        self.assertEqual(calls[2], ("rmi", "localhost/astroverso-n8n-contas:antigo"))
        self.assertEqual(calls[3], ("remove", "astroverso-n8n-velho"))

    def test_connections_from_kit_contracts(self) -> None:
        with mock.patch.object(sys, "stdout", io.StringIO()):
            found, missing = connections.build()
        self.assertEqual(found, [])
        self.assertEqual(len(missing), 3)
        mail.save("https://envio.exemplo.dev", "chave-envio")
        discord.save("https://discord.casa.com", "chave-discord")
        secret = self.home / "senha-imap"
        secret.write_text("senha-imap\n")
        with mock.patch.object(sys, "stdout", io.StringIO()):
            mailboxes.publish("mail", [mailboxes.Mailbox("inbox", "inbox@casa.com", "astroverso-mail", 31143, "inbox", str(secret))])
        config.save("n8n", {"HOOK_KEY": "chave-chamadas"})
        found, missing = connections.build()
        self.assertEqual(missing, [])
        self.assertEqual([item.id for item in found], ["astroversoEnvioEmail", "astroversoImapInbox", "astroversoDiscord", "astroversoChamadas"])
        imap = found[1]
        self.assertEqual((imap.type, imap.data["host"], imap.data["port"], imap.data["password"]), ("imap", "astroverso-mail", 31143, "senha-imap"))
        self.assertEqual(found[2].data, {"name": "Authorization", "value": "Bearer chave-discord"})
        self.assertEqual(found[0].detail, "POST https://envio.exemplo.dev/enviar")
        with mock.patch.object(n8n, "import_file", return_value=(0, "")) as imported, mock.patch.object(sys, "stdout", io.StringIO()):
            self.assertTrue(connections.sync())
        kind, payload = imported.call_args.args
        self.assertEqual(kind, "credentials")
        self.assertEqual([item["id"] for item in json.loads(payload)], [item.id for item in found])

    def test_import_file_keeps_secrets_out_of_arguments(self) -> None:
        calls: list[tuple] = []

        def exec_output(name, args, user="", env=None, input=None, timeout=None):
            calls.append((args, input))
            return 0, "Successfully imported 1 credential."

        with mock.patch.object(n8n.container, "exec_output", side_effect=exec_output):
            self.assertEqual(n8n.import_file("credentials", '[{"data": "segredo"}]')[0], 0)
        self.assertEqual(calls[0][1], '[{"data": "segredo"}]')
        self.assertEqual(calls[1][0], ["n8n", "import:credentials", f"--input={n8n.INBOX}"])
        self.assertEqual(calls[2][0], ["rm", "-f", n8n.INBOX])
        self.assertTrue(all("segredo" not in " ".join(args) for args, _ in calls))
        with mock.patch.object(n8n.container, "exec_output", return_value=(0, "An error occurred while importing")):
            self.assertEqual(n8n.import_file("workflow", "{}")[0], 1)

    def test_install(self) -> None:
        recorded: list[str] = []
        keys = [b"\n", b"\n", b"\n", b"\n", b"curta\n", b"curta\n", b"Senha-longa-2026\n", b"Senha-longa-2026\n", b"\n", b"\n"]
        with mock.patch.object(n8n, "save_password", side_effect=lambda password: (recorded.append(password), n8n.hash_file().write_text("$2hash"))), \
                mock.patch.object(n8n, "start", side_effect=lambda: recorded.append("start")), \
                mock.patch.object(connections, "sync", side_effect=lambda: recorded.append("sync")), \
                mock.patch.object(app, "summary"), \
                mock.patch.object(app.watch, "change", side_effect=lambda *a, **k: app.changes.Change("watch", a[1], a[2], lambda: False, lambda: None, lambda: None)):
            outcome = run_in_pty(lambda: (app.install(reuse=False), recorded)[1], keys, columns=160)
        self.assertEqual(outcome.code, 0, outcome.screen)
        self.assertIn("use pelo menos 8 caracteres", outcome.screen)
        self.assertEqual(outcome.result, ["Senha-longa-2026", "start", "sync"])
        self.assertNotIn("Senha-longa", outcome.screen)
        values = config.load("n8n")
        self.assertEqual((values["HOST"], values["OWNER_EMAIL"]), ("n8n.casa.com", "n8n@casa.com"))
        self.assertTrue(values["HOOK_KEY"])
        secrets = config.read_env(n8n.secrets_file())
        self.assertTrue(secrets["N8N_ENCRYPTION_KEY"])
        self.assertEqual(config.read_env(n8n.runners_file()), {"N8N_RUNNERS_AUTH_TOKEN": secrets["N8N_RUNNERS_AUTH_TOKEN"]})
        self.assertEqual(n8n.secrets_file().stat().st_mode & 0o777, 0o600)
        self.assertEqual(json.loads((routes.folder() / "n8n.json").read_text()), [{"host": "n8n.casa.com", "target": "http://astroverso-n8n:5678"}])

    def test_specs(self) -> None:
        config.save("n8n", {"HOST": "n8n.casa.com", "OWNER_EMAIL": "eu@casa.com"})
        main = n8n.main_spec()
        self.assertEqual(main.environment["WEBHOOK_URL"], "https://n8n.casa.com/")
        self.assertEqual(main.environment["N8N_INSTANCE_OWNER_EMAIL"], "eu@casa.com")
        for key in ("N8N_DIAGNOSTICS_ENABLED", "N8N_VERSION_NOTIFICATIONS_ENABLED", "N8N_TEMPLATES_ENABLED"):
            self.assertEqual(main.environment[key], "false")
        self.assertEqual(main.environment["N8N_DEFAULT_BINARY_DATA_MODE"], "filesystem")
        self.assertNotIn("N8N_ENCRYPTION_KEY", main.environment)
        self.assertEqual(main.env_file, n8n.secrets_file())
        self.assertEqual(main.ports, ())
        runners = n8n.runners_spec()
        self.assertEqual((runners.requires, runners.env_file), ([n8n.NAME], n8n.runners_file()))
        self.assertEqual(runners.image.rsplit(":", 1)[1], main.image.rsplit(":", 1)[1])
        make_module(self.modules, "contas")
        self.assertEqual([spec.name for spec in n8n.specs()], ["astroverso-n8n", "astroverso-n8n-runners", "astroverso-n8n-contas"])

    def test_restore_workflow_as_copy(self) -> None:
        folder = self.home / "versao"
        (folder / "workflows").mkdir(parents=True)
        (folder / "workflows" / "a.json").write_text(json.dumps({"id": "abc", "name": "Contas", "active": True, "nodes": []}))
        (folder / "workflows" / "b.json").write_text(json.dumps({"id": "def", "name": "Avisos", "active": True}))
        imported: list[tuple] = []

        class Opened:
            def __enter__(self):
                return folder, "12/11/2026 01:10"

            def __exit__(self, *args):
                return False

        with mock.patch.object(n8n, "installed", return_value=True), mock.patch.object(app.vault, "opened", return_value=Opened()), \
                mock.patch.object(n8n, "import_file", side_effect=lambda kind, content, *extra: imported.append((kind, json.loads(content), extra)) or (0, "")):
            outcome = run_in_pty(lambda: (app.restore_workflow(), imported)[1], [b"\x1b[B", b"\r", b"\r"], columns=160)
        self.assertEqual(outcome.code, 0, outcome.screen)
        [(kind, content, extra)] = outcome.result
        self.assertEqual(kind, "workflow")
        self.assertEqual(content, {"name": "Contas (restaurada de 12/11)", "active": False, "nodes": []})
        self.assertEqual(extra, [])

    def test_restore_workflow_replacing_republishes(self) -> None:
        folder = self.home / "versao"
        (folder / "workflows").mkdir(parents=True)
        (folder / "workflows" / "a.json").write_text(json.dumps({"id": "abc", "name": "Contas", "active": True}))
        calls: list = []

        class Opened:
            def __enter__(self):
                return folder, "12/11/2026 01:10"

            def __exit__(self, *args):
                return False

        with mock.patch.object(n8n, "installed", return_value=True), mock.patch.object(app.vault, "opened", return_value=Opened()), \
                mock.patch.object(n8n, "import_file", side_effect=lambda kind, content, *extra: calls.append(json.loads(content)) or (0, "")), \
                mock.patch.object(n8n, "cli", side_effect=lambda *args, **k: calls.append(list(args)) or (0, "")):
            outcome = run_in_pty(lambda: (app.restore_workflow(), calls)[1], [b"\r", b"\x1b[B", b"\r", b"s\n"], columns=160)
        self.assertEqual(outcome.code, 0, outcome.screen)
        self.assertEqual(outcome.result, [{"id": "abc", "name": "Contas", "active": True}, ["publish:workflow", "--id=abc"]])
        self.assertIn("de volta como estava em 12/11/2026 01:10 e ligada", outcome.screen)

    def test_import_workflows_warns_missing_credentials(self) -> None:
        folder = self.home / "rotinas"
        folder.mkdir()
        node = {"name": "NC", "credentials": {"nextCloudApi": {"id": "astroversoNextcloud", "name": "Astroverso: Nextcloud"}}}
        (folder / "a.json").write_text(json.dumps({"id": "abc", "name": "Contas", "active": True, "nodes": [node]}))
        (folder / "b.json").write_text(json.dumps({"id": "def", "name": "Avisos", "nodes": []}))
        imported: list = []
        with mock.patch.object(n8n, "installed", return_value=True), \
                mock.patch.object(n8n, "cli", return_value=(0, '[license SDK] Skipping renewal on init\n[{"id": "x", "name": "Astroverso: Discord", "type": "httpHeaderAuth"}]')), \
                mock.patch.object(n8n, "import_file", side_effect=lambda kind, content: imported.append(json.loads(content)["name"]) or (0, "")):
            keys = [f"{folder}\n".encode(), b"\r", b"s\n"]
            outcome = run_in_pty(lambda: (app.import_workflows(), imported)[1], keys, columns=200)
        self.assertEqual(outcome.code, 0, outcome.screen)
        self.assertIn("credenciais que ainda não existem no n8n: Astroverso: Nextcloud (nextCloudApi)", outcome.screen)
        self.assertEqual(outcome.result, ["Avisos", "Contas"])

    def test_commands_become_remote_actions(self) -> None:
        commands = app.commands
        keys = [b"\r", b"summary\n", b"contas-email\n", b"/webhook/astroverso-contas-email\n", b"Manda o e-mail das contas\n", b"\x1b[B\x1b[B\x1b[B", b"\r"]
        outcome = run_in_pty(lambda: (app.manage_commands(), commands.commands())[1], keys, columns=160)
        self.assertEqual(outcome.code, 0, outcome.screen)
        self.assertIn("o nome summary já está em uso", outcome.screen)
        self.assertEqual(outcome.result, [{"name": "contas-email", "path": "astroverso-contas-email", "description": "Manda o e-mail das contas"}])
        action = next(a for a in app.actions() if a.id == "contas-email")
        self.assertEqual((action.remote, action.menu, action.label), (True, False, "Manda o e-mail das contas"))
        config.save("n8n", {"HOOK_KEY": "segredo-xyz"})
        calls: list = []

        def exec_output(name, args, user="", env=None, input=None, timeout=None):
            calls.append((args, input))
            return 0, 'log do n8n\n{"status": 200, "corpo": "{\\"mensagem\\": \\"enviado\\"}"}'

        with mock.patch.object(n8n, "installed", return_value=True), mock.patch.object(commands.container, "exec_output", side_effect=exec_output), \
                mock.patch.object(sys, "stdout", io.StringIO()) as out:
            action.run()
        self.assertEqual((calls[0][0][-1], calls[0][1]), ("astroverso-contas-email", "segredo-xyz"))
        self.assertNotIn("segredo-xyz", " ".join(calls[0][0]))
        self.assertIn("enviado", out.getvalue())
        self.assertEqual(commands.answer(404, ""), (False, "o n8n não achou o webhook: a rotina está desligada ou o caminho mudou"))
        with mock.patch.object(n8n, "installed", return_value=True), mock.patch.object(commands.container, "exec_output", return_value=(0, '{"status": 500, "corpo": "erro"}')), \
                mock.patch.object(sys, "stderr", io.StringIO()), mock.patch.object(sys, "stdout", io.StringIO()):
            with self.assertRaises(SystemExit):
                action.run()

    def test_collect(self) -> None:
        make_module(self.modules, "contas")
        with mock.patch.object(container, "active", return_value=False):
            self.assertEqual(list(app.collect({})), ["containers"])
        with mock.patch.object(container, "active", return_value=True), mock.patch.object(container, "exec_output", return_value=(1, "")), \
                mock.patch.object(modules, "health", return_value="unhealthy"):
            found = app.collect({})
        self.assertEqual(sorted(found), ["health", "module:contas"])

    def test_items_and_actions(self) -> None:
        self.assertEqual([item.id for item in app.items()], ["watch", "backup"])
        self.assertEqual([(a.id, a.remote) for a in app.actions()],
                         [("summary", True), ("connections", True), ("password", False), ("restore-workflow", False),
                          ("import-workflows", False), ("commands", False), ("changes", False), ("watch", True), ("backup-now", True), ("restore-version", False)])


if __name__ == "__main__":
    unittest.main()
