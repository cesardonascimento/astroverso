import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "packages"))

from kit import docs

FOLDER = ROOT / "apps" / "vault"
LINK = re.compile(r'docs\.link\(DOCS / "([^"]+)"(?:, "([^"]+)")?\)')
RELATIVE = re.compile(r"\]\(([\w-]+\.md)(?:#([^)]+))?\)")


class DocsTest(unittest.TestCase):
    def test_installer_links_exist(self) -> None:
        found = [match for source in FOLDER.glob("*.py") for match in LINK.findall(source.read_text())]
        self.assertGreaterEqual(len(found), 1)
        for name, anchor in found:
            target = FOLDER / "docs" / name
            self.assertTrue(target.is_file(), name)
            if anchor:
                self.assertIn(anchor, docs.anchors(target), f"{name}#{anchor}")

    def test_links_between_docs_exist(self) -> None:
        for page in [*(FOLDER / "docs").glob("*.md"), FOLDER / "README.md"]:
            for name, anchor in RELATIVE.findall(page.read_text()):
                target = page.parent / name
                if not target.is_file():
                    target = FOLDER / "docs" / name
                self.assertTrue(target.is_file(), f"{page.name} → {name}")
                if anchor:
                    self.assertIn(anchor, docs.anchors(target), f"{page.name} → {name}#{anchor}")


if __name__ == "__main__":
    unittest.main()
