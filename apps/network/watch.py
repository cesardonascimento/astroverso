from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from kit import config, discord, docs, net, ui, units

from . import adguard, caddy, tailscale

APP = "network"
NAME = "astroverso-network-watch"
DOCS = Path(__file__).with_name("docs")
BUTTONS = (("Resumo da rede", "network:summary"), ("Verificar de novo", "network:watch"))
WARN_DAYS = 14
CRITICAL_DAYS = 3


@dataclass(frozen=True)
class Problem:
    level: str
    title: str
    text: str = ""
    kind: str = ""

    @property
    def identity(self) -> str:
        return self.kind or self.title


def state_file() -> Path:
    return config.state(APP) / "watch.json"


def _load() -> dict[str, dict[str, str]]:
    try:
        saved = json.loads(state_file().read_text())
    except (OSError, ValueError):
        return {}
    return {key: value for key, value in saved.items() if isinstance(value, dict)} if isinstance(saved, dict) else {}


def _save(state: dict[str, dict[str, str]]) -> None:
    temporary = state_file().with_suffix(".tmp")
    temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n")
    temporary.replace(state_file())


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
            found[key] = Problem(previous[key]["level"], previous[key]["title"], previous[key].get("text", ""),
                                 previous[key].get("kind", ""))
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
    previous = _load()
    found = collect(previous)
    if not discord.configured():
        for problem in found.values():
            ui.warn(problem.title)
        ui.info("Discord não configurado nesta máquina: os problemas só aparecem aqui (instale o app discord)")
        return
    state = dict(previous)
    for key, problem in found.items():
        before = previous.get(key)
        if before and before.get("level") == problem.level and (before.get("kind") or before.get("title")) == problem.identity:
            continue
        if discord.notify(APP, problem.level, problem.title, problem.text, actions=BUTTONS):
            state[key] = {"level": problem.level, "title": problem.title, "text": problem.text, "kind": problem.kind}
            ui.warn(f"avisado no Discord: {problem.title}")
    for key, before in previous.items():
        if key in found:
            continue
        title = f"{before.get('title', key)}: resolvido"
        if discord.notify(APP, "sucesso", title):
            state.pop(key, None)
            ui.ok(f"avisado no Discord: {title}")
    _save(state)
    if not found:
        ui.ok("rede em ordem")


def units_text() -> dict[str, str]:
    command = Path(__file__).resolve().parents[2] / "astroverso"
    return {
        f"{NAME}.timer": "\n".join([
            "[Unit]",
            "Description=Astroverso network: verifica a rede a cada hora e avisa no Discord",
            "",
            "[Timer]",
            "OnActiveSec=10min",
            "OnUnitActiveSec=1h",
            "RandomizedDelaySec=2min",
            "",
            "[Install]",
            "WantedBy=timers.target",
            "",
        ]),
        f"{NAME}.service": "\n".join([
            "[Unit]",
            "Description=Astroverso network: verificação da rede",
            "",
            "[Service]",
            "Type=oneshot",
            f"ExecStart={command} network action watch",
            "",
        ]),
    }


def install() -> None:
    units.install(units_text(), [f"{NAME}.timer"])
    if not discord.configured():
        ui.info("a verificação de hora em hora avisa no Discord quando o app discord estiver instalado")


def remove() -> None:
    units.remove([f"{NAME}.timer", f"{NAME}.service"])


def active() -> bool:
    return units.active(f"{NAME}.timer")


def summary() -> None:
    state = _load()
    ui.section("Verificação de hora em hora")
    rows: list[list[str | ui.Cell]] = [
        ["Verificação", ui.good("ligada") if active() else ui.pending("desligada")],
        ["Avisos no Discord", ui.good("ligados") if discord.configured() else ui.pending("instale o app discord")],
    ]
    for item in state.values():
        level = item.get("level", "")
        cell = ui.bad if level == "erro" else ui.pending if level == "aviso" else ui.off
        rows.append(["Aviso em aberto" if item is next(iter(state.values())) else "", cell(item.get("title", ""))])
    if not state:
        rows.append(["Avisos em aberto", ui.good("nenhum")])
    ui.table(rows)
