from __future__ import annotations

import json
import re
from pathlib import Path

from kit import config, container, ui, validate

from . import n8n

PATH = re.compile(r"^[A-Za-z0-9][A-Za-z0-9/_-]*$")
TIMEOUT = 600
CALL = (
    "const chave = require('fs').readFileSync(0, 'utf8').trim();"
    "fetch('http://127.0.0.1:5678/webhook/' + process.argv[1], { method: 'POST', headers: { 'Content-Type': 'application/json', "
    "'X-Astroverso-Chave': chave }, body: '{}', signal: AbortSignal.timeout(590000) })"
    ".then(async (r) => console.log(JSON.stringify({ status: r.status, corpo: await r.text() })))"
    ".catch((e) => console.log(JSON.stringify({ status: 0, corpo: String(e) })));"
)


def commands_file() -> Path:
    return config.state(n8n.APP) / "commands.json"


def commands() -> list[dict[str, str]]:
    try:
        saved = json.loads(commands_file().read_text())
    except (OSError, ValueError):
        return []
    return [item for item in saved if isinstance(item, dict) and item.get("name") and item.get("path")] if isinstance(saved, list) else []


def save(items: list[dict[str, str]]) -> None:
    temporary = commands_file().with_suffix(".tmp")
    temporary.write_text(json.dumps(sorted(items, key=lambda item: item["name"]), ensure_ascii=False, indent=2) + "\n")
    temporary.chmod(0o600)
    temporary.replace(commands_file())


def answer(status: int, body: str) -> tuple[bool, str]:
    if status == 0:
        return False, f"o n8n não respondeu: {body[:300]}"
    try:
        data = json.loads(body) if body.strip() else {}
    except ValueError:
        data = {}
    text = str(data.get("mensagem") or "") if isinstance(data, dict) else ""
    if status == 404:
        return False, "o n8n não achou o webhook: a rotina está desligada ou o caminho mudou"
    if status in (401, 403):
        return False, "o n8n recusou a chave: a rotina precisa da credencial \"Astroverso: chamadas do Astroverso\" no webhook"
    if status >= 400:
        return False, text or f"a rotina falhou (HTTP {status}): {body[:300]}"
    return True, text or "rotina chamada (ela não devolveu mensagem)"


def call(item: dict[str, str]) -> bool:
    if not n8n.installed():
        ui.fail("o n8n não está no ar")
    key = config.load(n8n.APP).get("HOOK_KEY", "")
    code, output = container.exec_output(n8n.NAME, ["node", "-e", CALL, item["path"]], user=n8n.USER, input=key, timeout=TIMEOUT)
    try:
        result = json.loads(output.strip().splitlines()[-1]) if code == 0 and output.strip() else {"status": 0, "corpo": output}
    except ValueError:
        result = {"status": 0, "corpo": output}
    ok, text = answer(int(result.get("status") or 0), str(result.get("corpo") or ""))
    (ui.ok if ok else ui.error)(text)
    return ok


def _path(value: str) -> str:
    value = value.strip().removeprefix("/").removeprefix("webhook/")
    if not PATH.match(value):
        raise ValueError("o caminho do webhook da rotina, como astroverso-contas-email (letras, números, - _ /)")
    return value


def add(reserved: set[str]) -> None:
    def name(value: str) -> str:
        value = validate.name(value)
        if value in reserved or any(item["name"] == value for item in commands()):
            raise ValueError(f"o nome {value} já está em uso")
        return value

    ui.note(
        "Um comando chama o webhook de uma rotina do n8n (método POST, autenticação Header Auth com a credencial "
        "\"Astroverso: chamadas do Astroverso\", resposta pelo último nó) e mostra o campo mensagem da resposta. No "
        "Discord, vira /astro n8n:<nome>."
    )
    item = {"name": ui.ask("nome do comando", validate=name), "path": ui.ask("caminho do webhook da rotina", validate=_path)}
    item["description"] = ui.ask("o que ele faz (aparece no Discord)", default=f"Rotina {item['path']}")
    save(commands() + [item])
    ui.ok(f"comando {item['name']} cadastrado: /astro n8n:{item['name']}")


def manage(reserved: set[str]) -> None:
    while True:
        found = commands()
        if found:
            ui.table([[item["name"], item["path"], item.get("description", "")] for item in found], ["Comando", "Webhook", "O que faz"])
        options = ["Adicionar um comando"] + (["Testar um comando", "Remover comandos"] if found else []) + ["Pronto"]
        choice = options[ui.menu("Comandos do Discord", options)]
        if choice == "Pronto":
            return
        if choice.startswith("Adicionar"):
            add(reserved)
        elif choice.startswith("Testar"):
            index = ui.menu("Qual comando?", [item["name"] for item in found] + ["Voltar"])
            if index < len(found):
                call(found[index])
        else:
            chosen = ui.checklist("Quais comandos remover?", [item["name"] for item in found], cancel=True) or []
            if chosen:
                save([item for i, item in enumerate(found) if i not in chosen])
                ui.ok("comandos removidos (as rotinas continuam no n8n)")
