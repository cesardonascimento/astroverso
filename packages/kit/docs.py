from __future__ import annotations

import re
from pathlib import Path

from kit import run

REMOTE = re.compile(r"^(?:git@github\.com:|ssh://git@github\.com/|https://github\.com/)([^/]+/[^/]+?)(?:\.git)?/?$")
FENCE = re.compile(r"^\s*(```|~~~)")
HEADING = re.compile(r"^#{1,6}\s+(.+?)\s*#*\s*$")


def _git(folder: Path, *args: str) -> str:
    command = ["git", "-C", str(folder), *args]
    return run.capture(command) if run.succeeds(command) else ""


def link(path: Path, anchor: str = "") -> str:
    path = path.resolve()
    suffix = f"#{anchor}" if anchor else ""
    folder = path.parent
    root = _git(folder, "rev-parse", "--show-toplevel")
    match = REMOTE.match(_git(folder, "remote", "get-url", "origin"))
    if not root or not match:
        return f"{path}{suffix}"
    branch = _git(folder, "symbolic-ref", "--short", "-q", "HEAD") or "main"
    return f"https://github.com/{match[1]}/blob/{branch}/{path.relative_to(Path(root).resolve()).as_posix()}{suffix}"


def slug(heading: str) -> str:
    text = re.sub(r"[`*_]", "", heading).strip().lower()
    return re.sub(r"[^\w\- ]", "", text).replace(" ", "-")


def anchors(path: Path) -> set[str]:
    found: set[str] = set()
    inside = False
    for line in path.read_text().splitlines():
        if FENCE.match(line):
            inside = not inside
            continue
        heading = None if inside else HEADING.match(line)
        if heading:
            found.add(slug(heading[1]))
    return found
