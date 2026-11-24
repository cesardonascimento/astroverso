import io
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from kit import net, ui


def fake_socket(address: str | None) -> mock.MagicMock:
    probe = mock.MagicMock()
    probe.__enter__.return_value = probe
    if address is None:
        probe.connect.side_effect = OSError("Network is unreachable")
    probe.getsockname.return_value = (address, 40000)
    return mock.MagicMock(return_value=probe)


class NetTest(unittest.TestCase):
    def setUp(self) -> None:
        ui.set_app("teste")
        self.err = io.StringIO()
        patch = mock.patch.object(sys, "stderr", self.err)
        patch.start()
        self.addCleanup(patch.stop)

    def test_lan_ip(self) -> None:
        with mock.patch("socket.socket", fake_socket("192.168.0.10")):
            self.assertEqual(net.lan_ip(), "192.168.0.10")

    def test_tailscale_exit_node(self) -> None:
        with mock.patch("socket.socket", fake_socket("100.101.102.103")), self.assertRaises(SystemExit):
            net.lan_ip()
        self.assertIn("saída é pelo 100.101.102.103", self.err.getvalue())

    def test_without_network(self) -> None:
        with mock.patch("socket.socket", fake_socket(None)), self.assertRaises(SystemExit):
            net.lan_ip()
        self.assertIn("sem rede", self.err.getvalue())

    def test_real_machine(self) -> None:
        self.assertNotIn(".", net.hostname())
        self.assertRegex(net.lan_ip(), r"^\d+\.\d+\.\d+\.\d+$")


if __name__ == "__main__":
    unittest.main()
