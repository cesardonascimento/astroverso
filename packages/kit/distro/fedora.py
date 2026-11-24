from __future__ import annotations

import re
import urllib.request
from collections.abc import Mapping, Sequence
from pathlib import Path

from kit import run, ui

REPOS = Path("/etc/yum.repos.d")
SYSCTL = Path("/etc/sysctl.d")
PORT = re.compile(r"^\d+(-\d+)?/(tcp|udp|sctp|dccp)$")


def _write(path: Path, content: str) -> None:
    run.cmd(["tee", str(path)], sudo=True, input=content, quiet=True)


def _plural(items: Sequence[str]) -> str:
    return "s" if len(items) > 1 else ""


def installed(package: str) -> bool:
    return run.succeeds(["rpm", "-q", package])


def install(packages: Sequence[str]) -> None:
    missing = [package for package in packages if not installed(package)]
    if missing:
        run.cmd(["dnf", "install", "-y", "-q", *missing], sudo=True)
        ui.ok(f"pacote{_plural(missing)} instalado{_plural(missing)}: {', '.join(missing)}")


def uninstall(packages: Sequence[str]) -> None:
    present = [package for package in packages if installed(package)]
    if present:
        run.cmd(["dnf", "remove", "-y", "-q", *present], sudo=True)
        ui.ok(f"pacote{_plural(present)} removido{_plural(present)}: {', '.join(present)}")


def add_repo(name: str, url: str) -> None:
    path = REPOS / f"{name}.repo"
    if path.exists():
        return
    try:
        with urllib.request.urlopen(url, timeout=30) as response:
            content = response.read().decode()
    except (OSError, UnicodeDecodeError) as problem:
        ui.fail(f"não foi possível baixar o repositório {name}: {problem}")
    _write(path, content)
    ui.ok(f"repositório {name} adicionado")


def remove_repo(name: str) -> None:
    path = REPOS / f"{name}.repo"
    if path.exists():
        run.cmd(["rm", "-f", str(path)], sudo=True)
        ui.ok(f"repositório {name} removido")


def service_active(name: str) -> bool:
    return run.succeeds(["systemctl", "is-active", "-q", name])


def _service_enabled(name: str) -> bool:
    return run.succeeds(["systemctl", "is-enabled", "-q", name])


def service_enable(name: str) -> None:
    if service_active(name) and _service_enabled(name):
        return
    run.cmd(["systemctl", "enable", "--now", "-q", name], sudo=True)
    ui.ok(f"serviço {name} ligado")


def service_disable(name: str) -> None:
    if not service_active(name) and not _service_enabled(name):
        return
    run.cmd(["systemctl", "disable", "--now", "-q", name], sudo=True)
    ui.ok(f"serviço {name} desligado")


def _firewalld() -> bool:
    return service_active("firewalld")


def _kind(item: str) -> str:
    return "port" if PORT.match(item) else "service"


def _listed(kind: str) -> set[str]:
    return set(run.capture(["firewall-cmd", f"--list-{kind}s"]).split())


def _firewall_change(items: Sequence[str], add: bool) -> list[str]:
    changed: list[str] = []
    lists = {"port": _listed("port"), "service": _listed("service")}
    for item in items:
        kind = _kind(item)
        if (item in lists[kind]) == add:
            continue
        run.cmd(["firewall-cmd", "-q", "--permanent", f"--{'add' if add else 'remove'}-{kind}={item}"], sudo=True)
        changed.append(item)
    if changed:
        run.cmd(["firewall-cmd", "-q", "--reload"], sudo=True)
    return changed


def firewall_open(items: Sequence[str]) -> None:
    if _firewalld() and (changed := _firewall_change(items, True)):
        ui.ok(f"liberado no firewall: {', '.join(changed)}")


def firewall_close(items: Sequence[str]) -> None:
    if _firewalld() and (changed := _firewall_change(items, False)):
        ui.ok(f"fechado no firewall: {', '.join(changed)}")


def firewall_masquerade(enabled: bool) -> None:
    if not _firewalld() or run.succeeds(["firewall-cmd", "-q", "--query-masquerade"]) == enabled:
        return
    run.cmd(["firewall-cmd", "-q", "--permanent", f"--{'add' if enabled else 'remove'}-masquerade"], sudo=True)
    run.cmd(["firewall-cmd", "-q", "--reload"], sudo=True)
    ui.ok(f"masquerade {'ligado' if enabled else 'desligado'} no firewall")


def _sysctl_path(name: str) -> Path:
    return SYSCTL / f"99-astroverso-{name}.conf"


def sysctl_set(name: str, values: Mapping[str, str]) -> None:
    path = _sysctl_path(name)
    content = "".join(f"{key} = {value}\n" for key, value in values.items())
    try:
        if path.read_text() == content:
            return
    except OSError:
        pass
    _write(path, content)
    run.cmd(["sysctl", "-q", "-p", str(path)], sudo=True)
    ui.ok(f"ajuste do sistema aplicado: {', '.join(f'{key} = {value}' for key, value in values.items())}")


def sysctl_remove(name: str) -> None:
    path = _sysctl_path(name)
    if not path.exists():
        return
    run.cmd(["rm", "-f", str(path)], sudo=True)
    run.cmd(["sysctl", "-q", "--system"], sudo=True)
    ui.ok(f"ajuste do sistema {path.name} removido (volta ao padrão por completo depois de reiniciar)")
