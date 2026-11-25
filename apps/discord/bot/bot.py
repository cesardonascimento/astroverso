from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import os
import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import discord
from aiohttp import web
from discord import app_commands

DATA = Path("/data")
MANIFESTS = DATA / "clients"
CHANNELS_FILE = DATA / "channels.json"
TOKEN = os.environ["DISCORD_TOKEN"]
GUILD = int(os.environ["DISCORD_GUILD"])
USERS = {int(item) for item in os.environ.get("DISCORD_USERS", "").replace(",", " ").split() if item.isdigit()}
KEYS = {name: digest for name, _, digest in (item.partition("=") for item in os.environ.get("DISCORD_CLIENTS", "").split()) if digest}
CONTENT = os.environ.get("DISCORD_MESSAGE_CONTENT", "no") == "yes"
PORT = 8080
CATEGORY = "Astroverso"
MAIN = "astro"
SYSTEM = "sistema"
NAME = re.compile(r"^[a-z0-9][a-z0-9-]{0,31}$")
ARGUMENT = re.compile(r"^[A-Za-z0-9._-]{0,64}$")
COMMAND_WAIT = 840
MESSAGE_WAIT = 120
STYLES = {
    "primary": discord.ButtonStyle.primary, "success": discord.ButtonStyle.success,
    "danger": discord.ButtonStyle.danger, "secondary": discord.ButtonStyle.secondary,
}
LEVELS = {
    "info": ("ℹ️", 0x8A4DFF, True),
    "sucesso": ("✅", 0x4ADE80, True),
    "aviso": ("⚠️", 0xFBBF24, False),
    "erro": ("❌", 0xF87171, False),
}

logging.basicConfig(level=logging.INFO, format="[discord] %(message)s")
logging.getLogger("discord").setLevel(logging.WARNING)
logging.getLogger("discord.client").setLevel(logging.ERROR)
logging.getLogger("aiohttp.access").setLevel(logging.WARNING)
log = logging.getLogger("astro")


class Client:
    def __init__(self, name: str) -> None:
        self.name = name
        self.queue: asyncio.Queue[dict] = asyncio.Queue()
        self.seen = 0.0
        self.manifest: dict[str, Any] = {}
        self.patterns: list[tuple[re.Pattern[str], Any]] = []
        try:
            self.apply(json.loads((MANIFESTS / f"{name}.json").read_text()))
        except (OSError, ValueError):
            pass

    def apply(self, manifest: dict[str, Any]) -> None:
        patterns = []
        for rule in manifest.get("botoes") or []:
            try:
                patterns.append((re.compile(str(rule["padrao"])[:200]), rule.get("texto")))
            except (KeyError, TypeError, re.error):
                log.warning("%s: padrão de botão inválido ignorado: %s", self.name, rule)
        self.manifest = manifest
        self.patterns = patterns


clients: dict[str, Client] = {}
pending: dict[str, tuple[str, asyncio.Future, float]] = {}
channels: dict[str, int] = {}
listeners: dict[int, str] = {}


def load_channels() -> None:
    try:
        channels.update({key: int(value) for key, value in json.loads(CHANNELS_FILE.read_text()).items()})
    except (OSError, ValueError):
        pass


def save_channels() -> None:
    temporary = CHANNELS_FILE.with_suffix(".tmp")
    temporary.write_text(json.dumps(channels, ensure_ascii=False))
    temporary.rename(CHANNELS_FILE)


def update_listeners() -> None:
    listeners.clear()
    for client in clients.values():
        for item in client.manifest.get("canais") or []:
            if item.get("escuta") and item.get("nome") in channels:
                listeners[channels[item["nome"]]] = client.name


def catalog() -> dict[str, dict]:
    items: dict[str, dict] = {}
    for client in clients.values():
        for action in client.manifest.get("catalogo") or []:
            if isinstance(action, dict) and action.get("id") and action["id"] not in items:
                items[action["id"]] = {**action, "cliente": client.name}
    return items


def button_owner(custom_id: str) -> tuple[Client | None, Any]:
    for client in clients.values():
        for pattern, text in client.patterns:
            if pattern.fullmatch(custom_id):
                return client, text
    return None, None


def label(action: str, argument: str) -> str:
    return f"`{action}{' ' + argument if argument else ''}`"


def result(action: str, argument: str, data: dict) -> str:
    icon = "✅" if data.get("ok") else "❌"
    output = (data.get("saida") or "").strip().replace("```", "'''")
    if len(output) > 1800:
        output = "…\n" + output[-1800:]
    return f"{icon} {label(action, argument)}" + (f"\n```\n{output}\n```" if output else "")


def help_pages() -> list[str]:
    items = [item for client in clients.values() for item in client.manifest.get("ajuda") or []]
    if not items:
        actions = catalog()
        if not actions:
            return ["nenhum cliente publicou comandos ainda"]
        return ["**Comandos**\n" + "\n".join(f"`{a['id']}` — {a.get('descricao', '')}" for a in actions.values())]
    blocks = ["**Operações do Astroverso** (`/astro command:<comando> argument:<opcional>`)"]
    group = None
    for item in items:
        if item.get("grupo") != group:
            group = item.get("grupo")
            blocks.append(f"\n__{group}__")
        command = item.get("comando") or ""
        command = f"`{command}`" if command and command != "-" else "só pelo instalador"
        blocks.append(f"**{item.get('nome', '')}** — {item.get('descricao', '')}\n  ⏱ {item.get('quando', '')} · 💬 {command}")
    pages, current = [], ""
    for block in blocks:
        if len(current) + len(block) + 1 > 1900:
            pages.append(current)
            current = ""
        current += ("\n" if current else "") + block
    return pages + ([current] if current else [])


def user_info(user: discord.abc.User) -> dict[str, str]:
    return {"id": str(user.id), "nome": str(user), "exibicao": getattr(user, "display_name", str(user))}


async def ask(client: Client, event: dict, wait: float) -> dict | None:
    event = {"id": uuid.uuid4().hex, **event}
    future = asyncio.get_running_loop().create_future()
    pending[event["id"]] = (client.name, future, time.monotonic())
    await client.queue.put(event)
    try:
        return await asyncio.wait_for(future, wait)
    except asyncio.TimeoutError:
        return None
    finally:
        pending.pop(event["id"], None)


def own_button(text: str, kind: str, action: str = "", argument: str = "",
               style: discord.ButtonStyle = discord.ButtonStyle.secondary) -> discord.ui.Button:
    return discord.ui.Button(label=text[:80], style=style, custom_id=f"astro|{kind}|{action}|{argument}"[:100])


def confirmation(action: str, argument: str) -> discord.ui.View:
    view = discord.ui.View(timeout=None)
    view.add_item(own_button("Confirmar", "ok", action, argument, discord.ButtonStyle.danger))
    view.add_item(own_button("Cancelar", "cancelar"))
    return view


def buttons(items: Any, client: Client | None = None) -> Any:
    view = discord.ui.View(timeout=None)
    for item in (items or [])[:25]:
        if not isinstance(item, dict):
            continue
        style = STYLES.get(item.get("estilo", ""), discord.ButtonStyle.secondary)
        text = str(item.get("rotulo") or "?")[:80]
        if item.get("custom_id"):
            custom_id = str(item["custom_id"])[:100]
            if client is None or not any(pattern.fullmatch(custom_id) for pattern, _ in client.patterns):
                log.warning("%s: botão %s fora dos padrões declarados, ignorado", client and client.name, custom_id)
                continue
            view.add_item(discord.ui.Button(label=text, style=style, custom_id=custom_id))
        elif item.get("acao"):
            view.add_item(own_button(text, "run", str(item["acao"]), str(item.get("arg") or ""), style))
    return view if view.children else discord.utils.MISSING


def notice(data: dict, client: Client, owner: int) -> dict[str, Any]:
    icon, color, quiet = LEVELS[data["nivel"]]
    embed = discord.Embed(
        title=f"{icon} {str(data.get('titulo') or '')[:240]}",
        description=str(data.get("texto") or "")[:4000] or None,
        color=color,
        timestamp=datetime.now(timezone.utc),
    )
    embed.set_author(name=str(data.get("app") or client.name)[:256])
    fields = data.get("campos") if isinstance(data.get("campos"), dict) else {}
    for name, value in list(fields.items())[:25]:
        embed.add_field(name=str(name)[:256], value=str(value)[:1024] or "-", inline=True)
    embed.set_footer(text=client.name)
    parts: dict[str, Any] = {"embed": embed, "silent": bool(data.get("silencioso", quiet))}
    if data["nivel"] == "erro" and owner:
        parts["content"] = f"<@{owner}>"
        parts["allowed_mentions"] = discord.AllowedMentions(users=True)
    parts["view"] = buttons(data.get("botoes"), client)
    return parts


def build(data: dict, client: Client | None = None) -> dict[str, Any]:
    parts: dict[str, Any] = {"content": (str(data.get("texto") or "")[:2000]) or None}
    box = data.get("quadro")
    if isinstance(box, dict):
        embed = discord.Embed(title=(str(box.get("titulo") or "")[:256]) or None,
                              description=str(box.get("descricao") or "")[:4000] or None,
                              color=int(box.get("cor") or 0x8A4DFF), url=box.get("url") or None)
        if box.get("rodape"):
            embed.set_footer(text=str(box["rodape"])[:2048])
        parts["embed"] = embed
    parts["view"] = buttons(data.get("botoes"), client)
    return parts


def panel() -> discord.ui.View:
    actions = list(catalog().values())
    commands = [a["id"] for a in actions if a.get("tipo") != "container"] + ["help"]
    services = [a for a in actions if a.get("tipo") == "container"]
    view = discord.ui.View(timeout=None)
    for command in commands[:20]:
        view.add_item(own_button(command, "run", command))
    extras = [{"id": c, "descricao": ""} for c in commands[20:]] + services
    if extras:
        view.add_item(discord.ui.Select(
            custom_id="astro|menu||", placeholder="Serviço: iniciar, parar ou reiniciar…",
            options=[discord.SelectOption(label=a["id"][:100], value=a["id"][:100],
                                          description=(a.get("descricao") or None) and a["descricao"][:100])
                     for a in extras[:25]]))
    return view


async def send_help(interaction: discord.Interaction) -> None:
    pages = help_pages()
    await interaction.response.send_message(pages[0], ephemeral=True)
    for page in pages[1:]:
        await interaction.followup.send(page, ephemeral=True)


async def execute(action: str, argument: str, who: discord.abc.User) -> dict:
    item = catalog().get(action)
    client = clients.get(item["cliente"]) if item else None
    if client is None:
        return {"ok": False, "saida": "comando sem dono: nenhum cliente o publicou"}
    log.info("pedido de %s (%s) para %s: %s %s", who, who.id, client.name, action, argument)
    data = await ask(client, {"tipo": "comando", "acao": action, "arg": argument, "usuario": user_info(who)}, COMMAND_WAIT)
    if data is None:
        return {"ok": False, "saida": f"sem resposta de {client.name} em {COMMAND_WAIT // 60} minutos (o cliente está rodando?)"}
    return data


async def answer_command(interaction: discord.Interaction, action: str, argument: str, data: dict) -> None:
    if data.get("botoes"):
        await interaction.followup.send((data.get("saida") or label(action, argument))[:1900], view=buttons(data["botoes"]))
    else:
        await interaction.followup.send(result(action, argument, data))


class TextBox(discord.ui.Modal):
    def __init__(self, client: Client, custom_id: str, rule: dict) -> None:
        super().__init__(title=str(rule.get("titulo") or "Mensagem")[:45])
        self.client, self.custom_id = client, custom_id
        self.text = discord.ui.TextInput(label=str(rule.get("rotulo") or "Texto")[:45], style=discord.TextStyle.paragraph,
                                         max_length=1500, placeholder=(str(rule.get("dica") or "")[:100]) or None)
        self.add_item(self.text)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(thinking=True)
        await bot.button_to_client(interaction, self.client, self.custom_id, str(self.text.value))


class Bot(discord.Client):
    def __init__(self) -> None:
        intents = discord.Intents.none()
        intents.guilds = True
        intents.guild_messages = CONTENT
        intents.message_content = CONTENT
        super().__init__(intents=intents, allowed_mentions=discord.AllowedMentions.none())
        self.tree = app_commands.CommandTree(self)
        self.guild: discord.Guild | None = None
        self.category: discord.CategoryChannel | None = None
        self.ready_once = False

    async def setup_hook(self) -> None:
        MANIFESTS.mkdir(parents=True, exist_ok=True)
        load_channels()
        for name in KEYS:
            clients[name] = Client(name)
        await start_api()

    async def on_ready(self) -> None:
        if self.ready_once:
            return
        self.guild = self.get_guild(GUILD)
        if self.guild is None:
            log.error("o bot não está no servidor %s: convide-o de novo", GUILD)
            return
        self.category = next((c for c in self.guild.categories if c.name.lower() == CATEGORY.lower()), None)
        if self.category is None:
            self.category = await self.guild.create_category(CATEGORY, reason="astroverso: categoria do Astroverso")
            log.info("categoria %s criada", CATEGORY)
        await self.ensure_channel(MAIN, writable=True, owner="astroverso")
        await self.ensure_channel(SYSTEM, writable=False, owner="astroverso")
        self.tree.copy_global_to(guild=self.guild)
        await self.tree.sync(guild=self.guild)
        for client in clients.values():
            await self.prepare_channels(client)
        save_channels()
        self.ready_once = True
        log.info("conectado como %s no servidor %s; clientes: %s", self.user, self.guild.name, ", ".join(clients) or "nenhum")

    async def ensure_channel(self, name: str, writable: bool, owner: str) -> discord.TextChannel | None:
        assert self.guild is not None
        existing = self.get_channel(channels.get(name, 0)) or next((c for c in self.guild.text_channels if c.name == name), None)
        overwrites: dict[Any, discord.PermissionOverwrite] = {}
        if not writable:
            overwrites[self.guild.default_role] = discord.PermissionOverwrite(
                send_messages=False, create_public_threads=False, create_private_threads=False, send_messages_in_threads=False)
        overwrites[self.guild.me] = discord.PermissionOverwrite(
            view_channel=True, send_messages=True, embed_links=True, attach_files=True,
            read_message_history=True, add_reactions=True)
        try:
            if existing is None:
                existing = await self.guild.create_text_channel(
                    name, category=self.category, overwrites=overwrites, reason=f"astroverso: canal de {owner}")
                log.info("canal #%s criado para %s", name, owner)
            elif isinstance(existing, discord.TextChannel):
                for target, permission in overwrites.items():
                    await existing.set_permissions(target, overwrite=permission, reason=f"astroverso: {owner}")
        except discord.HTTPException as problem:
            log.warning("canal #%s de %s: sem permissão para criar ou ajustar (%s)", name, owner, problem)
            if existing is None:
                return None
        channels[name] = existing.id
        return existing if isinstance(existing, discord.TextChannel) else None

    async def prepare_channels(self, client: Client) -> dict[str, str]:
        if self.guild is None:
            return {}
        ready = {}
        for item in client.manifest.get("canais") or []:
            name = str(item.get("nome") or "")
            if NAME.match(name) and await self.ensure_channel(name, bool(item.get("escrita")), client.name):
                ready[name] = str(channels[name])
        save_channels()
        update_listeners()
        return ready

    async def target(self, data: dict, client: Client) -> discord.abc.Messageable:
        name = str(data.get("canal") or "")
        if not name and data.get("nivel"):
            app = str(data.get("app") or "")
            name = app if NAME.match(app) else SYSTEM
            if name not in channels and await self.ensure_channel(name, writable=False, owner=client.name):
                save_channels()
        found = channels.get(name)
        if found is None and str(data.get("canal_id") or "").isdigit() and int(data["canal_id"]) in channels.values():
            found = int(data["canal_id"])
        found = found or channels[MAIN]
        return self.get_channel(found) or await self.fetch_channel(found)

    async def authorized(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id in USERS:
            return True
        log.warning("recusado: %s (%s) não está autorizado", interaction.user, interaction.user.id)
        await interaction.response.send_message("sem permissão para usar o Astroverso", ephemeral=True)
        return False

    async def button_to_client(self, interaction: discord.Interaction, client: Client, custom_id: str, text: str) -> None:
        event = {"tipo": "botao", "custom_id": custom_id, "texto": text, "usuario": user_info(interaction.user),
                 "canal_id": str(interaction.channel_id),
                 "mensagem_id": str(interaction.message.id) if interaction.message else None}
        data = await ask(client, event, COMMAND_WAIT)
        if data is None:
            await interaction.followup.send(f"sem resposta de {client.name} (o cliente está rodando?)")
            return
        parts = build(data, client)
        if parts.get("content") or parts.get("embed"):
            await interaction.followup.send(**{k: v for k, v in parts.items() if v is not None})
        else:
            await interaction.followup.send("✅", ephemeral=True)

    async def on_interaction(self, interaction: discord.Interaction) -> None:
        if interaction.type != discord.InteractionType.component:
            return
        custom_id = (interaction.data or {}).get("custom_id") or ""
        if not custom_id.startswith("astro|"):
            client, rule = button_owner(custom_id)
            if client is None or not await self.authorized(interaction):
                return
            if isinstance(rule, dict) and re.fullmatch(str(rule.get("padrao") or ".*"), custom_id):
                await interaction.response.send_modal(TextBox(client, custom_id, rule))
                return
            await interaction.response.defer(thinking=True)
            await self.button_to_client(interaction, client, custom_id, "")
            return
        parts = custom_id.split("|")
        if len(parts) != 4 or not await self.authorized(interaction):
            return
        _, kind, action, argument = parts
        if kind == "menu":
            values = (interaction.data or {}).get("values") or [""]
            kind, action, argument = "run", values[0], ""
        if kind == "run" and action == "help":
            await send_help(interaction)
            return
        if kind == "cancelar":
            await interaction.response.edit_message(content="cancelado", view=None)
            return
        item = catalog().get(action)
        if not item or not ARGUMENT.match(argument):
            await interaction.response.send_message(f"{label(action, argument)} não existe mais", ephemeral=True)
            return
        if kind == "run" and item.get("confirmar"):
            await interaction.response.send_message(
                f"⚠️ confirmar {label(action, argument)}? {item.get('descricao', '')}", view=confirmation(action, argument))
            return
        if kind == "ok":
            await interaction.response.edit_message(
                content=f"⏳ {label(action, argument)} confirmado por {interaction.user.mention}", view=None)
        else:
            await interaction.response.defer(thinking=True)
        await answer_command(interaction, action, argument, await execute(action, argument, interaction.user))

    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or message.author.id not in USERS:
            return
        client = clients.get(listeners.get(message.channel.id, ""))
        if client is None:
            return
        reference = None
        if message.reference and message.reference.message_id:
            try:
                original = message.reference.resolved or await message.channel.fetch_message(message.reference.message_id)
            except discord.HTTPException:
                original = None
            if isinstance(original, discord.Message):
                reference = {"mensagem_id": str(original.id), "do_bot": original.author.id == self.user.id,
                             "texto": original.content,
                             "quadros": [{"titulo": e.title or "", "rodape": (e.footer.text if e.footer else "") or ""}
                                         for e in original.embeds],
                             "anexos": len(original.attachments)}
        event = {"tipo": "mensagem", "canal": getattr(message.channel, "name", ""), "canal_id": str(message.channel.id),
                 "mensagem_id": str(message.id), "texto": message.content, "usuario": user_info(message.author),
                 "responde_a": reference}
        data = await ask(client, event, MESSAGE_WAIT)
        if not data:
            return
        parts = {k: v for k, v in build(data, client).items() if v is not None}
        if parts.get("content") or parts.get("embed"):
            await message.reply(mention_author=False, **parts)


bot = Bot()


def failure(kind: type[web.HTTPException], reason: str) -> web.HTTPException:
    return kind(text=json.dumps({"erro": reason}), content_type="application/json")


def client_of(request: web.Request) -> Client:
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        raise failure(web.HTTPUnauthorized, "chave ausente")
    digest = hashlib.sha256(header[7:].strip().encode()).hexdigest()
    for name, expected in KEYS.items():
        if hmac.compare_digest(digest, expected):
            return clients[name]
    raise failure(web.HTTPUnauthorized, "chave inválida")


async def api_health(_: web.Request) -> web.Response:
    return web.json_response({"ok": bot.is_ready() and bot.ready_once, "clientes": {
        name: {"visto_ha_s": int(time.time() - c.seen) if c.seen else None} for name, c in clients.items()}})


async def api_me(request: web.Request) -> web.Response:
    client = client_of(request)
    client.seen = time.time()
    return web.json_response({"cliente": client.name})


async def api_client(request: web.Request) -> web.Response:
    client = client_of(request)
    manifest = await request.json()
    if not isinstance(manifest, dict):
        raise failure(web.HTTPBadRequest, "manifesto deve ser um objeto")
    manifest = {key: manifest.get(key) or [] for key in ("catalogo", "ajuda", "canais", "botoes")}
    temporary = MANIFESTS / f"{client.name}.tmp"
    temporary.write_text(json.dumps(manifest, ensure_ascii=False))
    temporary.rename(MANIFESTS / f"{client.name}.json")
    before = json.dumps(client.manifest.get("canais"), sort_keys=True)
    client.apply(manifest)
    wanted = [str(c.get("nome")) for c in manifest["canais"] if isinstance(c, dict)]
    if before != json.dumps(manifest["canais"], sort_keys=True) or not all(name in channels for name in wanted):
        ready = await bot.prepare_channels(client)
    else:
        ready = {name: str(channels[name]) for name in wanted}
        update_listeners()
    return web.json_response({"ok": True, "canais": ready, "comandos": len(manifest["catalogo"])})


async def api_events(request: web.Request) -> web.Response:
    client = client_of(request)
    client.seen = time.time()
    try:
        wait = max(0, min(int(request.query.get("espera", "25")), 50))
    except ValueError:
        wait = 25
    items = []
    try:
        items.append(await asyncio.wait_for(client.queue.get(), wait))
        while not client.queue.empty() and len(items) < 20:
            items.append(client.queue.get_nowait())
    except asyncio.TimeoutError:
        pass
    items = [event for event in items if event["id"] in pending]
    if request.transport is None or request.transport.is_closing():
        for event in items:
            client.queue.put_nowait(event)
        raise web.HTTPServiceUnavailable()
    client.seen = time.time()
    return web.json_response({"eventos": items})


async def api_answer(request: web.Request) -> web.Response:
    client = client_of(request)
    owner, future, _ = pending.get(request.match_info["id"], ("", None, 0))
    if future is None or owner != client.name:
        raise failure(web.HTTPNotFound, "evento desconhecido ou expirado")
    data = await request.json()
    if not future.done():
        future.set_result(data if isinstance(data, dict) else {})
    return web.json_response({"ok": True})


async def api_messages(request: web.Request) -> web.Response:
    client = client_of(request)
    attachment = None
    if request.content_type.startswith("multipart/"):
        form = await request.post()
        data = json.loads(form.get("dados") or "{}")
        sent = form.get("arquivo")
        if sent is not None and hasattr(sent, "file"):
            attachment = discord.File(sent.file, filename=str(data.get("arquivo_nome") or sent.filename or "arquivo"))
    else:
        data = await request.json()
    if not isinstance(data, dict):
        raise failure(web.HTTPBadRequest, "mensagem deve ser um objeto")
    if data.get("nivel") is not None and data["nivel"] not in LEVELS:
        raise failure(web.HTTPBadRequest, f"nível inválido: {data['nivel']} (use {', '.join(LEVELS)})")
    if not bot.ready_once or bot.guild is None:
        raise failure(web.HTTPServiceUnavailable, "bot desconectado do Discord")
    client.seen = time.time()
    channel = await bot.target(data, client)
    parts = notice(data, client, bot.guild.owner_id or 0) if data.get("nivel") else build(data, client)
    if attachment is not None:
        parts["file"] = attachment
    parts.setdefault("silent", bool(data.get("silencioso")))
    parts = {key: value for key, value in parts.items() if value is not None}
    try:
        if str(data.get("responde_a") or "").isdigit():
            try:
                original = await channel.fetch_message(int(data["responde_a"]))
                message = await original.reply(mention_author=False, **parts)
            except discord.NotFound:
                message = await channel.send(**parts)
        else:
            message = await channel.send(**parts)
    except discord.HTTPException as problem:
        log.warning("%s: o Discord recusou a mensagem: %s", client.name, problem)
        raise failure(web.HTTPBadGateway, str(problem))
    return web.json_response({"mensagem_id": str(message.id), "canal_id": str(message.channel.id)})


async def api_reactions(request: web.Request) -> web.Response:
    client = client_of(request)
    data = await request.json()
    channel = await bot.target({"canal_id": data.get("canal_id"), "canal": data.get("canal")}, client)
    try:
        await channel.get_partial_message(int(data["mensagem_id"])).add_reaction(str(data["emoji"]))
    except (KeyError, ValueError, discord.HTTPException) as problem:
        log.warning("%s: reação recusada: %s", client.name, problem)
        raise failure(web.HTTPBadRequest, str(problem))
    return web.json_response({"ok": True})


async def start_api() -> None:
    app = web.Application(client_max_size=26 * 1024 * 1024)
    app.add_routes([
        web.get("/v1/saude", api_health),
        web.get("/v1/eu", api_me),
        web.put("/v1/cliente", api_client),
        web.get("/v1/eventos", api_events),
        web.post("/v1/eventos/{id}/resposta", api_answer),
        web.post("/v1/mensagens", api_messages),
        web.post("/v1/reacoes", api_reactions),
    ])
    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", PORT).start()
    log.info("API na porta %s", PORT)


@bot.tree.command(name="astro", description="Comandos do Astroverso")
@app_commands.describe(command="ex.: network:summary (comece a digitar; help mostra tudo)", argument="opcional")
async def astro(interaction: discord.Interaction, command: str, argument: str = "") -> None:
    if not await bot.authorized(interaction):
        return
    if command == "help":
        await send_help(interaction)
        return
    if command == "panel":
        await interaction.response.send_message("🛰️ **Painel do Astroverso**", view=panel())
        return
    item = catalog().get(command)
    if not item:
        await interaction.response.send_message(f"comando desconhecido: `{command}` (veja `/astro command:help`)", ephemeral=True)
        return
    if not ARGUMENT.match(argument):
        await interaction.response.send_message("argumento inválido (só letras, números, ponto, hífen e _)", ephemeral=True)
        return
    if item.get("confirmar"):
        await interaction.response.send_message(
            f"⚠️ confirmar {label(command, argument)}? {item.get('descricao', '')}", view=confirmation(command, argument))
        return
    await interaction.response.defer(thinking=True)
    await answer_command(interaction, command, argument, await execute(command, argument, interaction.user))


@astro.autocomplete("command")
async def complete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    options = [{"id": "help", "descricao": "Ajuda: todas as operações, quando rodam e os comandos"},
               {"id": "panel", "descricao": "Painel: um botão para cada comando"}] + list(catalog().values())
    return [
        app_commands.Choice(name=f"{a['id']} — {a.get('descricao', '')}"[:100], value=a["id"])
        for a in options if current.lower() in a["id"].lower()
    ][:25]


bot.run(TOKEN, log_handler=None)
