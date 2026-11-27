import io
import json
import os
import subprocess
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

APP = load(ROOT / "apps" / "system")
assert APP.module is not None, APP.problem
app = APP.module
power = app.power
ssh = app.ssh
hostname = app.hostname


def new_key(folder: Path, comment: str) -> str:
    path = folder / comment.replace("@", "-")
    subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", comment, "-f", str(path)], check=True)
    return path.with_suffix(".pub").read_text().strip()


class FakeUpdates:
    def __init__(self) -> None:
        self.on = False
        self.last = ("", "")
        self.pending = False
        self.clock = False
        self.synced = True

    def auto_updates_active(self):
        return self.on

    def auto_updates_on(self):
        self.on = True

    def auto_updates_off(self):
        self.on = False

    def auto_updates_last(self):
        return self.last

    def reboot_pending(self):
        return self.pending

    def time_sync_active(self):
        return self.clock

    def time_sync_on(self):
        self.clock = True

    def time_sync_off(self):
        self.clock = False

    def time_synced(self):
        return self.synced


class FakeSystem:
    def __init__(self) -> None:
        self.calls: list[tuple] = []
        self.masked = False
        self.files: dict[str, str] = {}
        self.units: set[str] = set()
        self.limited = False
        self.sshd = True

    def record(self, *call) -> None:
        self.calls.append(call)

    def units_masked(self, names):
        return self.masked

    def units_mask(self, names):
        self.masked = True
        self.record("mask")

    def units_unmask(self, names):
        self.masked = False
        self.record("unmask")

    def file_put(self, path, content):
        changed = self.files.get(str(path)) != content
        self.files[str(path)] = content
        return changed

    def file_drop(self, path):
        return self.files.pop(str(path), None) is not None

    def reload_service(self, name):
        self.record("reload", name)

    def unit_install(self, name, content):
        self.units.add(name)
        self.record("unit", name)

    def unit_remove(self, name):
        self.units.discard(name)
        self.record("unit_remove", name)

    def unit_enabled(self, name):
        return name in self.units

    def installed(self, package):
        return True

    def install(self, packages):
        self.record("install", *packages)

    def service_active(self, name):
        return self.sshd

    def service_enable(self, name):
        self.sshd = True

    def service_disable(self, name):
        self.sshd = False
        self.record("disable", name)

    def firewall_limit(self, service, sources):
        self.limited = True
        self.record("limit", service, tuple(sources))

    def firewall_unlimit(self, service, sources):
        self.limited = False
        self.record("unlimit", service)

    def firewall_limited(self, service, sources):
        return self.limited

    def hostname_set(self, name):
        self.record("hostname", name)


class SystemTest(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.home = Path(temp.name)
        self.keys = self.home / "chaves"
        self.keys.mkdir()
        patch = mock.patch.dict(os.environ, {"HOME": str(self.home)})
        patch.start()
        self.addCleanup(patch.stop)
        ui.set_app("system")
        self.system = FakeSystem()
        self.updates = FakeUpdates()
        fake_net = mock.Mock(lan_network=mock.Mock(return_value="192.168.0.0/24"), hostname=mock.Mock(return_value="servidor"))
        real_output = ssh.run.output

        def output(args, timeout=None, env=None, input=None):
            if args[:2] == ["ssh", "-T"]:
                return 1, "Hi dono! You've successfully authenticated, but GitHub does not provide shell access.\n" if self.github else "Permission denied (publickey)."
            return real_output(args, timeout=timeout, env=env, input=input)

        self.github = False
        for patch in (
            mock.patch.object(power, "distro", self.system),
            mock.patch.object(app.updates, "distro", self.updates),
            mock.patch.object(app.clock, "distro", self.updates),
            mock.patch.object(app.watch, "units", mock.Mock(active=mock.Mock(return_value=False))),
            mock.patch.object(ssh, "distro", self.system),
            mock.patch.object(ssh, "net", fake_net),
            mock.patch.object(hostname, "net", fake_net),
            mock.patch.object(hostname, "distro", self.system),
            mock.patch.object(ssh.run, "output", side_effect=output),
            mock.patch.object(ssh.run, "succeeds", return_value=True),
            mock.patch.object(ssh.getpass, "getuser", return_value="dono"),
            mock.patch.object(__import__("kit.vault").vault, "units", mock.Mock(active=mock.Mock(return_value=False))),
        ):
            patch.start()
            self.addCleanup(patch.stop)

    def test_parse_and_fingerprint(self) -> None:
        public = new_key(self.keys, "dono@notebook")
        key, plain, comment = ssh.parse(f'from="10.0.0.0/8" {public}')
        self.assertTrue(key.startswith('from="10.0.0.0/8" ssh-ed25519 '))
        self.assertEqual(comment, "dono@notebook")
        self.assertTrue(ssh.fingerprint(plain).startswith("SHA256:"))
        self.assertEqual(ssh.fingerprint("ssh-ed25519 AAAAquebrada"), "")
        with self.assertRaises(ValueError):
            ssh.parse("isto não é chave")

    def test_import_add_remove(self) -> None:
        first, second = new_key(self.keys, "dono@notebook"), new_key(self.keys, "velha")
        ssh.authorized_file().parent.mkdir(mode=0o700)
        ssh.authorized_file().write_text(f"# comentário\n{first}\nlixo\n{second}\n")
        outcome = run_in_pty(lambda: (ssh._import(), ssh.keys())[1], [b"\x1b[B", b" ", b"\r", b"\n"], columns=160)
        self.assertEqual(outcome.code, 0, outcome.screen)
        self.assertEqual([item["name"] for item in outcome.result], ["notebook"])
        text = ssh.authorized_file().read_text()
        self.assertTrue(text.startswith("# Gerado pelo Astroverso"))
        self.assertIn(" ".join(first.split()[:2]) + " notebook\n", text)
        self.assertNotIn(second.split()[1], text)
        self.assertEqual(ssh.authorized_file().stat().st_mode & 0o777, 0o600)
        self.assertIn("linha do authorized_keys ignorada", outcome.screen)

        third = new_key(self.keys, "dono@pc-dev")
        outcome = run_in_pty(lambda: (ssh.add_key(), ssh.keys())[1], [first.encode() + b"\n", third.encode() + b"\n", b"\n"], columns=400)
        self.assertEqual(outcome.code, 0, outcome.screen)
        self.assertIn("essa chave já está autorizada", outcome.screen)
        self.assertEqual([item["name"] for item in outcome.result], ["notebook", "pc-dev"])

        outcome = run_in_pty(lambda: (ssh.remove_keys(), ssh.keys())[1], [b" ", b"\r"], columns=160)
        self.assertEqual([item["name"] for item in outcome.result], ["pc-dev"])

    def test_power_changes(self) -> None:
        items = {item.id: item for item in power.items()}
        self.assertTrue(items["power-sleep"].danger and items["power-lid"].danger)
        self.assertFalse(items["power-keys"].danger or items["power-blank"].danger)
        with mock.patch.object(sys, "stdout", io.StringIO()):
            items["power-sleep"].apply()
            items["power-lid"].apply()
            items["power-blank"].apply()
        self.assertTrue(self.system.masked)
        self.assertIn("HandleLidSwitch=ignore", self.system.files[str(power.LID)])
        self.assertIn(("reload", "systemd-logind"), self.system.calls)
        self.assertIn(power.BLANK, self.system.units)
        self.assertIn("--blank 1 --powerdown 1", power.BLANK_TEXT)

    def test_ssh_changes(self) -> None:
        items = {item.id: item for item in ssh.items()}
        self.assertTrue(items["ssh-server"].danger)
        with mock.patch.object(sys, "stdout", io.StringIO()):
            items["ssh-firewall"].apply()
            items["ssh-users"].apply()
        self.assertIn(("limit", "ssh", ("192.168.0.0/24", "100.64.0.0/10")), self.system.calls)
        self.assertEqual(self.system.files[str(ssh.DROPIN)], "AllowUsers dono\nPermitRootLogin no\n")

    def test_install_remove(self) -> None:
        def scenario():
            app.install(reuse=False)
            return self.system.calls

        self.github = True
        keys = [b"\n"] * 14
        with mock.patch.object(ssh, "_import"), mock.patch.object(ssh.run, "cmd", side_effect=lambda args, **_: self._keygen(args)):
            outcome = run_in_pty(scenario, keys, columns=160)
        self.assertEqual(outcome.code, 0, outcome.screen)
        self.assertIn("Desligar a suspensão e a hibernação? [S/n]", outcome.screen)
        self.assertIn("Aceitar SSH só da rede de casa e do Tailscale? [S/n]", outcome.screen)
        self.assertIn("o GitHub aceitou a chave desta máquina", outcome.screen)
        self.assertIn("Atualizar o sistema sozinho, todo dia de madrugada (sem reiniciar)? [S/n]", outcome.screen)
        self.assertIn("⚠ Ignorar a tampa fechada", outcome.screen)
        self.assertIn("nome da máquina: servidor", outcome.screen)
        self.assertIn("Acertar o relógio pela internet (NTP)? [S/n]", outcome.screen)
        self.assertNotIn(["hostname", "servidor"], outcome.result)
        saved = config.load("system")
        self.assertEqual(saved["HOSTNAME"], "servidor")
        self.assertEqual({key: value for key, value in saved.items() if key.startswith("CHANGE_")}, {
            "CHANGE_CLOCK": "yes", "CHANGE_POWER_SLEEP": "yes", "CHANGE_POWER_LID": "yes", "CHANGE_POWER_KEYS": "yes", "CHANGE_POWER_BLANK": "yes",
            "CHANGE_SSH_SERVER": "yes", "CHANGE_SSH_FIREWALL": "yes", "CHANGE_SSH_USERS": "yes", "CHANGE_UPDATES": "yes",
            "CHANGE_WATCH": "yes", "CHANGE_BACKUP": "yes",
        })

    def test_clock_watch(self) -> None:
        self.updates.clock, self.updates.synced = True, False
        self.assertEqual(app.clock.collect()["clock"].title, "Relógio fora de sincronia")
        self.updates.synced = True
        self.assertEqual(app.clock.collect(), {})
        self.updates.clock, self.updates.synced = False, False
        self.assertEqual(app.clock.collect(), {})

    def test_hostname(self) -> None:
        self.assertEqual(hostname.validate(" Casa-01 "), "casa-01")
        for bad in ("-casa", "casa-", "casa.lan", "c" * 64, "", "casa_1"):
            with self.assertRaises(ValueError):
                hostname.validate(bad)
        outcome = run_in_pty(lambda: (hostname.install(False), self.system.calls)[1], [b"-ruim\n", b"novo\n"], columns=160)
        self.assertEqual(outcome.code, 0, outcome.screen)
        self.assertIn("? nome da máquina [servidor]", outcome.screen)
        self.assertIn("sem hífen no começo nem no fim", outcome.screen)
        self.assertIn(["hostname", "novo"], outcome.result)
        self.assertIn("reinstale os apps", outcome.screen)
        self.assertEqual(config.load("system")["HOSTNAME"], "novo")
        self.system.calls.clear()
        with mock.patch.object(sys, "stdout", io.StringIO()):
            hostname.install(True)
        self.assertEqual(self.system.calls, [("hostname", "novo")])

    def _keygen(self, args) -> None:
        if args[0] == "ssh-keygen":
            path = Path(args[args.index("-f") + 1])
            path.write_text("privada")
            path.with_suffix(".pub").write_text("ssh-ed25519 AAAA dono@servidor\n")

    def test_github_creates_key_and_waits(self) -> None:
        with mock.patch.object(ssh.run, "cmd", side_effect=lambda args, **_: self._keygen(args)):
            outcome = run_in_pty(ssh.github, [b"n\n"], columns=160)
        self.assertEqual(outcome.code, 0, outcome.screen)
        self.assertIn("ssh-ed25519 AAAA dono@servidor", outcome.screen)
        self.assertIn("docs/github.md#cadastrar-a-chave", outcome.screen)
        self.assertIn("GitHub pendente", outcome.screen)
        self.assertTrue(ssh.machine_key().exists())

    def test_updates_collect(self) -> None:
        self.assertEqual(app.collect({}), {})
        self.updates.on = True
        self.updates.last = ("success", "qua 2026-11-25 06:10:00 -03")
        self.assertEqual(app.collect({}), {})
        self.updates.last = ("exit-code", "qua 2026-11-25 06:10:00 -03")
        self.updates.pending = True
        found = app.collect({})
        self.assertEqual(sorted(found), ["reboot", "updates"])
        self.assertEqual((found["updates"].level, found["reboot"].level), ("erro", "aviso"))

    def test_remove_keeps_sshd(self) -> None:
        self.system.masked = True
        self.system.limited = True
        config.save("system", {"CHANGE_SSH_SERVER": "yes"})
        with mock.patch.object(sys, "stdout", io.StringIO()):
            app.remove()
        self.assertTrue(self.system.sshd)
        self.assertIn(("unlimit", "ssh"), self.system.calls)
        self.assertIn(("unmask",), self.system.calls)
        self.assertFalse(config.env_file("system").parent.exists())

    def test_actions(self) -> None:
        self.assertEqual([(a.id, a.remote) for a in app.actions()],
                         [("summary", True), ("changes", False), ("keys", False), ("github", False), ("watch", True), ("backup-now", True), ("restore-version", False)])


if __name__ == "__main__":
    unittest.main()
