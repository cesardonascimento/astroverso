from __future__ import annotations

import json
from pathlib import Path

from kit import changes, container, mailboxes, ui, units

from . import nextcloud

PREFIX = "Astroverso "
UNIT = "astroverso-nextcloud-mailboxes"
COMMAND = Path(__file__).resolve().parents[2] / "astroverso"
SECRET = "ASTROVERSO_SECRET"


def name(box: mailboxes.Mailbox) -> str:
    return PREFIX + box.name.replace("-", " ").title()


def _literal(text: str) -> str:
    return "'" + text.replace("\\", "\\\\").replace("'", "\\'") + "'"


def _php(args: list[str]) -> str:
    return "\n".join([
        "<?php",
        f"$args = json_decode({_literal(json.dumps(['occ', *args]))}, true);",
        f'$_SERVER["argv"] = array_map(fn($a) => $a === "@secret" ? getenv("{SECRET}") : $a, $args);',
        '$argv = $_SERVER["argv"];',
        "$argc = count($argv);",
        'chdir("/var/www/html");',
        'require "/var/www/html/console.php";',
        "",
    ])


def _occ_secret(secret: str, *args: str) -> tuple[int, str]:
    return container.exec_output(nextcloud.NAME, ["php"], user="www-data", env={SECRET: secret}, input=_php(list(args)))


def existing(user: str) -> list[dict]:
    code, output = nextcloud.occ_output("mail:account:export", user, "--output=json")
    if code or "[" not in output:
        return []
    try:
        found = json.loads(output[output.index("["):])
    except ValueError:
        return []
    return [item for item in found if isinstance(item, dict)]


def _ensure_app() -> bool:
    code, output = nextcloud.occ_output("app:list", "--output=json")
    try:
        listed = json.loads(output[output.index("{"):]) if code == 0 else {}
    except ValueError:
        listed = {}
    if "mail" in (listed.get("enabled") or {}):
        return True
    if "mail" not in (listed.get("disabled") or {}):
        ui.info("instalando o app Mail no Nextcloud...")
        code, output = nextcloud.occ_output("app:install", "mail")
        if code and "already installed" not in output:
            ui.warn(f"não foi possível instalar o app Mail: {output.strip().splitlines()[-1] if output.strip() else code}")
            return False
    nextcloud.occ_output("app:enable", "mail")
    ui.ok("app Mail ligado no Nextcloud")
    return True


def sync() -> None:
    boxes = mailboxes.load()
    if not nextcloud.installed():
        ui.info("Nextcloud parado: as contas de e-mail ficam para quando ele voltar")
        return
    user = nextcloud.admin()
    if boxes and not _ensure_app():
        return
    current = existing(user)
    published = {box.address.lower() for box in boxes}
    for box in boxes:
        match = next((item for item in current if str(item.get("email", "")).lower() == box.address.lower()), None)
        smtp = str(box.smtp_port or box.port)
        if match:
            code, output = nextcloud.occ_output(
                "mail:account:update", str(match["id"]), "--name", name(box), "--imap-host", box.host,
                "--imap-port", str(box.port), "--smtp-host", box.host, "--smtp-port", smtp)
            if code:
                ui.warn(f"não foi possível atualizar a conta {box.address} no Mail de {user}: {output.strip()[-200:]}")
            else:
                ui.ok(f"conta \"{name(box)}\" ({box.address}) conferida no Mail de {user}")
            continue
        code, output = _occ_secret(
            box.password(), "mail:account:create", user, name(box), box.address,
            box.host, str(box.port), "none", box.user, "@secret", box.host, smtp, "none", box.user, "@secret")
        if code:
            ui.warn(f"não foi possível criar a conta {box.address} no Mail de {user}: {output.strip()[-200:]}")
        else:
            ui.ok(f"conta \"{name(box)}\" ({box.address}) criada no Mail de {user}")
    for item in current:
        if str(item.get("name", "")).startswith(PREFIX) and str(item.get("email", "")).lower() not in published:
            code, output = nextcloud.occ_output("mail:account:delete", str(item["id"]))
            if code:
                ui.warn(f"a conta {item.get('email')} ficou no Mail de {user} (apague pelo Nextcloud): {output.strip()[-120:]}")
            else:
                ui.ok(f"conta {item.get('email')} retirada do Mail de {user} (a caixa não existe mais)")


def unit_text() -> dict[str, str]:
    return {
        f"{UNIT}.path": "\n".join([
            "[Unit]",
            "Description=Astroverso nextcloud: atualiza as contas do Nextcloud Mail quando uma caixa de e-mail muda",
            "",
            "[Path]",
            f"PathChanged={mailboxes.folder()}",
            "MakeDirectory=yes",
            "DirectoryMode=0700",
            "",
            "[Install]",
            "WantedBy=default.target",
            "",
        ]),
        f"{UNIT}.service": "\n".join([
            "[Unit]",
            "Description=Astroverso nextcloud: contas de e-mail do Nextcloud Mail",
            "",
            "[Service]",
            "Type=oneshot",
            f"ExecStart={COMMAND} nextcloud action mailboxes",
            "",
        ]),
    }


def change() -> changes.Change:
    return changes.Change(
        "mailboxes", "Criar sozinho no Nextcloud Mail as contas das caixas de e-mail do Astroverso",
        f"Quando um app (como o mail) publica uma caixa de e-mail em ~/.astroverso/mailboxes, uma unidade do usuário "
        f"({UNIT}.path) cria ou atualiza a conta dela no Nextcloud Mail do administrador; quando a caixa sai, a conta "
        "sai também. Sem ela, use a ação Atualizar as contas de e-mail.",
        lambda: units.active(f"{UNIT}.path"),
        lambda: units.install(unit_text(), [f"{UNIT}.path"]),
        lambda: units.remove([f"{UNIT}.path", f"{UNIT}.service"]),
    )
