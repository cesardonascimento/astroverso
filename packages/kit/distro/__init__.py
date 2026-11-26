from __future__ import annotations

import importlib
from collections.abc import Mapping, Sequence
from pathlib import Path
from types import ModuleType

from kit import ui

OS_RELEASE = Path("/etc/os-release")
SUPPORTED: tuple[str, ...] = ("fedora",)

_backend: ModuleType | None = None


def release(path: Path = OS_RELEASE) -> dict[str, str]:
    values: dict[str, str] = {}
    try:
        lines = path.read_text().splitlines()
    except OSError:
        return values
    for line in lines:
        key, sep, value = line.partition("=")
        if sep:
            values[key.strip()] = value.strip().strip("\"'")
    return values


def backend(path: Path = OS_RELEASE) -> ModuleType:
    global _backend
    if _backend is None:
        info = release(path)
        name = info.get("ID", "").lower()
        if name not in SUPPORTED:
            ui.fail(f"distribuição não suportada: {info.get('PRETTY_NAME') or name or 'desconhecida'}")
        _backend = importlib.import_module(f"kit.distro.{name}")
    return _backend


def check() -> None:
    backend()


def installed(package: str) -> bool:
    return bool(backend().installed(package))


def install(packages: Sequence[str]) -> None:
    backend().install(packages)


def uninstall(packages: Sequence[str]) -> None:
    backend().uninstall(packages)


def add_repo(name: str, url: str) -> None:
    backend().add_repo(name, url)


def remove_repo(name: str) -> None:
    backend().remove_repo(name)


def service_active(name: str) -> bool:
    return bool(backend().service_active(name))


def service_enable(name: str) -> None:
    backend().service_enable(name)


def service_disable(name: str) -> None:
    backend().service_disable(name)


def firewall_open(items: Sequence[str]) -> None:
    backend().firewall_open(items)


def firewall_close(items: Sequence[str]) -> None:
    backend().firewall_close(items)


def firewall_allowed(item: str) -> bool:
    return bool(backend().firewall_allowed(item))


def firewall_masquerade(enabled: bool) -> None:
    backend().firewall_masquerade(enabled)


def resolver_route(name: str, domain: str, server: str) -> None:
    backend().resolver_route(name, domain, server)


def resolver_route_remove(name: str) -> None:
    backend().resolver_route_remove(name)


def sysctl_set(name: str, values: Mapping[str, str]) -> None:
    backend().sysctl_set(name, values)


def sysctl_remove(name: str) -> None:
    backend().sysctl_remove(name)


def file_put(path: Path, content: str, mode: int | None = None) -> bool:
    return bool(backend().file_put(path, content, mode))


def file_drop(path: Path) -> bool:
    return bool(backend().file_drop(path))


def units_masked(names: Sequence[str]) -> bool:
    return bool(backend().units_masked(names))


def units_mask(names: Sequence[str]) -> None:
    backend().units_mask(names)


def units_unmask(names: Sequence[str]) -> None:
    backend().units_unmask(names)


def unit_install(name: str, content: str) -> None:
    backend().unit_install(name, content)


def unit_remove(name: str) -> None:
    backend().unit_remove(name)


def unit_enabled(name: str) -> bool:
    return bool(backend().unit_enabled(name))


def daemon_reload() -> None:
    backend().daemon_reload()


def reload_service(name: str) -> None:
    backend().reload_service(name)


def firewall_limit(service: str, sources: Sequence[str]) -> None:
    backend().firewall_limit(service, sources)


def firewall_unlimit(service: str, sources: Sequence[str]) -> None:
    backend().firewall_unlimit(service, sources)


def firewall_limited(service: str, sources: Sequence[str]) -> bool:
    return bool(backend().firewall_limited(service, sources))


def sysctl_has(name: str, values: Mapping[str, str]) -> bool:
    return bool(backend().sysctl_has(name, values))


def resolver_route_has(name: str, domain: str, server: str) -> bool:
    return bool(backend().resolver_route_has(name, domain, server))


def auto_updates_active() -> bool:
    return bool(backend().auto_updates_active())


def auto_updates_on() -> None:
    backend().auto_updates_on()


def auto_updates_off() -> None:
    backend().auto_updates_off()


def auto_updates_last() -> tuple[str, str]:
    return backend().auto_updates_last()


def reboot_pending() -> bool:
    return bool(backend().reboot_pending())
