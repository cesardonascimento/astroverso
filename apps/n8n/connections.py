from __future__ import annotations

import json
import re
from dataclasses import dataclass

from kit import config, discord, mail, mailboxes, ui

from . import n8n


@dataclass(frozen=True)
class Connection:
    id: str
    name: str
    type: str
    data: dict
    detail: str = ""


def _camel(text: str) -> str:
    return "".join(part.capitalize() for part in re.split(r"[^A-Za-z0-9]+", text) if part)


def build() -> tuple[list[Connection], list[str]]:
    found: list[Connection] = []
    missing: list[str] = []
    values = mail.settings()
    if mail.configured():
        found.append(Connection("astroversoEnvioEmail", "Astroverso: envio de e-mail", "httpHeaderAuth",
                                {"name": "X-Astroverso-Chave", "value": values["MAIL_KEY"]}, f"POST {values['MAIL_URL']}/enviar"))
    else:
        missing.append("envio de e-mail (app mail)")
    boxes = mailboxes.load()
    for box in boxes:
        try:
            password = box.password()
        except OSError:
            ui.warn(f"caixa {box.address}: a senha publicada não abriu, ficou de fora")
            continue
        found.append(Connection(f"astroversoImap{_camel(box.name)}", f"Astroverso: caixa {box.name} (IMAP)", "imap",
                                {"user": box.user, "password": password, "host": box.host, "port": box.port, "secure": False,
                                 "allowUnauthorizedCerts": False}, f"{box.address} ({box.host}:{box.port})"))
    if not boxes:
        missing.append("caixas de entrada (app mail)")
    values = discord.settings()
    if discord.configured():
        found.append(Connection("astroversoDiscord", "Astroverso: Discord", "httpHeaderAuth",
                                {"name": "Authorization", "value": f"Bearer {values['DISCORD_KEY']}"}, f"POST {values['DISCORD_URL']}/v1/mensagens"))
    else:
        missing.append("Discord (app discord)")
    key = config.load(n8n.APP).get("HOOK_KEY", "")
    if key:
        found.append(Connection("astroversoChamadas", "Astroverso: chamadas do Astroverso", "httpHeaderAuth",
                                {"name": "X-Astroverso-Chave", "value": key}, "webhooks chamados pelo Astroverso"))
    return found, missing


def sync() -> bool:
    found, missing = build()
    if missing:
        ui.info(f"conexões ainda não disponíveis nesta máquina: {', '.join(missing)}")
    if not found:
        return True
    payload = json.dumps([{"id": item.id, "name": item.name, "type": item.type, "data": item.data} for item in found])
    code, output = n8n.import_file("credentials", payload)
    if code:
        ui.warn(f"o n8n não gravou as conexões: {output.strip()[-300:]}")
        return False
    ui.ok(f"conexões do Astroverso no n8n: {', '.join(item.name.removeprefix('Astroverso: ') for item in found)}")
    return True
