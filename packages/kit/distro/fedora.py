from __future__ import annotations

import re
import urllib.request
from collections.abc import Mapping, Sequence
from pathlib import Path

from kit import run, ui

REPOS = Path("/etc/yum.repos.d")
SYSCTL = Path("/etc/sysctl.d")
RESOLVED = Path("/etc/systemd/resolved.conf.d")
SYSTEMD = Path("/etc/systemd/system")
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


def _firewall_read() -> None:
    run.sudo_prepare("ler a configuração do firewall")


def _listed(kind: str) -> set[str]:
    _firewall_read()
    return set(run.capture(["firewall-cmd", f"--list-{kind}s"], sudo=True).split())


def _query(*args: str) -> bool:
    _firewall_read()
    return run.succeeds(["firewall-cmd", "-q", *args], sudo=True)


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


def _covers(rule: str, item: str) -> bool:
    if rule == item:
        return True
    span, _, protocol = rule.partition("/")
    number, _, item_protocol = item.partition("/")
    if protocol != item_protocol or "-" not in span or not number.isdigit():
        return False
    start, _, end = span.partition("-")
    return int(start) <= int(number) <= int(end)


def firewall_allowed(item: str) -> bool:
    if not _firewalld():
        return True
    kind = _kind(item)
    return any(_covers(rule, item) for rule in _listed(kind)) if kind == "port" else item in _listed(kind)


def firewall_masquerade(enabled: bool) -> None:
    if not _firewalld() or _query("--query-masquerade") == enabled:
        return
    run.cmd(["firewall-cmd", "-q", "--permanent", f"--{'add' if enabled else 'remove'}-masquerade"], sudo=True)
    run.cmd(["firewall-cmd", "-q", "--reload"], sudo=True)
    ui.ok(f"masquerade {'ligado' if enabled else 'desligado'} no firewall")


def _resolver_path(name: str) -> Path:
    return RESOLVED / f"99-astroverso-{name}.conf"


def resolver_route(name: str, domain: str, server: str) -> None:
    path = _resolver_path(name)
    content = f"[Resolve]\nDNS={server}\nDomains=~{domain}\n"
    try:
        if path.read_text() == content:
            return
    except OSError:
        pass
    run.cmd(["mkdir", "-p", str(RESOLVED)], sudo=True)
    _write(path, content)
    run.cmd(["systemctl", "restart", "systemd-resolved"], sudo=True)
    ui.ok(f"esta máquina pergunta a {server} pelos nomes de {domain}")


def resolver_route_remove(name: str) -> None:
    path = _resolver_path(name)
    if not path.exists():
        return
    run.cmd(["rm", "-f", str(path)], sudo=True)
    run.cmd(["systemctl", "restart", "systemd-resolved"], sudo=True)
    ui.ok(f"ajuste de DNS {path.name} removido")


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


def sysctl_has(name: str, values: Mapping[str, str]) -> bool:
    try:
        return _sysctl_path(name).read_text() == "".join(f"{key} = {value}\n" for key, value in values.items())
    except OSError:
        return False


def resolver_route_has(name: str, domain: str, server: str) -> bool:
    try:
        return _resolver_path(name).read_text() == f"[Resolve]\nDNS={server}\nDomains=~{domain}\n"
    except OSError:
        return False


def sysctl_remove(name: str) -> None:
    path = _sysctl_path(name)
    if not path.exists():
        return
    run.cmd(["rm", "-f", str(path)], sudo=True)
    run.cmd(["sysctl", "-q", "--system"], sudo=True)
    ui.ok(f"ajuste do sistema {path.name} removido (volta ao padrão por completo depois de reiniciar)")


def file_put(path: Path, content: str, mode: int | None = None) -> bool:
    try:
        if path.read_text() == content:
            return False
    except OSError:
        pass
    run.cmd(["mkdir", "-p", str(path.parent)], sudo=True)
    _write(path, content)
    if mode is not None:
        run.cmd(["chmod", f"{mode:o}", str(path)], sudo=True)
    return True


def file_drop(path: Path) -> bool:
    if not path.exists():
        return False
    run.cmd(["rm", "-f", str(path)], sudo=True)
    return True


def _unit_state(name: str) -> str:
    _, output = run.output(["systemctl", "is-enabled", name], timeout=10)
    return output.strip()


def units_masked(names: Sequence[str]) -> bool:
    return bool(names) and all(_unit_state(name) == "masked" for name in names)


def units_mask(names: Sequence[str]) -> None:
    run.cmd(["systemctl", "mask", "-q", *names], sudo=True)


def units_unmask(names: Sequence[str]) -> None:
    run.cmd(["systemctl", "unmask", "-q", *names], sudo=True)


def unit_install(name: str, content: str) -> None:
    if file_put(SYSTEMD / name, content):
        run.cmd(["systemctl", "daemon-reload"], sudo=True)
    if not _service_enabled(name):
        run.cmd(["systemctl", "enable", "-q", name], sudo=True)
    run.cmd(["systemctl", "restart", name], sudo=True)


def unit_remove(name: str) -> None:
    if not (SYSTEMD / name).exists():
        return
    run.succeeds(["systemctl", "disable", "--now", "-q", name], sudo=True)
    file_drop(SYSTEMD / name)
    run.cmd(["systemctl", "daemon-reload"], sudo=True)


def unit_enabled(name: str) -> bool:
    return (SYSTEMD / name).exists() and _service_enabled(name)


def daemon_reload() -> None:
    run.cmd(["systemctl", "daemon-reload"], sudo=True)


def reload_service(name: str) -> None:
    if not run.succeeds(["systemctl", "reload", name], sudo=True):
        run.cmd(["systemctl", "kill", "-s", "HUP", name], sudo=True)


def _rich(source: str, service: str) -> str:
    return f'rule family="ipv4" source address="{source}" service name="{service}" accept'


def firewall_limit(service: str, sources: Sequence[str]) -> None:
    if not _firewalld():
        return
    for source in sources:
        if not _query("--query-rich-rule", _rich(source, service)):
            run.cmd(["firewall-cmd", "-q", "--permanent", "--add-rich-rule", _rich(source, service)], sudo=True)
    if service in _listed("service"):
        run.cmd(["firewall-cmd", "-q", "--permanent", "--remove-service", service], sudo=True)
    run.cmd(["firewall-cmd", "-q", "--reload"], sudo=True)
    ui.ok(f"{service} no firewall só de: {', '.join(sources)}")


def firewall_unlimit(service: str, sources: Sequence[str]) -> None:
    if not _firewalld():
        return
    if service not in _listed("service"):
        run.cmd(["firewall-cmd", "-q", "--permanent", "--add-service", service], sudo=True)
    for source in sources:
        if _query("--query-rich-rule", _rich(source, service)):
            run.cmd(["firewall-cmd", "-q", "--permanent", "--remove-rich-rule", _rich(source, service)], sudo=True)
    run.cmd(["firewall-cmd", "-q", "--reload"], sudo=True)
    ui.ok(f"{service} liberado no firewall para qualquer origem")


def firewall_limited(service: str, sources: Sequence[str]) -> bool:
    if not _firewalld():
        return False
    return service not in _listed("service") and all(
        _query("--query-rich-rule", _rich(source, service)) for source in sources
    )


AUTOMATIC_CONF = Path("/etc/dnf/automatic.conf")
AUTOMATIC_TIMER = "dnf5-automatic.timer"
AUTOMATIC_SERVICE = "dnf5-automatic.service"
AUTOMATIC_TEXT = (
    "# Gerado pelo Astroverso (app system): aplica as atualizações sozinho, sem reiniciar.\n"
    "[commands]\napply_updates = yes\nreboot = never\n\n[emitters]\nemit_via = stdio\n"
)


def auto_updates_active() -> bool:
    try:
        written = AUTOMATIC_CONF.read_text() == AUTOMATIC_TEXT
    except OSError:
        written = False
    return written and unit_enabled(AUTOMATIC_TIMER)


def auto_updates_on() -> None:
    install(["dnf5-plugin-automatic"])
    file_put(AUTOMATIC_CONF, AUTOMATIC_TEXT, 0o644)
    service_enable(AUTOMATIC_TIMER)


def auto_updates_off() -> None:
    service_disable(AUTOMATIC_TIMER)
    if file_drop(AUTOMATIC_CONF):
        ui.ok("atualização automática desligada")


def auto_updates_last() -> tuple[str, str]:
    code, output = run.output(["systemctl", "show", AUTOMATIC_SERVICE, "-p", "Result", "-p", "ExecMainStartTimestamp", "--value"], timeout=10)
    lines = output.strip().splitlines() if code == 0 else []
    return (lines[0], lines[1]) if len(lines) >= 2 else ("", "")


def reboot_pending() -> bool:
    return run.output(["dnf", "-q", "-C", "needs-restarting"], timeout=120)[0] == 1
