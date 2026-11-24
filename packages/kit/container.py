from __future__ import annotations

import getpass
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from kit import distro, run, ui

NETWORK = "astroverso"


@dataclass(frozen=True)
class Volume:
    source: Path
    target: str
    options: str = "Z"


@dataclass(frozen=True)
class Container:
    name: str
    image: str
    description: str
    network: str = NETWORK
    volumes: Sequence[Volume] = ()
    ports: Sequence[str] = ()
    environment: Mapping[str, str] = field(default_factory=dict)
    command: Sequence[str] = ()
    health: str = ""


def quadlets() -> Path:
    return Path.home() / ".config" / "containers" / "systemd"


def unit(name: str) -> str:
    return f"{name}.service"


def _quote(value: str) -> str:
    if "\n" in value:
        ui.fail(f"valor com quebra de linha não é aceito num container: {value!r}")
    text = value.replace("%", "%%").replace("$", "$$")
    if any(char.isspace() or char in "\"'\\;" for char in text):
        return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return text


def render(spec: Container) -> str:
    network = "host" if spec.network == "host" else f"{spec.network}.network"
    lines = [
        "[Unit]",
        f"Description={spec.description}",
        "",
        "[Container]",
        f"ContainerName={spec.name}",
        f"Image={spec.image}",
        f"Network={network}",
    ]
    lines += [f"Volume={_quote(f'{volume.source}:{volume.target}:{volume.options}')}" for volume in spec.volumes]
    lines += [f"PublishPort={_quote(port)}" for port in spec.ports]
    lines += [f"Environment={_quote(f'{key}={value}')}" for key, value in spec.environment.items()]
    if spec.command:
        lines.append(f"Exec={' '.join(_quote(part) for part in spec.command)}")
    if spec.health:
        lines += [f"HealthCmd={_quote(spec.health)}", "HealthInterval=30s", "HealthStartPeriod=30s", "HealthRetries=3"]
    lines += ["", "[Service]", "Restart=always", "TimeoutStartSec=600", "", "[Install]", "WantedBy=default.target", ""]
    return "\n".join(lines)


def _write(path: Path, content: str) -> bool:
    try:
        if path.read_text() == content:
            return False
    except FileNotFoundError:
        pass
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(content)
    temporary.replace(path)
    return True


def _systemctl(*args: str, quiet: bool = True) -> None:
    run.cmd(["systemctl", "--user", *args], quiet=quiet)


def prepare() -> None:
    distro.install(["podman"])
    user = getpass.getuser()
    if run.capture(["loginctl", "show-user", user, "-p", "Linger", "--value"]) != "yes":
        run.cmd(["loginctl", "enable-linger", user], sudo=True)
        ui.ok("containers liberados para subir no boot, sem ninguém logado")


def pull(image: str) -> None:
    if run.succeeds(["podman", "image", "exists", image]):
        return
    ui.info(f"baixando {image}...")
    run.cmd(["podman", "pull", "-q", image], quiet=True, timeout=1800)
    ui.ok(f"imagem {image} baixada")


def start(spec: Container, timeout: float = 180) -> None:
    pull(spec.image)
    changed = _write(quadlets() / f"{spec.name}.container", render(spec))
    if spec.network != "host":
        _write(quadlets() / f"{spec.network}.network", f"[Network]\nNetworkName={spec.network}\n")
    _systemctl("daemon-reload")
    if changed or not active(spec.name):
        _systemctl("restart", unit(spec.name))
    wait(spec.name, bool(spec.health), timeout)
    ui.ok(f"container {spec.name} no ar")


def active(name: str) -> bool:
    return run.succeeds(["systemctl", "--user", "is-active", "-q", unit(name)])


def _state(name: str, health: bool) -> str:
    template = "{{.State.Health.Status}}" if health else "{{.State.Status}}"
    if not run.succeeds(["podman", "container", "exists", name]):
        return ""
    return run.capture(["podman", "inspect", "-f", template, name])


def wait(name: str, health: bool, timeout: float = 180) -> None:
    goal = "healthy" if health else "running"
    end = time.monotonic() + timeout
    state = ""
    while time.monotonic() < end:
        state = _state(name, health)
        if state == goal:
            return
        if state == "unhealthy":
            break
        time.sleep(1)
    logs = run.capture(["journalctl", "--user", "-u", unit(name), "-n", "20", "--no-pager", "-o", "cat"])
    if logs:
        ui.prefixed(logs)
    ui.fail(f"o container {name} não ficou pronto (estado: {state or 'não existe'})")


def remove(name: str, image: str | None = None) -> None:
    path = quadlets() / f"{name}.container"
    lines = path.read_text().splitlines() if path.exists() else []
    network = next((line.split("=", 1)[1] for line in lines if line.startswith("Network=")), "")
    if active(name):
        _systemctl("stop", unit(name))
    run.succeeds(["systemctl", "--user", "reset-failed", unit(name)])
    if path.exists():
        path.unlink()
        _systemctl("daemon-reload")
        ui.ok(f"container {name} removido")
    if image and run.succeeds(["podman", "image", "exists", image]):
        run.cmd(["podman", "rmi", image], quiet=True)
        ui.ok(f"imagem {image} removida")
    if network.endswith(".network"):
        _drop_network(network.removesuffix(".network"))


def _drop_network(name: str) -> None:
    file = quadlets() / f"{name}.network"
    users = [item for item in quadlets().glob("*.container") if f"Network={name}.network" in item.read_text()]
    if users or not file.exists():
        return
    file.unlink()
    _systemctl("daemon-reload")
    if run.succeeds(["podman", "network", "exists", name]):
        run.cmd(["podman", "network", "rm", name], quiet=True)


def once(image: str, args: Sequence[str], input: str | None = None) -> str:
    pull(image)
    return run.capture(["podman", "run", "--rm", "-i", image, *args], input=input)
