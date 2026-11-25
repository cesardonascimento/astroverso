from __future__ import annotations

import base64
import hashlib
import json
import re
import secrets
import time
import urllib.error
import urllib.request
from pathlib import Path

from kit import config, container, discord, docs, net, routes, run, ui, validate

APP = "discord"
NAME = "astroverso-discord"
PORT = 8080
PYTHON_VERSION = "3.13.18"
DISCORD_PY_VERSION = "2.7.1"
REPOSITORY = "localhost/astroverso-discord"
BOT = Path(__file__).with_name("bot")
DOCS = Path(__file__).with_name("docs")
ICON = Path(__file__).resolve().parents[2] / "logo" / "icone.png"
API = "https://discord.com/api/v10"
PERMISSIONS = 378225642512
MESSAGE_CONTENT = (1 << 18) | (1 << 19)
SNOWFLAKE = re.compile(r"^\d{17,20}$")


def folder() -> Path:
    return config.state(APP)


def keys_folder() -> Path:
    return folder() / "clients"


def image() -> str:
    digest = hashlib.sha256()
    for part in (PYTHON_VERSION, DISCORD_PY_VERSION, (BOT / "Containerfile").read_text(), (BOT / "bot.py").read_text()):
        digest.update(part.encode())
    return f"{REPOSITORY}:{digest.hexdigest()[:12]}"


def address(domain: str) -> str:
    return f"discord.{domain}"


def spec() -> container.Container:
    return container.Container(
        name=NAME,
        image=image(),
        description="Astroverso discord: bot e API",
        volumes=[container.Volume(folder() / "data", "/data")],
        env_file=config.env_file(APP),
        health=f"python -I -c \"import urllib.request; urllib.request.urlopen('http://127.0.0.1:{PORT}/v1/saude', timeout=5)\"",
    )


def installed() -> bool:
    return container.active(NAME)


def snowflake(value: str) -> str:
    value = value.strip()
    if not SNOWFLAKE.match(value):
        raise ValueError("ID do Discord: só números, de 17 a 20 dígitos")
    return value


def _discord(token: str, method: str, path: str, payload: object = None) -> tuple[int, dict | list]:
    headers = {"Authorization": f"Bot {token}", "User-Agent": "DiscordBot (astroverso, 1)", "Content-Type": "application/json"}
    data = None if payload is None else json.dumps(payload).encode()
    try:
        with urllib.request.urlopen(urllib.request.Request(f"{API}/{path}", data, headers, method=method), timeout=30) as response:
            return response.status, json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as problem:
        try:
            return problem.code, json.loads(problem.read() or b"{}")
        except ValueError:
            return problem.code, {}
    except (OSError, ValueError):
        return 0, {}


def check_token(token: str) -> tuple[str, str]:
    code, body = _discord(token, "GET", "users/@me")
    if code == 0:
        return "", "o Discord não respondeu: confira a internet desta máquina"
    if code != 200 or not isinstance(body, dict):
        return "", f"o Discord recusou esse token (HTTP {code}): copiado pela metade ou trocado depois?"
    return str(body.get("id", "")), str(body.get("username", ""))


def message_content(token: str) -> bool:
    code, body = _discord(token, "GET", "applications/@me")
    return code == 200 and isinstance(body, dict) and bool(int(body.get("flags") or 0) & MESSAGE_CONTENT)


def guilds(token: str) -> list[dict]:
    code, body = _discord(token, "GET", "users/@me/guilds")
    return [item for item in body if isinstance(item, dict)] if code == 200 and isinstance(body, list) else []


def owner(token: str, guild: str) -> str:
    code, body = _discord(token, "GET", f"guilds/{guild}")
    return str(body.get("owner_id", "")) if code == 200 and isinstance(body, dict) else ""


def invite(bot_id: str) -> str:
    return f"https://discord.com/oauth2/authorize?client_id={bot_id}&scope=bot+applications.commands&permissions={PERMISSIONS}"


def _token(reuse: bool) -> tuple[str, str]:
    saved = config.load(APP).get("DISCORD_TOKEN", "")
    if reuse and saved:
        bot_id, name = check_token(saved)
        if bot_id:
            ui.ok(f"token salvo continua válido: bot {name}")
            return saved, bot_id
        ui.warn(f"o token salvo não vale mais ({name})")
    ui.note(
        "O bot é uma conta do Discord que só o Astroverso usa. Crie uma aplicação no portal de desenvolvedores do "
        "Discord, com o bot privado e a leitura de mensagens ligada, e copie o token dele."
    )
    ui.link("passo a passo", docs.link(DOCS / "discord.md", "criar-o-bot"))
    while True:
        token = ui.secret("token do bot", confirm=False)
        bot_id, name = check_token(token)
        if bot_id:
            ui.ok(f"token válido: bot {name}")
            config.save(APP, {"DISCORD_TOKEN": token})
            return token, bot_id
        ui.warn(name)


def _message_content(token: str) -> str:
    if message_content(token):
        ui.ok("leitura de mensagens ligada: o bot lê as mensagens dos canais que os clientes escutam")
        return "yes"
    ui.warn("leitura de mensagens desligada: avisos, comandos e botões funcionam, mas o bot não lê as mensagens dos canais")
    ui.link("como ligar", docs.link(DOCS / "discord.md", "ligar-a-leitura-de-mensagens"))
    return "no"


def _guild(token: str, bot_id: str, reuse: bool) -> dict:
    saved = config.load(APP).get("DISCORD_GUILD", "")
    found = guilds(token)
    if not found:
        ui.note(
            "Agora convide o bot para o servidor do Discord que vai ser do Astroverso (pode ser um servidor novo, só "
            "seu). O convite já pede as permissões para o bot criar a categoria e os canais."
        )
        ui.link("convite do bot", invite(bot_id))
        ui.link("passo a passo", docs.link(DOCS / "discord.md", "convidar-o-bot"))
        while not found:
            if not ui.confirm("Já convidou?", default=True):
                ui.fail("o bot precisa estar num servidor do Discord: convide e rode a instalação de novo")
            found = guilds(token)
            if not found:
                ui.warn("o bot ainda não aparece em nenhum servidor")
    chosen = next((item for item in found if item.get("id") == saved), None) if reuse else None
    if chosen is None:
        if len(found) == 1:
            chosen = found[0]
        else:
            names = [str(item.get("name", "?")) for item in found]
            chosen = found[ui.menu("Em qual servidor o Astroverso vai ficar?", names)]
    ui.ok(f"servidor do Discord: {chosen.get('name', '?')}")
    return chosen


def _users(token: str, guild: str, reuse: bool) -> str:
    saved = config.load(APP).get("DISCORD_USERS", "")
    if reuse and saved:
        return saved
    boss = owner(token, guild)
    if not boss:
        ui.fail("não foi possível ler o dono do servidor no Discord: confira se o bot ainda está nele")
    ui.note("Só quem estiver autorizado usa os comandos, os botões e as mensagens do bot. O dono do servidor já entra.")
    extra: list[str] = []
    if ui.confirm("Autorizar mais alguém?", default=False):
        ui.link("como copiar o ID de alguém", docs.link(DOCS / "discord.md", "copiar-ids"))
        extra = ui.ask_list("ID do usuário (Enter vazio para terminar)", validate=snowflake)
    return " ".join(dict.fromkeys([boss, *extra]))


def client_names() -> list[str]:
    return [item.partition("=")[0] for item in config.load(APP).get("DISCORD_CLIENTS", "").split() if item.partition("=")[2]]


def client_key(name: str) -> str:
    path = keys_folder() / f"{name}.key"
    return path.read_text().strip() if path.exists() else ""


def _ensure_keys(names: list[str]) -> None:
    keys_folder().mkdir(mode=0o700, exist_ok=True)
    listed = []
    for name in names:
        path = keys_folder() / f"{name}.key"
        if not path.exists():
            path.touch(mode=0o600)
            path.write_text(secrets.token_urlsafe(32) + "\n")
            ui.ok(f"chave nova do cliente {name}")
        listed.append(f"{name}={hashlib.sha256(client_key(name).encode()).hexdigest()}")
    config.save(APP, {"DISCORD_CLIENTS": " ".join(listed)})


def _avatar(token: str) -> None:
    if not ICON.exists():
        return
    digest = hashlib.sha256(ICON.read_bytes()).hexdigest()
    mark = folder() / ".avatar"
    if mark.exists() and mark.read_text().strip() == digest:
        return
    data = "data:image/png;base64," + base64.b64encode(ICON.read_bytes()).decode()
    code, _ = _discord(token, "PATCH", "users/@me", {"avatar": data})
    if code == 200:
        mark.write_text(digest + "\n")
        ui.ok("foto do bot trocada pelo logo do Astroverso")
    elif code == 429:
        ui.warn("o Discord limita trocas de foto seguidas: o logo entra na próxima instalação")
    else:
        ui.warn(f"o Discord recusou a foto do bot (HTTP {code}): troque à mão no portal, com {ICON}")


def health() -> dict:
    command = f"import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:{PORT}/v1/saude', timeout=5).read().decode())"
    if not installed() or not run.succeeds(["podman", "exec", NAME, "python", "-I", "-c", command]):
        return {}
    try:
        return json.loads(container.exec(NAME, ["python", "-I", "-c", command]))
    except ValueError:
        return {}


def _wait_connected(timeout: float = 90) -> None:
    ui.info("esperando o bot conectar ao Discord...")
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if health().get("ok"):
            ui.ok("bot conectado ao Discord")
            return
        time.sleep(2)
    logs = run.capture(["journalctl", "--user", "-u", container.unit(NAME), "-n", "20", "--no-pager", "-o", "cat"])
    if logs:
        ui.prefixed(logs)
    ui.fail("o bot não conectou ao Discord (veja o log acima)")


def _drop_old_images() -> None:
    listed = run.capture(["podman", "images", "--format", "{{.Repository}}:{{.Tag}}", REPOSITORY])
    for item in listed.splitlines():
        if item.strip() and item.strip() != image():
            container.remove_image(item.strip())


def _check_address(domain: str) -> None:
    url = f"https://{address(domain)}"
    for _ in range(30):
        try:
            discord.whoami()
            break
        except discord.DiscordError:
            time.sleep(2)
    else:
        ui.warn(f"{url} ainda não responde: ele depende do Caddy e do DNS do app network (confira em Resumo)")
        return
    ui.ok(f"API no ar em {url}")
    if discord.notify(APP, "sucesso", "Bot do Astroverso no ar", f"Instalado em {net.hostname()}."):
        ui.ok("mensagem de teste enviada ao canal #discord")


def install(reuse: bool) -> None:
    domain = config.domain()
    token, bot_id = _token(reuse)
    reading = _message_content(token)
    guild = _guild(token, bot_id, reuse)
    users = _users(token, str(guild["id"]), reuse)
    config.save(APP, {"MODE": "server", "DISCORD_GUILD": str(guild["id"]), "DISCORD_USERS": users, "DISCORD_MESSAGE_CONTENT": reading})
    local = net.hostname()
    _ensure_keys(list(dict.fromkeys([local, *client_names()])))
    _avatar(token)
    container.prepare()
    (folder() / "data").mkdir(mode=0o700, exist_ok=True)
    container.build(image(), BOT / "Containerfile", {"PYTHON_VERSION": PYTHON_VERSION, "DISCORD_PY_VERSION": DISCORD_PY_VERSION})
    container.start(spec())
    _wait_connected()
    _drop_old_images()
    routes.publish(APP, [routes.Route(address(domain), f"http://{NAME}:{PORT}")])
    discord.save(f"https://{address(domain)}", client_key(local))
    _check_address(domain)


def show_key() -> None:
    names = client_names()
    if not names:
        ui.fail("nenhum cliente cadastrado: instale primeiro")
    choice = ui.menu("Qual cliente?", names + ["Voltar"])
    if choice == len(names):
        return
    ui.warn("a chave é a senha do cliente: copie para a outra máquina e não mostre a ninguém")
    ui.info(f"endereço: https://{address(config.saved_domain())}")
    ui.info(f"chave de {names[choice]}: {client_key(names[choice])}")


def add_client() -> None:
    names = client_names()
    if not names:
        ui.fail("instale primeiro")

    def new_name(value: str) -> str:
        value = validate.name(value)
        if len(value) > 32:
            raise ValueError("no máximo 32 caracteres")
        if value in names:
            raise ValueError(f"o cliente {value} já existe")
        return value

    ui.note("Cada máquina ou projeto que usa o bot é um cliente, com a própria chave. Use o nome da máquina (ou do projeto).")
    name = ui.ask("nome do cliente novo", validate=new_name)
    _ensure_keys([*names, name])
    container.restart(spec())
    ui.info(f"endereço: https://{address(config.saved_domain())}")
    ui.info(f"chave de {name}: {client_key(name)}")
    ui.note("Na outra máquina, instale o app discord, escolha usar o bot de outra máquina e cole o endereço e a chave.")


def remove() -> None:
    container.remove(NAME)
    listed = run.capture(["podman", "images", "--format", "{{.Repository}}:{{.Tag}}", REPOSITORY]) if run.succeeds(["podman", "--version"]) else ""
    for item in listed.splitlines():
        if item.strip():
            container.remove_image(item.strip())
    routes.withdraw(APP)


def summary() -> None:
    values = config.load(APP)
    state = health()
    domain = config.saved_domain()
    ui.section("Bot")
    ui.table([
        ["Container", ui.good("no ar") if installed() else ui.bad("parado")],
        ["Discord", ui.good("conectado") if state.get("ok") else ui.bad("desconectado")],
        ["Endereço da API", f"https://{address(domain)}" if domain else "-"],
        ["Leitura de mensagens", ui.good("ligada") if values.get("DISCORD_MESSAGE_CONTENT") == "yes" else ui.pending("desligada")],
        ["Usuários autorizados", str(len(values.get("DISCORD_USERS", "").split()))],
    ])
    ui.section("Clientes")
    seen = state.get("clientes") or {}
    rows: list[list[str | ui.Cell]] = []
    for name in client_names():
        ago = (seen.get(name) or {}).get("visto_ha_s")
        rows.append([name, ui.off("nunca apareceu") if ago is None else ui.good(_ago(int(ago)))])
    ui.table(rows, ["Cliente", "Última conexão"])


def _ago(seconds: int) -> str:
    if seconds < 120:
        return "agora há pouco"
    if seconds < 7200:
        return f"há {seconds // 60} min"
    if seconds < 172800:
        return f"há {seconds // 3600} h"
    return f"há {seconds // 86400} dias"
