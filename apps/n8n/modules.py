from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from kit import config, container, run, ui

FOLDER = Path(__file__).with_name("modules")
PREFIX = "astroverso-n8n-"
RESERVED = ("runners",)
PORT = 8080
SKIP = {"tests", "__pycache__", "README.md"}


@dataclass(frozen=True)
class Module:
    name: str
    path: Path

    @property
    def container(self) -> str:
        return f"{PREFIX}{self.name}"

    @property
    def url(self) -> str:
        return f"http://{self.container}:{PORT}"

    def image(self) -> str:
        return f"localhost/{self.container}:{digest(self.path)}"


def found(folder: Path | None = None) -> list[Module]:
    base = folder or FOLDER
    items = []
    for path in sorted(base.iterdir()) if base.is_dir() else []:
        if path.is_dir() and (path / "Containerfile").is_file():
            if not config.APP.match(path.name) or path.name in RESERVED:
                ui.warn(f"módulo ignorado, nome inválido: {path.name} (letras minúsculas, números e -)")
                continue
            items.append(Module(path.name, path))
    return items


def digest(path: Path) -> str:
    total = hashlib.sha256()
    for item in sorted(path.rglob("*")):
        relative = item.relative_to(path)
        if item.is_file() and not SKIP & set(relative.parts):
            total.update(str(relative).encode() + b"\0" + item.read_bytes() + b"\0")
    return total.hexdigest()[:12]


def spec(module: Module) -> container.Container:
    return container.Container(
        name=module.container,
        image=module.image(),
        description=f"Astroverso n8n: módulo {module.name} (API para as rotinas)",
        environment={"TZ": config.timezone(), "PORT": str(PORT)},
        health=f"python3 -I -c \"import urllib.request; urllib.request.urlopen('http://127.0.0.1:{PORT}/v1/saude', timeout=5)\"",
    )


def _old_images(module: Module) -> list[str]:
    code, output = run.output(["podman", "images", "--format", "{{.Repository}}:{{.Tag}}", f"localhost/{module.container}"])
    return [line for line in output.split() if line != module.image()] if code == 0 else []


def build(module: Module) -> None:
    container.build(module.image(), module.path / "Containerfile")


def start_all(folder: Path | None = None) -> None:
    items = found(folder)
    for module in items:
        build(module)
        container.start(spec(module))
        for image in _old_images(module):
            container.remove_image(image)
    keep = {module.container for module in items}
    for path in sorted(container.quadlets().glob(f"{PREFIX}*.container")):
        name = path.stem
        if name not in keep and name.removeprefix(PREFIX) not in RESERVED:
            ui.info(f"o módulo {name.removeprefix(PREFIX)} saiu do repositório: removendo o container")
            container.remove(name)


def health(module: Module) -> str:
    code, output = run.output(["podman", "inspect", "--format", "{{.State.Health.Status}}", module.container])
    return output.strip() if code == 0 else "parado"
