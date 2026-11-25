import tempfile
import unittest
from pathlib import Path
from unittest import mock

from kit import docs


def fake_git(remote: str, branch: str = "main", root: str = ""):
    def capture(args, **_):
        command = tuple(args[3:])
        return {
            ("rev-parse", "--show-toplevel"): root,
            ("remote", "get-url", "origin"): remote,
            ("symbolic-ref", "--short", "-q", "HEAD"): branch,
        }[command]

    def succeeds(args, **_):
        return bool(capture(args))

    return capture, succeeds


class DocsTest(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.page = self.root / "apps" / "rede" / "docs" / "guia.md"
        self.page.parent.mkdir(parents=True)
        self.page.write_text("# Guia\n\n## Criar o token\n\n```\n## não é título\n```\n\n### Reservar o IP e apontar o DNS\n")

    def link(self, remote: str, branch: str = "main", anchor: str = "") -> str:
        capture, succeeds = fake_git(remote, branch, str(self.root) if remote else "")
        with mock.patch.object(docs.run, "capture", side_effect=capture), \
                mock.patch.object(docs.run, "succeeds", side_effect=succeeds):
            return docs.link(self.page, anchor)

    def test_github_remotes(self) -> None:
        expected = "https://github.com/dono/repo/blob/main/apps/rede/docs/guia.md#criar-o-token"
        for remote in ("git@github.com:dono/repo.git", "ssh://git@github.com/dono/repo.git",
                       "https://github.com/dono/repo", "https://github.com/dono/repo.git"):
            self.assertEqual(self.link(remote, anchor="criar-o-token"), expected, remote)

    def test_branch_and_detached(self) -> None:
        self.assertIn("/blob/teste/apps/", self.link("git@github.com:dono/repo.git", branch="teste"))
        self.assertIn("/blob/main/apps/", self.link("git@github.com:dono/repo.git", branch=""))

    def test_local_fallback(self) -> None:
        self.assertEqual(self.link("", anchor="x"), f"{self.page}#x")
        self.assertEqual(self.link("git@gitlab.com:dono/repo.git"), str(self.page))

    def test_anchors(self) -> None:
        self.assertEqual(docs.anchors(self.page), {"guia", "criar-o-token", "reservar-o-ip-e-apontar-o-dns"})
        self.assertEqual(docs.slug("Direto ou por relay"), "direto-ou-por-relay")
        self.assertEqual(docs.slug("Quando o **cadeado** demora?"), "quando-o-cadeado-demora")
        self.assertEqual(docs.slug("Reservar o IP: o primeiro passo"), "reservar-o-ip-o-primeiro-passo")


if __name__ == "__main__":
    unittest.main()
