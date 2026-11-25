from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from kit import changes, config, discord, docs, net, ui, watch as kit_watch
from kit.watch import Problem

from . import adguard, caddy, tailscale

APP = "network"
NAME = "astroverso-network-watch"
DOCS = Path(__file__).with_name("docs")
BUTTONS = (("Resumo da rede", "network:summary"), ("Verificar de novo", "network:watch"))
WARN_DAYS = 14
CRITICAL_DAYS = 3


def state_file() -> Path:
    return kit_watch.state_file(APP)


def _days(moment: datetime, now: datetime) -> int:
    return int((moment - now).total_seconds() // 86400)


def _address() -> str:
    try:
        return net.lan_ip()
    except SystemExit:
        return ""


def _certificate(domain: str, now: datetime) -> dict[str, Problem]:
    if not caddy.installed():
        return {"caddy": Problem("erro", "Caddy parado", "Os endereços do Astroverso não abrem (o reinício automático não resolveu).")}
    expires = caddy.expiry(domain)
    if expires is None:
        return {"certificate": Problem("erro", "Cadeado inválido ou vencido",
                                       f"O certificado de *.{domain} não foi emitido ou venceu. Veja as causas comuns: "
                                       + docs.link(DOCS / "cloudflare.md", "quando-o-cadeado-demora"))}
    left = _days(expires, now)
    if left < WARN_DAYS:
        return {"certificate": Problem("erro" if left < CRITICAL_DAYS else "aviso", f"Cadeado vence em {left} dias",
                                       f"A renovação automática de *.{domain} está falhando. Veja as causas comuns: "
                                       + docs.link(DOCS / "cloudflare.md", "quando-o-cadeado-demora"), "certificate-expiring")}
    return {}


def _token(domain: str) -> dict[str, Problem]:
    token = caddy.saved_token()
    problem = caddy.check_token(token, domain) if token else "não há token salvo"
    if not problem or "não respondeu" in problem:
        return {}
    return {"token": Problem("erro", "Token da Cloudflare não vale mais",
                             f"{problem}. Sem ele, o cadeado não renova. Crie outro e reinstale o network: "
                             + docs.link(DOCS / "cloudflare.md", "trocar-o-token"))}


def _tailscale(saved_ip: str, now: datetime, previous: dict[str, dict[str, str]]) -> dict[str, Problem]:
    state = tailscale.status()
    if not tailscale.connected(state):
        return {"tailscale": Problem("erro", "Servidor fora do Tailscale",
                                     f"Situação: {state.get('BackendState') or 'serviço parado'}. Fora de casa, nada abre. "
                                     "Use a ação Reconectar ao Tailscale.")}
    found: dict[str, Problem] = {}
    if saved_ip and f"{saved_ip}/32" not in ((state.get("Self") or {}).get("PrimaryRoutes") or []):
        found["route"] = Problem("erro", f"Anúncio de {saved_ip}/32 sem aprovação",
                                 "Fora de casa, os endereços não abrem. Aprove de novo no painel: "
                                 + docs.link(DOCS / "tailscale.md", "aprovar-a-rota-do-servidor"))
    expiry = str((state.get("Self") or {}).get("KeyExpiry") or "")
    if expiry:
        try:
            left = _days(datetime.fromisoformat(expiry.replace("Z", "+00:00")), now)
        except ValueError:
            left = WARN_DAYS
        if left < WARN_DAYS:
            found["key"] = Problem("aviso", f"Chave do servidor no Tailscale vence em {left} dias",
                                   "Quando vencer, o servidor sai da rede. Desligue a expiração no painel: "
                                   + docs.link(DOCS / "tailscale.md", "desligar-a-expiração-da-chave"), "key-expiring")
    for peer in (state.get("Peer") or {}).values():
        name = tailscale.peer_name(peer)
        key = f"relay:{name}"
        if peer.get("Online") and peer.get("Active"):
            if tailscale.relayed(peer):
                found[key] = Problem("info", f"{name} está por relay",
                                     "A conexão com o servidor passa por um servidor intermediário, mais lento. "
                                     "Veja as causas: " + docs.link(DOCS / "tailscale.md", "direto-ou-por-relay"))
        elif key in previous:
            found[key] = kit_watch.carry(previous, key)
    return found


def collect(previous: dict[str, dict[str, str]] | None = None) -> dict[str, Problem]:
    previous = previous or {}
    now = datetime.now(timezone.utc)
    domain = config.saved_domain()
    saved_ip = config.load(APP).get("SERVER_IP", "")
    found: dict[str, Problem] = {}
    current_ip = _address()
    if saved_ip and current_ip and current_ip != saved_ip:
        found["ip"] = Problem("erro", f"IP do servidor mudou de {saved_ip} para {current_ip}",
                              "O DNS da casa e o anúncio no Tailscale apontam para o IP antigo. Confira a reserva no "
                              "roteador e reinstale o network: " + docs.link(DOCS / "roteador.md", "reservar-o-ip-e-apontar-o-dns"))
    if not adguard.installed():
        found["adguard"] = Problem("erro", "AdGuard parado",
                                   "A casa está no DNS secundário: sem bloqueio e sem os endereços do Astroverso.")
    if domain:
        found.update(_certificate(domain, now))
        found.update(_token(domain))
    found.update(_tailscale(saved_ip, now, previous))
    return found


def check() -> None:
    kit_watch.run(APP, collect, BUTTONS, "rede em ordem")


def units_text() -> dict[str, str]:
    return kit_watch.units_text(APP, "a rede")


def items() -> list[changes.Change]:
    return [
        kit_watch.change(
            APP, "Verificar a rede de hora em hora e avisar no Discord",
            f"Um timer do usuário ({NAME}.timer) confere a rede a cada hora (AdGuard e Caddy no ar, cadeado, token da "
            "Cloudflare, Tailscale, IP) e avisa no Discord quando algo quebra e quando volta ao normal.",
            "a rede",
        ),
    ]


def install(reuse: bool) -> None:
    changes.install(APP, items(), reuse)
    if active() and not discord.configured():
        ui.info("a verificação avisa no Discord quando o app discord estiver instalado nesta máquina")


def remove() -> None:
    changes.undo_all(items())


def active() -> bool:
    return kit_watch.active(APP)


def summary() -> None:
    kit_watch.summary(APP)
