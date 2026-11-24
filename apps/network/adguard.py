from __future__ import annotations

import os
import socket
import string
from pathlib import Path

from kit import config, container, distro, net, run, ui, validate

from . import tailscale

APP = "network"
NAME = "astroverso-network-adguard"
IMAGE = "docker.io/adguard/adguardhome:v0.107.80"
HASHER = "docker.io/library/caddy:2.11.9-alpine"
WEB_PORT = 8080
TEMPLATE = Path(__file__).with_name("adguard.yaml")
DNS_ADMIN = "https://login.tailscale.com/admin/dns"


def folder() -> Path:
    return config.state(APP) / "adguard"


def conf_file() -> Path:
    return folder() / "conf" / "AdGuardHome.yaml"


def spec() -> container.Container:
    return container.Container(
        name=NAME,
        image=IMAGE,
        description="Astroverso network: AdGuard (DNS)",
        network="host",
        volumes=[
            container.Volume(folder() / "conf", "/opt/adguardhome/conf"),
            container.Volume(folder() / "work", "/opt/adguardhome/work"),
        ],
        command=["--no-check-update", "-c", "/opt/adguardhome/conf/AdGuardHome.yaml", "-w", "/opt/adguardhome/work"],
        health=f"wget -q --spider http://127.0.0.1:{WEB_PORT}/login.html",
    )


def installed() -> bool:
    return container.active(NAME)


def timezone() -> str:
    target = str(Path("/etc/localtime").resolve())
    return target.split("zoneinfo/", 1)[1] if "zoneinfo/" in target else "UTC"


def language() -> str:
    return "pt-br" if os.environ.get("LANG", "").lower().startswith("pt") else "en"


def render(user: str, password_hash: str, domain: str, address: str) -> str:
    return string.Template(TEMPLATE.read_text()).substitute(
        WEB_PORT=str(WEB_PORT),
        ADGUARD_USERNAME=user,
        ADGUARD_PASSWORD_HASH=password_hash,
        ADGUARD_LANGUAGE=language(),
        DNS_BIND_HOSTS=f"    - {address}\n    - 127.0.0.1",
        TZ=timezone(),
        ADGUARD_REWRITES_YAML=f"[{{domain: '*.{domain}', answer: '{address}', enabled: true}}]",
    )


def install(reuse: bool) -> None:
    ui.step("AdGuard: o DNS da casa")
    ui.note(
        "O AdGuard responde aos aparelhos da casa qual é o endereço de cada site e, no caminho, bloqueia propaganda "
        "e rastreadores. É ele também que faz os endereços do Astroverso, como adguard.<seu domínio>, apontarem "
        "para esta máquina."
    )
    if not config.saved_domain():
        ui.note(
            "Os serviços do Astroverso ganham endereços com o domínio que você registrou (por exemplo, casa.com vira "
            "adguard.casa.com). O mesmo domínio vale para todos os apps."
        )
    domain = config.domain()
    address = net.lan_ip()
    values = config.load(APP)
    regenerate = not conf_file().exists()
    password = ""
    if not (reuse and values.get("ADGUARD_USER") and values.get("ADGUARD_PASSWORD_HASH")):
        ui.note("O AdGuard tem um painel na web para ver as consultas e ajustar o bloqueio. Escolha o acesso a ele.")
        user = ui.ask("usuário do painel do AdGuard", default=values.get("ADGUARD_USER") or "astroverso", validate=validate.name)
        password = ui.secret("senha do painel do AdGuard")
    run.sudo_prepare("liberar o DNS no firewall e ajustar o DNS desta máquina")
    container.prepare()
    if password:
        password_hash = container.once(HASHER, ["caddy", "hash-password"], input=f"{password}\n").splitlines()[-1]
        config.save(APP, {"ADGUARD_USER": user, "ADGUARD_PASSWORD_HASH": password_hash})
        values = config.load(APP)
        regenerate = True
    distro.sysctl_set(APP, {"net.ipv4.ip_unprivileged_port_start": "53"})
    distro.firewall_open(["dns", f"{WEB_PORT}/tcp"])
    if regenerate:
        _write_conf(values["ADGUARD_USER"], values["ADGUARD_PASSWORD_HASH"], domain, address)
    container.start(spec())
    distro.resolver_route(APP, domain, "127.0.0.1")
    if resolves(domain, address):
        ui.ok(f"*.{domain} responde {address}")
    else:
        ui.warn(f"*.{domain} ainda não responde {address}: confira em Resumo da rede")
    _split_dns(domain, address)
    _router(reuse, address)


def _write_conf(user: str, password_hash: str, domain: str, address: str) -> None:
    for name in ("conf", "work"):
        (folder() / name).mkdir(parents=True, exist_ok=True, mode=0o700)
    target = conf_file()
    if target.exists():
        target.replace(target.with_suffix(".yaml.bak"))
        ui.info(f"configuração anterior guardada em {target.with_suffix('.yaml.bak').name}")
    target.write_text(render(user, password_hash, domain, address))
    target.chmod(0o600)
    ui.ok(f"configuração do AdGuard gerada (reescrita *.{domain} → {address})")


def resolves(domain: str, address: str) -> bool:
    try:
        return socket.gethostbyname(f"astroverso-teste.{domain}") == address
    except OSError:
        return False


def split_dns(domain: str) -> str:
    if not tailscale.connected():
        return ""
    output = run.capture(["tailscale", "dns", "status"]) if run.succeeds(["tailscale", "dns", "status"]) else ""
    for line in output.splitlines():
        parts = line.split()
        if len(parts) >= 4 and parts[0] == "-" and parts[1].rstrip(".") == domain and parts[2] == "->":
            return parts[3]
    return ""


def _split_dns(domain: str, address: str) -> None:
    if not tailscale.connected():
        return
    if split_dns(domain) == address:
        ui.ok(f"Split DNS do Tailscale: {domain} → {address}")
        return
    ui.note(
        f"Falta um ajuste no painel do Tailscale para os endereços funcionarem fora de casa: o Split DNS, que manda "
        f"as perguntas sobre {domain} para o AdGuard desta máquina. Abra {DNS_ADMIN}, em Nameservers clique em Add "
        f"nameserver, escolha Custom, coloque {address}, ligue Restrict to domain (Split DNS), coloque {domain} e "
        "salve. Se houver outra entrada para esse domínio, apague."
    )
    while ui.confirm("Já configurou?", default=True):
        server = split_dns(domain)
        if server == address:
            ui.ok(f"Split DNS do Tailscale: {domain} → {address}")
            return
        ui.warn(f"o Tailscale ainda manda {domain} para {server}" if server else f"o Split DNS de {domain} ainda não aparece")
    ui.warn("Split DNS pendente: fora de casa, os endereços não abrem até lá (veja em Resumo da rede)")


def _router(reuse: bool, address: str) -> None:
    saved = config.load(APP).get("ROUTER_DNS")
    if reuse and saved:
        return
    ui.note(
        "Para os aparelhos da casa usarem o AdGuard, entre nas configurações do roteador (DHCP ou LAN) e faça duas "
        f"coisas: reserve o IP {address} para esta máquina, para ele nunca mudar; e coloque {address} como DNS "
        "primário, com um DNS público (como 1.1.1.1) como secundário. O secundário garante que os aparelhos continuem "
        "navegando se esta máquina estiver desligada, só que sem o bloqueio e sem os endereços da casa."
    )
    done = ui.confirm("Já configurou o roteador?", default=saved == "yes")
    config.save(APP, {"ROUTER_DNS": "yes" if done else "no"})
    if not done:
        ui.warn("roteador pendente: depois de configurar, use a ação Marcar o DNS no roteador como feito")


def mark_router() -> None:
    config.save(APP, {"ROUTER_DNS": "yes"})
    ui.ok("DNS no roteador marcado como feito")


def remove() -> None:
    ui.step("AdGuard")
    run.sudo_prepare("tirar o DNS do firewall e devolver o DNS desta máquina ao normal")
    container.remove(NAME, IMAGE)
    container.remove_image(HASHER)
    distro.resolver_route_remove(APP)
    distro.firewall_close(["dns", f"{WEB_PORT}/tcp"])
    distro.sysctl_remove(APP)


def summary() -> None:
    values = config.load(APP)
    domain = config.saved_domain()
    address = net.lan_ip()
    running = installed()
    ui.section("DNS (AdGuard)")
    rows: list[list[str | ui.Cell]] = [
        ["AdGuard", ui.good("no ar") if running else ui.bad("parado")],
        ["Domínio", domain or ui.pending("não definido")],
        ["Reescrita", f"*.{domain} → {address}" if domain else "-"],
        ["Teste de nome", ui.good(f"astroverso-teste.{domain} → {address}") if domain and resolves(domain, address) else ui.bad("não responde")],
    ]
    if tailscale.connected():
        server = split_dns(domain) if domain else ""
        rows.append(["Split DNS", ui.good(f"{domain} → {server}") if server == address else (
            ui.bad(f"{domain} → {server}") if server else ui.pending("falta configurar no painel do Tailscale"))])
    rows.append(["Roteador (DNS)", ui.good("feito") if values.get("ROUTER_DNS") == "yes" else ui.pending("pendente")])
    rows.append(["Painel", f"http://{address}:{WEB_PORT} (usuário {values.get('ADGUARD_USER', '-')})"])
    ui.table(rows)


def port_rows() -> list[list[str | ui.Cell]]:
    def state(item: str) -> ui.Cell:
        return ui.good("liberada") if distro.firewall_allowed(item) else ui.pending("fechada")

    return [
        ["53 (tcp/udp)", "DNS (AdGuard)", state("dns"), "-"],
        [f"{WEB_PORT}/tcp", "Painel do AdGuard", state(f"{WEB_PORT}/tcp"), "-"],
    ]
