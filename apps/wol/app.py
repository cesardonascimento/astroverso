from __future__ import annotations

import ipaddress
import json
import re
import shutil
import socket
import time
from pathlib import Path

from kit import vault
from kit import changes, config, docs, net, run, ui, validate
from kit.app import Action

APP = "wol"
DESCRIPTION = "Wake-on-LAN: liga as máquinas da rede pelo gerenciador e pelo Discord"
ORDER = 110
DOCS = Path(__file__).with_name("docs")
MAC = re.compile(r"^([0-9a-f]{2}:){5}[0-9a-f]{2}$")
PORT = 9
INTERVAL = 4
WAIT = 180
PREFIX = "ligar-"


def registry_file() -> Path:
    return config.state(APP) / "machines.json"


def machines() -> list[dict[str, str]]:
    try:
        saved = json.loads(registry_file().read_text())
    except (OSError, ValueError):
        return []
    return [item for item in saved if isinstance(item, dict) and item.get("name") and item.get("mac")] if isinstance(saved, list) else []


def save_machines(items: list[dict[str, str]]) -> None:
    temporary = registry_file().with_suffix(".tmp")
    temporary.write_text(json.dumps(sorted(items, key=lambda item: item["name"]), ensure_ascii=False, indent=2) + "\n")
    temporary.chmod(0o600)
    temporary.replace(registry_file())


def mac(value: str) -> str:
    text = value.strip().lower().replace("-", ":")
    if re.fullmatch(r"[0-9a-f]{12}", text):
        text = ":".join(text[i:i + 2] for i in range(0, 12, 2))
    if not MAC.match(text):
        raise ValueError("MAC inválido: seis pares, como 60:cf:84:a0:38:04")
    return text


def online(ip: str) -> bool:
    return run.succeeds(["ping", "-c", "1", "-W", "1", ip], timeout=5)


def neighbor(ip: str) -> str:
    online(ip)
    found = re.search(r"lladdr ([0-9a-f:]{17})", run.output(["ip", "neigh", "show", ip], timeout=5)[1])
    return found.group(1) if found else ""


def targets() -> list[str]:
    found = ["255.255.255.255"]
    try:
        found.append(str(ipaddress.ip_network(net.lan_network(), strict=False).broadcast_address))
    except SystemExit:
        pass
    return found


def send(address: str) -> None:
    packet = b"\xff" * 6 + bytes.fromhex(address.replace(":", "")) * 16
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sender:
        sender.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        for target in targets():
            sender.sendto(packet, (target, PORT))


def wake(name: str) -> bool:
    item = next((machine for machine in machines() if machine["name"] == name), None)
    if item is None:
        ui.fail(f"máquina não cadastrada: {name}")
    if online(item["ip"]):
        ui.ok(f"{name} ({item['ip']}) já está ligada")
        return True
    ui.info(f"enviando o pacote mágico para {name} ({item['mac']}) e esperando a resposta em {item['ip']}...")
    started = time.monotonic()
    while time.monotonic() - started < WAIT:
        send(item["mac"])
        time.sleep(INTERVAL)
        if online(item["ip"]):
            ui.ok(f"{name} ligou em {int(time.monotonic() - started)} s")
            return True
    ui.error(f"{name} não respondeu em {WAIT // 60} min: confira o Wake-on-LAN na BIOS e na placa de rede e se ela está no cabo")
    return False


def _new_name(value: str) -> str:
    value = validate.name(value)
    if any(item["name"] == value for item in machines()):
        raise ValueError(f"já existe uma máquina {value}")
    return value


def add_machine() -> None:
    ui.note(f"O nome é o usado no Discord: /astro {APP}:{PREFIX}<nome>. Use o IP fixo da máquina (reserva no roteador), com ela ligada agora, para o MAC ser lido sozinho.")
    name = ui.ask("nome da máquina", validate=_new_name)
    ip = ui.ask("IP da máquina na rede local", validate=validate.ipv4)
    address = neighbor(ip)
    if address:
        ui.ok(f"MAC lido da rede: {address}")
    else:
        ui.info("a máquina não respondeu: digite o MAC da placa de rede (no Windows: ipconfig /all, \"Endereço Físico\")")
        address = ui.ask("MAC", validate=mac)
    save_machines(machines() + [{"name": name, "ip": ip, "mac": address}])
    ui.ok(f"{name} cadastrada: {ip} ({address})")
    ui.link("o que ligar na máquina para o Wake-on-LAN funcionar", docs.link(DOCS / "wake-on-lan.md"))


def manage_machines() -> None:
    while True:
        found = machines()
        if found:
            ui.table([[item["name"], item["ip"], item["mac"]] for item in found], ["Máquina", "IP", "MAC"])
        options = ["Adicionar uma máquina"] + (["Remover máquinas"] if found else []) + ["Pronto"]
        choice = options[ui.menu("Máquinas da rede", options)]
        if choice == "Pronto":
            return
        if choice.startswith("Adicionar"):
            add_machine()
            continue
        chosen = ui.checklist("Quais máquinas remover?", [item["name"] for item in found], cancel=True) or []
        if chosen:
            save_machines([item for i, item in enumerate(found) if i not in chosen])
            ui.ok("removidas: " + ", ".join(found[i]["name"] for i in chosen))


def wake_menu() -> None:
    found = machines()
    if not found:
        ui.fail("nenhuma máquina cadastrada: adicione em Máquinas da rede")
    index = ui.menu("Qual máquina ligar?", [item["name"] for item in found] + ["Voltar"], [item["ip"] for item in found])
    if index < len(found):
        wake(found[index]["name"])


def items() -> list[changes.Change]:
    return [vault.change(APP)]


def status() -> bool:
    return config.env_file(APP).exists()


def install(reuse: bool | None = None) -> None:
    again = config.reuse(APP) if reuse is None else reuse
    ui.step("Wake-on-LAN")
    ui.note(
        "Liga as máquinas da rede de casa pelo pacote mágico (Wake-on-LAN), pelo gerenciador ou pelo Discord, de qualquer "
        "lugar: quem manda o pacote é esta máquina, que está na rede. As máquinas precisam estar no cabo, com o "
        "Wake-on-LAN ligado na BIOS e na placa de rede."
    )
    config.save(APP, {})
    if not again and not machines() and ui.confirm("Cadastrar uma máquina agora?", default=True):
        manage_machines()
    changes.install(APP, items(), again)
    summary()


def remove() -> None:
    ui.step("Wake-on-LAN")
    changes.undo_all(items())
    config.purge(APP)


def backup(folder: Path) -> None:
    for source in (config.env_file(APP), registry_file()):
        if source.exists():
            shutil.copy2(source, folder / source.name)


def restore(folder: Path) -> None:
    if not (folder / ".env").exists():
        ui.fail(f"backup sem a configuração do {APP}")
    config.state(APP)
    for name, target in ((".env", config.env_file(APP)), ("machines.json", registry_file())):
        if (folder / name).exists():
            shutil.copy2(folder / name, target)
            target.chmod(0o600)
    install(reuse=True)


def summary() -> None:
    ui.step("Resumo das máquinas")
    found = machines()
    ui.table([[item["name"], item["ip"], item["mac"], ui.good("ligada") if online(item["ip"]) else ui.off("desligada"),
               f"/astro {APP}:{PREFIX}{item['name']}"] for item in found] or [[ui.off("nenhuma"), "-", "-", "-", "-"]],
             ["Máquina", "IP", "MAC", "Agora", "No Discord"])
    ui.section("Mudanças no sistema")
    ui.table(changes.rows(items()), ["Mudança", "Situação"])


def manage() -> None:
    changes.manage(APP, items())


def actions() -> list[Action]:
    return [
        Action("summary", "Resumo das máquinas", summary, remote=True),
        Action("wake", "Ligar uma máquina", wake_menu),
        Action("machines", "Máquinas da rede", manage_machines),
        Action("changes", "Mudanças no sistema", manage),
        Action("backup-now", "Fazer backup agora", lambda: vault.run_backup(APP, backup), remote=True),
        Action("restore-version", "Restaurar uma fotografia", lambda: vault.restore(APP, backup, restore)),
        *[Action(f"{PREFIX}{item['name']}", f"Ligar {item['name']}", lambda name=item["name"]: _remote(name), remote=True, menu=False)
          for item in machines()],
    ]


def _remote(name: str) -> None:
    if not wake(name):
        raise SystemExit(1)
