import asyncio
import json
import logging
import os
import pathlib
import re
import time
import uuid

import discord
from discord import app_commands

FILA = pathlib.Path("/fila")
PEDIDOS = FILA / "pedidos"
RESPOSTAS = FILA / "respostas"
SAIDA = FILA / "saida"
TMP = FILA / "tmp"
CATALOGO = FILA / "catalogo.json"
AJUDA = FILA / "ajuda.json"
TOKEN = os.environ["DISCORD_TOKEN"]
CANAL = int(os.environ["DISCORD_CHANNEL"])
CANAIS = {nome: int(id_) for nome, _, id_ in (item.partition("=") for item in os.environ.get("DISCORD_CHANNELS", "").split())
          if id_.isdigit()}
USUARIOS = {int(x) for x in os.environ.get("DISCORD_USERS", "").replace(",", " ").split()}
ARGUMENTO = re.compile(r"^[A-Za-z0-9._-]{0,64}$")
ESPERA = 840

logging.basicConfig(level=logging.INFO, format="[discord] %(message)s")
logging.getLogger("discord").setLevel(logging.WARNING)
logging.getLogger("discord.client").setLevel(logging.ERROR)
log = logging.getLogger("astro")


def catalogo():
    try:
        return {a["id"]: a for a in json.loads(CATALOGO.read_text())}
    except (OSError, ValueError, KeyError, TypeError):
        return {}


def gravar(pasta, nome, dados):
    tmp = TMP / f"{nome}.json"
    tmp.write_text(json.dumps(dados, ensure_ascii=False))
    tmp.rename(pasta / f"{nome}.json")


def rotulo(acao, arg):
    return f"`{acao}{' ' + arg if arg else ''}`"


def resultado(acao, arg, dados):
    icone = "✅" if dados.get("ok") else "❌"
    saida = (dados.get("saida") or "").strip().replace("```", "'''")
    if len(saida) > 1800:
        saida = "…\n" + saida[-1800:]
    texto = f"{icone} {rotulo(acao, arg)}"
    return texto + (f"\n```\n{saida}\n```" if saida else "")


def ajuda():
    try:
        itens = json.loads(AJUDA.read_text())
    except (OSError, ValueError):
        itens = []
    if not itens:
        acoes = catalogo()
        if not acoes:
            return ["o catálogo de comandos ainda não foi gerado no servidor"]
        return ["**Comandos**\n" + "\n".join(f"`{a['id']}` — {a['descricao']}" for a in acoes.values())]
    blocos = ["**Operações do Astroverso** (`/astro command:<comando> argument:<opcional>`)"]
    grupo = None
    for item in itens:
        if item.get("grupo") != grupo:
            grupo = item.get("grupo")
            blocos.append(f"\n__{grupo}__")
        comando = item.get("comando") or ""
        comando = f"`{comando}`" if comando and comando != "-" else "só pelo assistente"
        blocos.append(f"**{item['nome']}** — {item['descricao']}\n  ⏱ {item['quando']} · 💬 {comando}")
    mensagens, atual = [], ""
    for bloco in blocos:
        if len(atual) + len(bloco) + 1 > 1900:
            mensagens.append(atual)
            atual = ""
        atual += ("\n" if atual else "") + bloco
    if atual:
        mensagens.append(atual)
    return mensagens


async def executar(acao, arg, usuario):
    pedido = uuid.uuid4().hex
    gravar(PEDIDOS, pedido, {"id": pedido, "acao": acao, "arg": arg, "usuario": str(usuario.id), "nome": str(usuario)})
    log.info("pedido de %s (%s): %s %s", usuario, usuario.id, acao, arg)
    resposta = RESPOSTAS / f"{pedido}.json"
    fim = time.monotonic() + ESPERA
    while time.monotonic() < fim:
        if resposta.exists():
            try:
                dados = json.loads(resposta.read_text())
            except ValueError:
                await asyncio.sleep(0.5)
                continue
            resposta.unlink(missing_ok=True)
            return dados
        await asyncio.sleep(1)
    return {"ok": False, "saida": "sem resposta do servidor em 14 minutos (o executor astroverso-discord-runner está ativo?)"}


def botao(rotulo_botao, tipo, acao="", arg="", estilo=discord.ButtonStyle.secondary):
    return discord.ui.Button(label=rotulo_botao[:80], style=estilo, custom_id=f"astro|{tipo}|{acao}|{arg}"[:100])


def confirmacao(acao, arg):
    view = discord.ui.View(timeout=None)
    view.add_item(botao("Confirmar", "ok", acao, arg, discord.ButtonStyle.danger))
    view.add_item(botao("Cancelar", "cancelar"))
    return view


def botoes(lista):
    if not lista:
        return discord.utils.MISSING
    view = discord.ui.View(timeout=None)
    for item in lista[:5]:
        view.add_item(botao(item.get("rotulo", "?"), "run", item.get("acao", ""), item.get("arg", "")))
    return view


class Bot(discord.Client):
    def __init__(self):
        intents = discord.Intents.none()
        intents.guilds = True
        super().__init__(intents=intents, allowed_mentions=discord.AllowedMentions.none())
        self.tree = app_commands.CommandTree(self)
        self.sincronizado = False

    async def setup_hook(self):
        for pasta in (PEDIDOS, RESPOSTAS, SAIDA, TMP):
            pasta.mkdir(parents=True, exist_ok=True)
        self.loop.create_task(self.enviar_saida())

    async def on_ready(self):
        if self.sincronizado:
            return
        canal = await self.fetch_channel(CANAL)
        self.tree.copy_global_to(guild=canal.guild)
        await self.tree.sync(guild=canal.guild)
        self.sincronizado = True
        log.info("conectado como %s; comando /astro no servidor %s, avisos em #%s", self.user, canal.guild.name, canal.name)

    async def enviar_saida(self):
        await self.wait_until_ready()
        principal = await self.fetch_channel(CANAL)
        canais = {}
        for nome, id_ in CANAIS.items():
            try:
                canais[nome] = await self.fetch_channel(id_)
            except discord.HTTPException as erro:
                log.warning("canal de %s indisponível, os avisos dele vão para #%s: %s", nome, principal.name, erro)
        if canais:
            log.info("avisos por canal: %s", ", ".join(f"{n} → #{c.name}" for n, c in canais.items()))
        while not self.is_closed():
            for arquivo in sorted(SAIDA.glob("*.json")):
                try:
                    dados = json.loads(arquivo.read_text())
                except ValueError:
                    log.warning("aviso ilegível descartado: %s", arquivo.name)
                    arquivo.unlink(missing_ok=True)
                    continue
                canal = canais.get(dados.get("canal", ""), principal)
                try:
                    await canal.send(dados.get("texto", "")[:1900], view=botoes(dados.get("botoes")),
                                     silent=bool(dados.get("silencioso")))
                except discord.HTTPException as erro:
                    log.warning("falha ao enviar aviso (tento de novo): %s", erro)
                    break
                arquivo.unlink(missing_ok=True)
            await asyncio.sleep(2)

    async def autorizado(self, interacao):
        if interacao.user.id in USUARIOS:
            return True
        log.warning("recusado: %s (%s) não está autorizado", interacao.user, interacao.user.id)
        await interacao.response.send_message("sem permissão para comandar este servidor", ephemeral=True)
        return False

    async def on_interaction(self, interacao):
        if interacao.type != discord.InteractionType.component:
            return
        partes = ((interacao.data or {}).get("custom_id") or "").split("|")
        if len(partes) != 4 or partes[0] != "astro":
            return
        if not await self.autorizado(interacao):
            return
        _, tipo, acao, arg = partes
        if tipo == "cancelar":
            await interacao.response.edit_message(content="cancelado", view=None)
            return
        item = catalogo().get(acao)
        if not item or not ARGUMENTO.match(arg):
            await interacao.response.send_message(f"{rotulo(acao, arg)} não existe mais", ephemeral=True)
            return
        if tipo == "run" and item.get("confirmar"):
            await interacao.response.send_message(
                f"⚠️ confirmar {rotulo(acao, arg)}? {item['descricao']}", view=confirmacao(acao, arg))
            return
        if tipo == "ok":
            await interacao.response.edit_message(
                content=f"⏳ {rotulo(acao, arg)} confirmado por {interacao.user.mention}", view=None)
        else:
            await interacao.response.defer(thinking=True)
        dados = await executar(acao, arg, interacao.user)
        await interacao.followup.send(resultado(acao, arg, dados))


bot = Bot()


@bot.tree.command(name="astro", description="Comandos do Astroverso")
@app_commands.describe(command="ex.: backup:cloud (comece a digitar; help mostra tudo)", argument="opcional, ex.: proton")
async def astro(interacao: discord.Interaction, command: str, argument: str = ""):
    comando, argumento = command, argument
    if not await bot.autorizado(interacao):
        return
    if comando == "help":
        mensagens = ajuda()
        await interacao.response.send_message(mensagens[0], ephemeral=True)
        for mensagem in mensagens[1:]:
            await interacao.followup.send(mensagem, ephemeral=True)
        return
    item = catalogo().get(comando)
    if not item:
        await interacao.response.send_message(f"comando desconhecido: `{comando}` (veja `/astro command:help`)", ephemeral=True)
        return
    if not ARGUMENTO.match(argumento):
        await interacao.response.send_message("argumento inválido (só letras, números, ponto, hífen e _)", ephemeral=True)
        return
    if item.get("confirmar"):
        await interacao.response.send_message(
            f"⚠️ confirmar {rotulo(comando, argumento)}? {item['descricao']}", view=confirmacao(comando, argumento))
        return
    await interacao.response.defer(thinking=True)
    dados = await executar(comando, argumento, interacao.user)
    await interacao.followup.send(resultado(comando, argumento, dados))


@astro.autocomplete("command")
async def completar(interacao: discord.Interaction, atual: str):
    opcoes = [{"id": "help", "descricao": "Ajuda: todas as operações, quando rodam e os comandos"}] + list(catalogo().values())
    return [
        app_commands.Choice(name=f"{a['id']} — {a['descricao']}"[:100], value=a["id"])
        for a in opcoes if atual.lower() in a["id"].lower()
    ][:25]


bot.run(TOKEN, log_handler=None)
