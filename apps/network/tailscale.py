from __future__ import annotations

import getpass
import json
import time

from kit import config, distro, net, run, ui

APP = "network"
PACKAGE = "tailscale"
SERVICE = "tailscaled"
PORT = "41641/udp"
STATE_DIR = "/var/lib/tailscale"
ADMIN = "https://login.tailscale.com/admin/machines"
WINDOWS_RULE = (
    'New-NetFirewallRule -DisplayName "Tailscale" -Direction Inbound -Protocol UDP -LocalPort 41641 -Action Allow'
)
LINUX_RULE = "sudo firewall-cmd --permanent --add-port=41641/udp && sudo firewall-cmd --reload"


def status() -> dict:
    if not distro.installed(PACKAGE) or not run.succeeds(["tailscale", "status", "--json"]):
        return {}
    try:
        return json.loads(run.capture(["tailscale", "status", "--json"]))
    except json.JSONDecodeError:
        return {}


def prefs() -> dict:
    command = ["tailscale", "debug", "prefs"]
    try:
        return json.loads(run.capture(command, sudo=not run.succeeds(command)))
    except json.JSONDecodeError:
        return {}


def connected(state: dict | None = None) -> bool:
    return (status() if state is None else state).get("BackendState") == "Running"


def installed() -> bool:
    return connected()


def route() -> str:
    return f"{net.lan_ip()}/32"


def approved(state: dict | None = None) -> bool:
    current = status() if state is None else state
    return route() in ((current.get("Self") or {}).get("PrimaryRoutes") or [])


def _flags() -> list[str]:
    return ["--accept-routes=false", f"--operator={getpass.getuser()}", f"--hostname={net.hostname()}"]


def install(reuse: bool) -> None:
    ui.step("Tailscale: acesso de fora de casa")
    ui.note(
        "O Tailscale cria uma rede privada entre os seus aparelhos (celular, notebook) e esta máquina. "
        "Com ele, os endereços do Astroverso funcionam também fora de casa, sem abrir a sua rede para a internet."
    )
    run.sudo_prepare("instalar o Tailscale, ligar o serviço dele e liberar a porta dele no firewall")
    distro.install([PACKAGE])
    distro.service_enable(SERVICE)
    distro.firewall_open([PORT])
    _login()
    _advertise()
    _router(reuse)
    _other_machines()


def _login() -> None:
    if connected():
        current = prefs()
        if current.get("RouteAll") or current.get("OperatorUser") != getpass.getuser():
            run.cmd(["tailscale", "set", "--accept-routes=false", f"--operator={getpass.getuser()}"], sudo=True)
        ui.ok("esta máquina já está conectada ao Tailscale")
        return
    ui.note(
        "Agora é preciso ligar esta máquina à sua conta do Tailscale. Vai aparecer um endereço: abra no navegador "
        "do celular ou do computador e entre com a sua conta (se ainda não tiver, dá para criar ali mesmo, de graça). "
        "A instalação continua sozinha depois do login."
    )
    run.cmd(["tailscale", "up", "--reset", *_flags()], sudo=True)
    if not connected():
        ui.fail("o Tailscale não ficou conectado: tente de novo pela ação Reconectar ao Tailscale")
    ui.ok("esta máquina está conectada ao Tailscale")


def _advertise() -> None:
    address = route()
    ui.note(
        f"Para os endereços do Astroverso abrirem também fora de casa, esta máquina avisa ao Tailscale que responde "
        f"pelo próprio IP da rede de casa ({address.removesuffix('/32')}). Os outros aparelhos da casa não ficam expostos."
    )
    if prefs().get("AdvertiseRoutes") != [address]:
        run.cmd(["tailscale", "set", f"--advertise-routes={address}"], sudo=True)
        ui.ok(f"{address} anunciado no Tailscale")
    if approved():
        ui.ok(f"{address} aprovado no painel do Tailscale")
        return
    ui.note(
        f"Falta aprovar esse anúncio no painel do Tailscale (só na primeira vez): abra {ADMIN}, clique nos três "
        f"pontinhos ao lado de {net.hostname()}, escolha Edit route settings, marque {address} e salve."
    )
    while ui.confirm("Já aprovou?", default=True):
        for _ in range(5):
            if approved():
                ui.ok(f"{address} aprovado no painel do Tailscale")
                return
            time.sleep(1)
        ui.warn("ainda não aparece aprovado: confira no painel e tente de novo")
    ui.warn("aprovação pendente: fora de casa, os endereços só abrem depois dela (veja em Resumo da rede)")


def _router(reuse: bool) -> None:
    saved = config.load(APP).get("ROUTER_FORWARD")
    if reuse and saved:
        return
    port = PORT.split("/")[0]
    ui.note(
        "Opcional, mas recomendado: fora de casa, o Tailscale tenta ligar o seu aparelho direto a esta máquina. "
        "Quando não consegue, passa por um servidor intermediário, bem mais lento (ruim para vídeo e jogos). "
        "Para garantir a ligação direta, entre nas configurações do roteador e procure Redirecionamento de portas, "
        f"Port Forwarding ou Servidor virtual. Crie uma regra: protocolo UDP, porta {port}, para o IP "
        f"{net.lan_ip()}, porta {port}. Essa porta só aceita aparelhos da sua conta do Tailscale."
    )
    done = ui.confirm("Já fez esse redirecionamento no roteador?", default=saved == "yes")
    config.save(APP, {"ROUTER_FORWARD": "yes" if done else "no"})
    if not done:
        ui.warn("redirecionamento pendente: depois de fazer, use a ação Marcar o redirecionamento no roteador como feito")


def _other_machines() -> None:
    ui.note(
        "Importante: o mesmo vale para os outros computadores da casa que têm o Tailscale. Se o firewall deles "
        "bloquear a porta UDP 41641, a conexão com esta máquina passa pelo servidor intermediário até dentro de "
        "casa. Libere a entrada dessa porta em cada um deles:"
    )
    ui.info(f"  Windows (PowerShell como administrador): {WINDOWS_RULE}")
    ui.info(f"  Linux com firewalld: {LINUX_RULE}")
    ui.note("O Resumo da rede mostra, aparelho por aparelho, se a conexão está direta ou por relay.")


def reconnect() -> None:
    run.sudo_prepare("conectar esta máquina ao Tailscale de novo")
    ui.note("Vai aparecer um endereço: abra no navegador e entre com a sua conta do Tailscale.")
    run.cmd(["tailscale", "up", "--force-reauth", "--reset", *_flags(), f"--advertise-routes={route()}"], sudo=True)
    if not connected():
        ui.fail("o Tailscale não ficou conectado")
    ui.ok("esta máquina está conectada ao Tailscale")


def mark_router() -> None:
    config.save(APP, {"ROUTER_FORWARD": "yes"})
    ui.ok("redirecionamento no roteador marcado como feito")


def remove() -> None:
    ui.step("Tailscale")
    run.sudo_prepare("desconectar esta máquina do Tailscale e remover o pacote")
    if connected():
        run.cmd(["tailscale", "logout"], sudo=True)
        ui.ok("esta máquina saiu da sua conta do Tailscale")
    distro.service_disable(SERVICE)
    distro.firewall_close([PORT])
    distro.uninstall([PACKAGE])
    run.cmd(["rm", "-rf", STATE_DIR], sudo=True)


def _peer_name(peer: dict) -> str:
    return (peer.get("DNSName") or "").split(".")[0] or peer.get("HostName") or "?"


def _connection(peer: dict) -> str | ui.Cell:
    if not peer.get("Online"):
        return "-"
    if peer.get("CurAddr"):
        return ui.good("direta")
    return ui.pending(f"relay {peer['Relay']}") if peer.get("Relay") else "-"


def summary() -> None:
    state = status()
    me = state.get("Self") or {}
    ips = me.get("TailscaleIPs") or []
    ui.section("Esta máquina")
    ui.table([
        ["Nome", net.hostname()],
        ["IP na rede", net.lan_ip()],
        ["IP no Tailscale", ips[0] if ips else ui.off("desconectado")],
        ["Nome no Tailscale", (me.get("DNSName") or "").rstrip(".") or ui.off("desconectado")],
    ])
    ui.section("Tailscale")
    tailnet = (state.get("CurrentTailnet") or {}).get("Name") or ""
    situation = ui.good(f"conectado à rede {tailnet}".strip()) if connected(state) else ui.bad(
        state.get("BackendState") or "não instalado"
    )
    advertised = (prefs().get("AdvertiseRoutes") or []) if state else []
    rows: list[list[str | ui.Cell]] = [["Situação", situation]]
    for item in advertised or [""]:
        label = "Anunciado" if item == (advertised or [""])[0] else ""
        if not item:
            rows.append([label, ui.pending("nada anunciado")])
        elif item in (me.get("PrimaryRoutes") or []):
            rows.append([label, ui.good(f"{item} aprovado")])
        else:
            rows.append([label, ui.pending(f"{item}: falta aprovar no painel")])
    ui.table(rows)
    peers = sorted((state.get("Peer") or {}).values(), key=_peer_name)
    if peers:
        ui.section("Aparelhos no Tailscale")
        ui.table(
            [
                [
                    _peer_name(peer),
                    (peer.get("TailscaleIPs") or ["-"])[0],
                    peer.get("OS") or "-",
                    ui.good("online") if peer.get("Online") else ui.off("offline"),
                    _connection(peer),
                ]
                for peer in peers
            ],
            ["Nome", "IP", "Sistema", "Situação", "Conexão"],
        )
        for peer in peers:
            if peer.get("Online") and not peer.get("CurAddr") and peer.get("Relay"):
                ui.warn(
                    f"{_peer_name(peer)} está por relay: se ele estiver em casa, libere a porta UDP 41641 no "
                    "firewall dele (veja os comandos na instalação ou no README do network)"
                )
    router = config.load(APP).get("ROUTER_FORWARD")
    ui.section("Portas")
    ui.table(
        [[
            PORT,
            "Tailscale",
            ui.good("liberada") if distro.firewall_allowed(PORT) else ui.pending("fechada"),
            ui.good("feito") if router == "yes" else ui.pending("pendente"),
        ]],
        ["Porta", "Para quê", "Firewall", "Roteador"],
    )
