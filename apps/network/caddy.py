from __future__ import annotations

import json
import socket
import ssl
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

from kit import config, container, distro, docs, run, ui, validate

from . import adguard

APP = "network"
NAME = "astroverso-network-caddy"
VERSION = "2.11.9"
CLOUDFLARE_VERSION = "v0.2.4"
IMAGE = f"localhost/astroverso-network-caddy:{VERSION}-{CLOUDFLARE_VERSION}"
BASE = f"docker.io/library/caddy:{VERSION}-alpine"
BUILDER = f"docker.io/library/caddy:{VERSION}-builder-alpine"
CONTAINERFILE = Path(__file__).with_name("caddy.Containerfile")
DOCS = Path(__file__).with_name("docs")
API = "https://api.cloudflare.com/client/v4"
HOST = "host.containers.internal"
PORTS = ["http", "https", "443/udp"]


def folder() -> Path:
    return config.state(APP) / "caddy"


def caddyfile() -> Path:
    return folder() / "etc" / "Caddyfile"


def env_file() -> Path:
    return folder() / "caddy.env"


def devices_file() -> Path:
    return folder() / "devices.json"


def routes_folder() -> Path:
    return config.home() / "routes"


def spec() -> container.Container:
    return container.Container(
        name=NAME,
        image=IMAGE,
        description="Astroverso network: Caddy (endereços com HTTPS)",
        volumes=[
            container.Volume(folder() / "etc", "/etc/caddy"),
            container.Volume(folder() / "data", "/data"),
            container.Volume(folder() / "config", "/config"),
        ],
        ports=["80:80", "443:443", "443:443/udp"],
        env_file=env_file(),
        health="wget -q --spider http://127.0.0.1:2019/config/",
    )


def installed() -> bool:
    return container.active(NAME)


def _api(token: str, path: str) -> dict | None:
    request = urllib.request.Request(f"{API}/{path}", headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as problem:
        try:
            return json.loads(problem.read())
        except ValueError:
            return {"success": False}
    except (OSError, ValueError):
        return None


def check_token(token: str, domain: str) -> str:
    verify = _api(token, "user/tokens/verify")
    if verify is None:
        return "a Cloudflare não respondeu: confira a internet desta máquina"
    if not verify.get("success") or (verify.get("result") or {}).get("status") != "active":
        return "a Cloudflare não aceitou esse token (copiado pela metade, apagado ou desativado?)"
    labels = domain.split(".")
    for start in range(len(labels) - 1):
        zone = ".".join(labels[start:])
        found = _api(token, f"zones?name={zone}") or {}
        if (found.get("result_info") or {}).get("count") == 1:
            return ""
    return f"o token não enxerga a zona de {domain}: confira a permissão Zone → Zone → Read restrita a ela"


def saved_token() -> str:
    try:
        for line in env_file().read_text().splitlines():
            if line.startswith("CLOUDFLARE_API_TOKEN="):
                return line.split("=", 1)[1]
    except FileNotFoundError:
        pass
    return ""


def _save_token(token: str) -> None:
    folder().mkdir(parents=True, exist_ok=True, mode=0o700)
    path = env_file()
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.touch(mode=0o600)
    temporary.chmod(0o600)
    temporary.write_text(f"CLOUDFLARE_API_TOKEN={token}\n")
    temporary.replace(path)


def devices() -> list[dict]:
    try:
        return json.loads(devices_file().read_text())
    except (FileNotFoundError, ValueError):
        return []


def _save_devices(items: list[dict]) -> None:
    folder().mkdir(parents=True, exist_ok=True, mode=0o700)
    devices_file().write_text(json.dumps(items, indent=2, ensure_ascii=False) + "\n")


def _device_target(item: dict) -> str:
    return f"{'https+insecure' if item.get('https') else 'http'}://{item['ip']}:{item['port']}"


def app_routes() -> list[tuple[str, str, str]]:
    found: list[tuple[str, str, str]] = []
    if not routes_folder().is_dir():
        return found
    for path in sorted(routes_folder().glob("*.json")):
        try:
            items = json.loads(path.read_text())
        except ValueError:
            ui.warn(f"rotas ignoradas, arquivo inválido: {path}")
            continue
        for item in items if isinstance(items, list) else []:
            if isinstance(item, dict) and item.get("host") and item.get("target"):
                found.append((str(item["host"]), str(item["target"]), f"app {path.stem}"))
    return found


def routes(domain: str) -> list[tuple[str, str, str]]:
    own = [(f"adguard.{domain}", f"http://{HOST}:{adguard.WEB_PORT}", "network")]
    named = [(f"{item['name']}.{domain}", _device_target(item), "aparelho da rede") for item in devices()]
    seen: set[str] = set()
    result = []
    for host, target, origin in own + app_routes() + named:
        if host not in seen:
            seen.add(host)
            result.append((host, target, origin))
    return result


def _upstream(target: str, indent: str) -> str:
    if target.startswith("https+insecure://"):
        address = target.removeprefix("https+insecure://")
        return (
            f"{indent}reverse_proxy https://{address} {{\n{indent}\ttransport http {{\n"
            f"{indent}\t\ttls_insecure_skip_verify\n{indent}\t}}\n{indent}}}\n"
        )
    return f"{indent}reverse_proxy {target}\n"


def render(domain: str) -> str:
    inside, outside = [], []
    for host, target, _ in routes(domain):
        label = host.removesuffix(f".{domain}")
        (inside if host.endswith(f".{domain}") and "." not in label else outside).append((host, target))
    text = "{\n\tacme_dns cloudflare {env.CLOUDFLARE_API_TOKEN}\n}\n\n" + f"*.{domain} {{\n"
    for index, (host, target) in enumerate(inside, 1):
        text += f"\t@route{index} host {host}\n\thandle @route{index} {{\n{_upstream(target, chr(9) * 2)}\t}}\n\n"
    text += "\thandle {\n\t\tabort\n\t}\n}\n"
    for host, target in outside:
        text += f"\n{host} {{\n{_upstream(target, chr(9))}}}\n"
    return text


def _write_caddyfile(domain: str) -> bool:
    for name in ("etc", "data", "config"):
        (folder() / name).mkdir(parents=True, exist_ok=True, mode=0o700)
    content = render(domain)
    try:
        if caddyfile().read_text() == content:
            return False
    except FileNotFoundError:
        pass
    caddyfile().write_text(content)
    return True


def reload() -> None:
    domain = config.saved_domain()
    changed = _write_caddyfile(domain)
    if not installed():
        return
    try:
        container.exec(NAME, ["caddy", "reload", "--config", "/etc/caddy/Caddyfile", "--adapter", "caddyfile"])
    except SystemExit:
        ui.fail("o Caddy recusou a configuração nova (veja o erro acima)")
    if changed:
        ui.ok("endereços do Caddy atualizados, sem reiniciar")


def _token(reuse: bool, domain: str) -> None:
    current = saved_token()
    if reuse and current and not check_token(current, domain):
        ui.ok("token da Cloudflare salvo continua válido")
        return
    ui.note(
        f"O Caddy precisa de uma chave (token) da Cloudflare, onde fica o DNS de {domain}, para provar ao Let's "
        f"Encrypt que o domínio é seu. Crie um token com acesso só à zona {domain} e sem data de expiração."
    )
    ui.link("passo a passo", docs.link(DOCS / "cloudflare.md", "criar-o-token"))
    while True:
        token = ui.secret("token da Cloudflare", confirm=False)
        problem = check_token(token, domain)
        if not problem:
            break
        ui.warn(problem)
    _save_token(token)
    ui.ok("token da Cloudflare conferido e guardado")


def _wait_certificate(domain: str, timeout: float = 180) -> None:
    ui.info(f"pedindo o cadeado (certificado) de *.{domain} ao Let's Encrypt, pode levar até 3 minutos...")
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if certificate(domain):
            ui.ok(f"cadeado válido para *.{domain}")
            return
        time.sleep(3)
    logs = run.capture(["journalctl", "--user", "-u", container.unit(NAME), "-n", "80", "--no-pager", "-o", "cat"])
    problems = [line for line in logs.splitlines() if "error" in line.lower()][-5:]
    if problems:
        ui.prefixed("\n".join(problems))
    ui.warn("o cadeado ainda não saiu: o Caddy continua tentando sozinho (confira em Resumo da rede)")
    ui.link("causas comuns", docs.link(DOCS / "cloudflare.md", "quando-o-cadeado-demora"))


def certificate(domain: str) -> str:
    context = ssl.create_default_context()
    try:
        with socket.create_connection(("127.0.0.1", 443), timeout=5) as raw:
            with context.wrap_socket(raw, server_hostname=f"astroverso-teste.{domain}") as tls:
                expires = tls.getpeercert().get("notAfter", "")
    except (OSError, ssl.SSLError, ValueError):
        return ""
    return datetime.fromtimestamp(ssl.cert_time_to_seconds(expires)).strftime("%d/%m/%Y") if expires else ""


def install(reuse: bool) -> None:
    ui.step("Caddy: endereços com HTTPS")
    domain = config.domain()
    ui.note(
        f"O Caddy dá a cada serviço um endereço próprio, como adguard.{domain}, com cadeado (HTTPS) de verdade, "
        "emitido de graça pelo Let's Encrypt. Dentro e fora de casa, o endereço é o mesmo."
    )
    _token(reuse, domain)
    if not reuse and not devices():
        ui.note(
            "Aparelhos da rede com painel na web (roteador, impressora, um serviço em outro computador) também podem "
            f"ganhar um endereço, como roteador.{domain}. Dá para fazer isso agora ou depois, pela ação Endereços de "
            "aparelhos da rede."
        )
        if ui.confirm("Criar endereços para aparelhos agora?", default=False):
            manage_devices(apply=False)
    run.sudo_prepare("liberar as portas 80 e 443 no firewall")
    container.prepare()
    distro.firewall_open(PORTS)
    container.build(IMAGE, CONTAINERFILE, {"CADDY_VERSION": VERSION, "CLOUDFLARE_VERSION": CLOUDFLARE_VERSION})
    container.remove_image(BUILDER)
    _write_caddyfile(domain)
    container.start(spec())
    reload()
    _wait_certificate(domain)
    for host, _, _ in routes(domain):
        ui.info(f"https://{host}")


def _ask_device(taken: set[str]) -> dict | None:
    def name(value: str) -> str:
        result = validate.name(value)
        if result in taken:
            raise ValueError(f"o nome {result} já está em uso")
        return result

    ui.note(
        "Informe o nome do endereço (vira <nome>.<domínio>), o IP do aparelho na rede de casa e a porta do painel. "
        "Se o painel do aparelho abre com https (comum em roteadores), escolha HTTPS."
    )
    chosen = ui.ask("nome do endereço (ex.: roteador)", validate=name)
    ip = ui.ask("IP do aparelho", validate=validate.ipv4)
    port = ui.ask("porta do painel", default="80", validate=validate.port)
    secure = ui.menu("Como o painel do aparelho abre?", ["HTTP (o mais comum)", "HTTPS (o aparelho tem certificado próprio)"])
    return {"name": chosen, "ip": ip, "port": int(port), "https": secure == 1}


def manage_devices(apply: bool = True) -> None:
    domain = config.saved_domain()
    while True:
        items = devices()
        if items:
            ui.table(
                [[f"https://{item['name']}.{domain}", _device_target(item).replace("https+insecure", "https")] for item in items],
                ["Endereço", "Aparelho"],
            )
        choice = ui.menu("Endereços de aparelhos da rede", ["Adicionar", "Remover", "Voltar"])
        if choice == 0:
            taken = {"adguard"} | {item["name"] for item in items} | {
                host.removesuffix(f".{domain}") for host, _, _ in app_routes()
            }
            items.append(_ask_device(taken))
            _save_devices(items)
            ui.ok(f"endereço https://{items[-1]['name']}.{domain} criado")
        elif choice == 1:
            if not items:
                ui.info("nenhum endereço de aparelho cadastrado")
                continue
            chosen = ui.checklist("Quais remover?", [item["name"] for item in items], cancel=True) or []
            _save_devices([item for index, item in enumerate(items) if index not in chosen])
            for index in chosen:
                ui.ok(f"endereço {items[index]['name']}.{domain} removido")
        else:
            break
        if apply:
            reload()


def remove() -> None:
    ui.step("Caddy")
    run.sudo_prepare("fechar as portas 80 e 443 no firewall")
    container.remove(NAME, IMAGE)
    container.remove_image(BASE)
    container.remove_image(BUILDER)
    distro.firewall_close(PORTS)


def summary() -> None:
    domain = config.saved_domain()
    ui.section("Caddy")
    expires = certificate(domain) if domain else ""
    ui.table([
        ["Caddy", ui.good("no ar") if installed() else ui.bad("parado")],
        ["Cadeado", ui.good(f"*.{domain} válido até {expires}") if expires else ui.pending("ainda não emitido")],
        ["Token da Cloudflare", ui.good("guardado") if saved_token() else ui.pending("falta")],
    ])
    ui.section("Endereços")
    ui.table(
        [[f"https://{host}", target.replace("https+insecure", "https"), origin] for host, target, origin in routes(domain)],
        ["Endereço", "Destino", "Origem"],
    )


def port_rows() -> list[list[str | ui.Cell]]:
    def state(item: str) -> ui.Cell:
        return ui.good("liberada") if distro.firewall_allowed(item) else ui.pending("fechada")

    return [
        ["80/tcp", "HTTP (Caddy, só redireciona)", state("http"), "-"],
        ["443 (tcp/udp)", "HTTPS (Caddy)", state("https"), "-"],
    ]
