import tempfile
import unittest
from pathlib import Path
from unittest import mock

from kit import disks

LUKS = "1111aaaa-2222-3333-4444-555566667777"
PLAIN = "9999bbbb-8888-7777-6666-555544443333"
OPTIONS = "nofail,x-udisks-auth,context=system_u:object_r:container_file_t:s0"
FSTAB = "\n".join([
    "UUID=raiz / xfs defaults 0 0",
    f"{disks.MARK}{LUKS}",
    f"UUID=dentro /srv/dados ext4 {OPTIONS},x-systemd.requires=systemd-cryptsetup@luks\\x2d{LUKS.replace('-', chr(92) + 'x2d')}.service 0 2",
    "UUID=outro /mnt/usb ext4 defaults 0 0",
    f"{disks.MARK}{PLAIN}",
    "# linha que o udisks pôs no meio",
    f"UUID={PLAIN} /srv/jogos ntfs3 {OPTIONS} 0 0",
    f"UUID=solto /srv/perdido ext4 {OPTIONS} 0 0",
    "",
])


class DisksTest(unittest.TestCase):
    def test_blocks_pair_by_uuid_even_when_separated(self) -> None:
        self.assertEqual([uuid for uuid, _ in disks.blocks(FSTAB, "fstab")], [LUKS, PLAIN])
        self.assertEqual(disks.orphans(FSTAB, "fstab"), [f"UUID=solto /srv/perdido ext4 {OPTIONS} 0 0"])
        self.assertTrue(disks.owns(LUKS, f"x{disks.escaped(LUKS)}"))
        self.assertFalse(disks.ours("fstab", f"# UUID=a /srv/x ext4 {OPTIONS} 0 0"))
        self.assertTrue(disks.ours("crypttab", f"luks-{LUKS} UUID={LUKS} none tpm2-device=auto,headless=true"))

    def test_mounts_and_containing(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "fstab"
            path.write_text(FSTAB)
            found = disks.mounts(path)
            self.assertEqual([(disk.name, disk.fstype) for disk in found], [("dados", "ext4"), ("jogos", "ntfs3")])
            self.assertEqual(disks.mounts(Path(folder) / "nada"), [])
            with mock.patch.object(disks, "mounts", return_value=found):
                self.assertEqual(disks.containing(Path("/srv/dados/fotos/2026")).name, "dados")
                self.assertIsNone(disks.containing(Path("/srv/dadosx")))
                with mock.patch.object(disks, "responds", return_value=False):
                    self.assertFalse(disks.available(Path("/srv/jogos/roms")))
                    self.assertTrue(disks.available(Path("/home/eu")))

    def test_responds(self) -> None:
        with mock.patch.object(disks.run, "output", side_effect=[(1, "")]):
            self.assertFalse(disks.responds(Path("/srv/dados")))
        with mock.patch.object(disks.run, "output", side_effect=[(0, "/dev/sdb1\n"), (0, "")]):
            self.assertTrue(disks.responds(Path("/srv/dados")))
        with mock.patch.object(disks.run, "output", side_effect=[(0, "/dev/sdb1\n"), (124, "")]):
            self.assertFalse(disks.responds(Path("/srv/dados")))


if __name__ == "__main__":
    unittest.main()
