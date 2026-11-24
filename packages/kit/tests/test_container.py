import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from kit import container, ui


class FakeRun:
    def __init__(self, states: list[str] | None = None, linger: str = "yes", active: bool = False) -> None:
        self.calls: list[tuple[str, ...]] = []
        self.states = states or ["healthy"]
        self.linger = linger
        self.is_active = active

    def cmd(self, args, sudo=False, input=None, quiet=False, timeout=None):
        self.calls.append(tuple(args))

    def capture(self, args, sudo=False, input=None, timeout=None):
        self.calls.append(tuple(args))
        if args[:2] == ["loginctl", "show-user"]:
            return self.linger
        if args[:2] == ["podman", "inspect"]:
            return self.states.pop(0) if len(self.states) > 1 else self.states[0]
        if args[0] == "journalctl":
            return "linha do log"
        if args[:2] == ["podman", "run"]:
            return "resultado"
        return ""

    def succeeds(self, args, sudo=False, timeout=None):
        self.calls.append(tuple(args))
        if args[:3] == ["systemctl", "--user", "is-active"]:
            return self.is_active
        return args[:3] != ["podman", "image", "exists"] or "existe" in args[-1]


SPEC = container.Container(
    name="astroverso-teste",
    image="docker.io/library/exemplo:1",
    description="Teste",
    volumes=[container.Volume(Path("/dados/conf"), "/conf")],
    ports=["8080:80"],
    environment={"TZ": "America/Sao_Paulo", "FRASE": "com espaço"},
    command=["sh", "-c", "echo $HOME 100% > /x"],
    health="wget -q --spider http://127.0.0.1/",
)


class ContainerTest(unittest.TestCase):
    def setUp(self) -> None:
        ui.set_app("teste")
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.err = io.StringIO()
        for patch in (
            mock.patch.dict(os.environ, {"HOME": self.temp.name}),
            mock.patch.object(sys, "stdout", io.StringIO()),
            mock.patch.object(sys, "stderr", self.err),
            mock.patch.object(container.time, "sleep"),
        ):
            patch.start()
            self.addCleanup(patch.stop)

    def use(self, fake: FakeRun) -> FakeRun:
        patch = mock.patch.object(container, "run", fake)
        patch.start()
        self.addCleanup(patch.stop)
        return fake

    def test_render(self) -> None:
        text = container.render(SPEC)
        self.assertIn("ContainerName=astroverso-teste\n", text)
        self.assertIn("Network=astroverso.network\n", text)
        self.assertIn("Volume=/dados/conf:/conf:Z\n", text)
        self.assertIn("PublishPort=8080:80\n", text)
        self.assertIn('Environment="FRASE=com espaço"\n', text)
        self.assertIn('Exec=sh -c "echo $$HOME 100%% > /x"\n', text)
        self.assertIn('HealthCmd="wget -q --spider http://127.0.0.1/"\n', text)
        self.assertIn("WantedBy=default.target", text)
        host = container.render(container.Container("a", "b", "c", network="host"))
        self.assertIn("Network=host\n", host)

    def test_start(self) -> None:
        fake = self.use(FakeRun(states=["starting", "healthy"]))
        container.start(SPEC)
        files = sorted(path.name for path in container.quadlets().iterdir())
        self.assertEqual(files, ["astroverso-teste.container", "astroverso.network"])
        self.assertEqual((container.quadlets() / "astroverso.network").read_text(), "[Network]\nNetworkName=astroverso\n")
        self.assertIn(("podman", "pull", "-q", SPEC.image), fake.calls)
        self.assertIn(("systemctl", "--user", "daemon-reload"), fake.calls)
        self.assertIn(("systemctl", "--user", "restart", "astroverso-teste.service"), fake.calls)

    def test_start_unchanged_and_active(self) -> None:
        self.use(FakeRun())
        container.start(SPEC)
        fake = self.use(FakeRun(active=True))
        container.start(SPEC)
        self.assertNotIn(("systemctl", "--user", "restart", "astroverso-teste.service"), fake.calls)

    def test_unhealthy(self) -> None:
        self.use(FakeRun(states=["starting", "unhealthy"]))
        with self.assertRaises(SystemExit):
            container.start(SPEC)
        self.assertIn("não ficou pronto (estado: unhealthy)", self.err.getvalue())

    def test_remove(self) -> None:
        self.use(FakeRun())
        container.start(SPEC)
        fake = self.use(FakeRun(active=True))
        container.remove("astroverso-teste", "docker.io/library/existe:1")
        self.assertEqual(list(container.quadlets().iterdir()), [])
        self.assertIn(("systemctl", "--user", "stop", "astroverso-teste.service"), fake.calls)
        self.assertIn(("podman", "rmi", "docker.io/library/existe:1"), fake.calls)
        self.assertIn(("podman", "network", "rm", "astroverso"), fake.calls)

    def test_remove_keeps_shared_network(self) -> None:
        self.use(FakeRun())
        container.start(SPEC)
        other = container.Container("astroverso-outro", "img", "Outro", health="true")
        container.start(other)
        fake = self.use(FakeRun())
        container.remove("astroverso-teste")
        self.assertTrue((container.quadlets() / "astroverso.network").exists())
        self.assertNotIn(("podman", "network", "rm", "astroverso"), fake.calls)

    def test_prepare_linger(self) -> None:
        fake = self.use(FakeRun(linger="no"))
        with mock.patch.object(container, "distro") as distro, mock.patch.object(container.getpass, "getuser", return_value="dono"):
            container.prepare()
        distro.install.assert_called_once_with(["podman"])
        self.assertIn(("loginctl", "enable-linger", "dono"), fake.calls)

    def test_once(self) -> None:
        fake = self.use(FakeRun())
        self.assertEqual(container.once("img:1", ["hash"], input="segredo"), "resultado")
        self.assertIn(("podman", "run", "--rm", "-i", "img:1", "hash"), fake.calls)


if __name__ == "__main__":
    unittest.main()
