from __future__ import annotations

from kit import config, discord, net, ui, units

APP = "discord"


def url(value: str) -> str:
    value = value.strip().rstrip("/")
    if not value.startswith("https://") or len(value) <= len("https://") or " " in value:
        raise ValueError("endereço com https://, como https://discord.casa.com")
    return value


def install(reuse: bool) -> None:
    if reuse and discord.configured():
        try:
            name = discord.whoami()
        except discord.DiscordError as problem:
            ui.warn(f"a configuração salva não funciona mais ({problem}): responda de novo")
        else:
            ui.ok(f"esta máquina continua ligada ao bot como {name}")
            return
    domain = config.domain()
    ui.note(
        "Na máquina que roda o bot, use a ação Adicionar um cliente (ou Mostrar a chave de um cliente) do app "
        "discord: ela mostra o endereço e a chave para colar aqui."
    )
    while True:
        address = ui.ask("endereço do bot", default=f"https://discord.{domain}", validate=url)
        key = ui.secret("chave do cliente", confirm=False)
        try:
            name = discord.whoami(address, key)
            break
        except discord.DiscordError as problem:
            ui.warn(f"o bot não aceitou: {problem}")
    discord.save(address, key)
    config.save(APP, {"MODE": "client"})
    ui.ok(f"esta máquina está ligada ao bot como {name}")
    if discord.notify(APP, "sucesso", "Máquina ligada ao Discord", f"{net.hostname()} agora manda avisos como {name}."):
        ui.ok("mensagem de teste enviada ao canal #discord")


def summary() -> None:
    values = discord.settings()
    try:
        name = discord.whoami()
        state = ui.good(f"ligada como {name}")
    except discord.DiscordError as problem:
        state = ui.bad(str(problem))
    ui.section("Esta máquina")
    ui.table([
        ["Endereço do bot", values.get("DISCORD_URL") or ui.pending("não configurado")],
        ["Situação", state],
        ["Comandos do /astro", ui.good("agente ligado") if units.active("astroverso-discord-agent.service") else ui.pending("agente desligado")],
    ])
