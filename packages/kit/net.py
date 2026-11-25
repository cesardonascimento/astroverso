from __future__ import annotations

import ipaddress
import json
import socket

from kit import run, ui

TAILSCALE = ipaddress.IPv4Network("100.64.0.0/10")
PROBE = ("1.1.1.1", 53)


def lan_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect(PROBE)
            address = probe.getsockname()[0]
    except OSError:
        ui.fail("IP da rede local não encontrado: a máquina está sem rede")
    if ipaddress.IPv4Address(address) in TAILSCALE or address.startswith("127."):
        ui.fail(f"IP da rede local não encontrado: a saída é pelo {address} (Tailscale com exit node?)")
    return address


def hostname() -> str:
    return socket.gethostname().split(".")[0].lower()


def lan_network() -> str:
    address = lan_ip()
    try:
        interfaces = json.loads(run.capture(["ip", "-j", "-4", "addr", "show"]))
    except ValueError:
        interfaces = []
    for interface in interfaces:
        for item in interface.get("addr_info") or []:
            if item.get("local") == address:
                return str(ipaddress.ip_interface(f"{address}/{item.get('prefixlen', 24)}").network)
    return str(ipaddress.ip_interface(f"{address}/24").network)
