import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from kit import distro, ui
from kit.distro import fedora


class Recorder:
    def __init__(self, succeeds: dict[tuple[str, ...], bool] | None = None, captures: dict[tuple[str, ...], str] | None = None):
        self.calls: list[tuple[str, tuple[str, ...], bool, str | None]] = []
        self.answers = succeeds or {}
        self.captures = captures or {}

    def cmd(self, args, sudo=False, input=None, quiet=False, timeout=None):
        self.calls.append(("cmd", tuple(args), sudo, input))

    def capture(self, args, sudo=False, input=None, timeout=None):
        return self.captures.get(tuple(args), "")

    def succeeds(self, args, sudo=False, timeout=None):
        return self.answers.get(tuple(args), False)

    def commands(self) -> list[tuple[str, ...]]:
        return [call[1] for call in self.calls]


class DistroTest(unittest.TestCase):
    def setUp(self) -> None:
        ui.set_app("teste")
        self.out = io.StringIO()
        self.err = io.StringIO()
        for patch in (mock.patch.object(sys, "stdout", self.out), mock.patch.object(sys, "stderr", self.err)):
            patch.start()
            self.addCleanup(patch.stop)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def use(self, recorder: Recorder) -> Recorder:
        patch = mock.patch.object(fedora, "run", recorder)
        patch.start()
        self.addCleanup(patch.stop)
        return recorder

    def release(self, text: str) -> Path:
        path = self.root / "os-release"
        path.write_text(text)
        return path

    def test_detect(self) -> None:
        path = self.release('NAME="Fedora Linux"\nID=fedora\nPRETTY_NAME="Fedora Linux 44 (Forty Four)"\n')
        self.assertEqual(distro.release(path)["PRETTY_NAME"], "Fedora Linux 44 (Forty Four)")
        with mock.patch.object(distro, "_backend", None):
            self.assertIs(distro.backend(path), fedora)

    def test_unsupported(self) -> None:
        path = self.release('ID=debian\nPRETTY_NAME="Debian GNU/Linux 13 (trixie)"\n')
        with mock.patch.object(distro, "_backend", None), self.assertRaises(SystemExit):
            distro.backend(path)
        self.assertIn("distribuição não suportada: Debian GNU/Linux 13 (trixie)", self.err.getvalue())
        with mock.patch.object(distro, "_backend", None), self.assertRaises(SystemExit):
            distro.backend(self.root / "nada")
        self.assertIn("distribuição não suportada: desconhecida", self.err.getvalue())

    def test_install_only_missing(self) -> None:
        recorder = self.use(Recorder({("rpm", "-q", "a"): True}))
        fedora.install(["a", "b"])
        self.assertEqual(recorder.calls, [("cmd", ("dnf", "install", "-y", "-q", "b"), True, None)])
        self.assertIn("pacote instalado: b", self.out.getvalue())

    def test_install_nothing_to_do(self) -> None:
        recorder = self.use(Recorder({("rpm", "-q", "a"): True}))
        fedora.install(["a"])
        fedora.uninstall(["b"])
        self.assertEqual(recorder.calls, [])
        self.assertEqual(self.out.getvalue(), "")

    def test_uninstall(self) -> None:
        recorder = self.use(Recorder({("rpm", "-q", "a"): True, ("rpm", "-q", "b"): True}))
        fedora.uninstall(["a", "b"])
        self.assertEqual(recorder.commands(), [("dnf", "remove", "-y", "-q", "a", "b")])
        self.assertIn("pacotes removidos: a, b", self.out.getvalue())

    def test_repo(self) -> None:
        recorder = self.use(Recorder())
        response = mock.MagicMock()
        response.__enter__.return_value.read.return_value = b"[repo]\nname=teste\n"
        with mock.patch.object(fedora, "REPOS", self.root), mock.patch("urllib.request.urlopen", return_value=response):
            fedora.add_repo("teste", "https://exemplo/teste.repo")
        self.assertEqual(recorder.calls, [("cmd", ("tee", str(self.root / "teste.repo")), True, "[repo]\nname=teste\n")])
        (self.root / "teste.repo").write_text("x")
        with mock.patch.object(fedora, "REPOS", self.root):
            fedora.add_repo("teste", "https://exemplo/teste.repo")
            fedora.remove_repo("teste")
            fedora.remove_repo("outro")
        self.assertEqual(recorder.commands()[1:], [("rm", "-f", str(self.root / "teste.repo"))])

    def test_repo_download_error(self) -> None:
        self.use(Recorder())
        with mock.patch.object(fedora, "REPOS", self.root), mock.patch("urllib.request.urlopen", side_effect=OSError("sem rede")):
            with self.assertRaises(SystemExit):
                fedora.add_repo("teste", "https://exemplo/teste.repo")
        self.assertIn("não foi possível baixar o repositório teste: sem rede", self.err.getvalue())

    def test_services(self) -> None:
        recorder = self.use(Recorder({("systemctl", "is-active", "-q", "ligado"): True, ("systemctl", "is-enabled", "-q", "ligado"): True}))
        fedora.service_enable("ligado")
        fedora.service_disable("parado")
        fedora.service_enable("parado")
        fedora.service_disable("ligado")
        self.assertEqual(recorder.commands(), [
            ("systemctl", "enable", "--now", "-q", "parado"),
            ("systemctl", "disable", "--now", "-q", "ligado"),
        ])

    def test_firewall(self) -> None:
        active = {("systemctl", "is-active", "-q", "firewalld"): True}
        lists = {("firewall-cmd", "--list-ports"): "1025-65535/udp 80/tcp", ("firewall-cmd", "--list-services"): "ssh"}
        recorder = self.use(Recorder(active, lists))
        fedora.firewall_open(["41641/udp", "80/tcp", "ssh", "samba"])
        fedora.firewall_close(["8080/tcp", "80/tcp"])
        self.assertEqual(recorder.commands(), [
            ("firewall-cmd", "-q", "--permanent", "--add-port=41641/udp"),
            ("firewall-cmd", "-q", "--permanent", "--add-service=samba"),
            ("firewall-cmd", "-q", "--reload"),
            ("firewall-cmd", "-q", "--permanent", "--remove-port=80/tcp"),
            ("firewall-cmd", "-q", "--reload"),
        ])
        self.assertIn("liberado no firewall: 41641/udp, samba", self.out.getvalue())
        self.assertIn("fechado no firewall: 80/tcp", self.out.getvalue())

    def test_firewall_allowed(self) -> None:
        active = {("systemctl", "is-active", "-q", "firewalld"): True}
        lists = {("firewall-cmd", "--list-ports"): "1025-65535/udp 80/tcp", ("firewall-cmd", "--list-services"): "ssh"}
        self.use(Recorder(active, lists))
        self.assertTrue(fedora.firewall_allowed("41641/udp"))
        self.assertTrue(fedora.firewall_allowed("80/tcp"))
        self.assertFalse(fedora.firewall_allowed("41641/tcp"))
        self.assertTrue(fedora.firewall_allowed("ssh"))
        self.assertFalse(fedora.firewall_allowed("samba"))

    def test_firewall_inactive(self) -> None:
        recorder = self.use(Recorder())
        fedora.firewall_open(["41641/udp"])
        fedora.firewall_masquerade(True)
        self.assertEqual(recorder.calls, [])

    def test_masquerade(self) -> None:
        recorder = self.use(Recorder({("systemctl", "is-active", "-q", "firewalld"): True}))
        fedora.firewall_masquerade(False)
        fedora.firewall_masquerade(True)
        self.assertEqual(recorder.commands(), [
            ("firewall-cmd", "-q", "--permanent", "--add-masquerade"),
            ("firewall-cmd", "-q", "--reload"),
        ])

    def test_sysctl(self) -> None:
        recorder = self.use(Recorder())
        path = self.root / "99-astroverso-teste.conf"
        with mock.patch.object(fedora, "SYSCTL", self.root):
            fedora.sysctl_set("teste", {"net.ipv4.ip_forward": "1"})
            path.write_text("net.ipv4.ip_forward = 1\n")
            fedora.sysctl_set("teste", {"net.ipv4.ip_forward": "1"})
            fedora.sysctl_remove("teste")
            path.unlink()
            fedora.sysctl_remove("teste")
        self.assertEqual(recorder.calls, [
            ("cmd", ("tee", str(path)), True, "net.ipv4.ip_forward = 1\n"),
            ("cmd", ("sysctl", "-q", "-p", str(path)), True, None),
            ("cmd", ("rm", "-f", str(path)), True, None),
            ("cmd", ("sysctl", "-q", "--system"), True, None),
        ])


if __name__ == "__main__":
    unittest.main()
