from __future__ import annotations

from pathlib import Path

from kit import docs, ui, validate

from . import rclone

NAME = "proton"
LABEL = "Proton Drive"
OPTIONS = ("--transfers", "2", "--checkers", "4")
DOCS = Path(__file__).with_name("docs")


def login(section: str, user: str = "") -> str:
    ui.note("A conta do Proton Drive. A senha fica só nesta máquina, ofuscada no rclone.conf do app (600).")
    ui.link("conta com duas senhas, verificação em duas etapas e primeiro login", docs.link(DOCS / "proton.md"))
    user = ui.ask("e-mail da conta Proton", default=user or None, validate=validate.email)
    for _ in range(3):
        password = ui.secret("senha da conta Proton", confirm=False)
        values = {"type": "protondrive", "username": user, "password": rclone.obscure(password), "replace_existing_draft": "true"}
        if ui.confirm("A conta usa duas senhas (uma para entrar e outra para a caixa de e-mail)?", default=False):
            values["mailbox_password"] = rclone.obscure(ui.secret("senha da caixa de e-mail", confirm=False))
        env = {}
        if ui.confirm("A conta usa verificação em duas etapas?", default=True):
            env["RCLONE_PROTONDRIVE_2FA"] = ui.ask("código de 6 dígitos do aplicativo autenticador", validate=_code)
        rclone.set_section(section, values)
        code, output = rclone.call(["lsjson", "--max-depth", "1", f"{section}:"], env=env, timeout=180)
        if code == 0:
            ui.ok(f"conectado ao Proton Drive como {user}")
            return user
        ui.warn(f"o Proton recusou o login: {rclone.tail(output, 2)}")
    rclone.drop_section(section)
    ui.fail("o login no Proton não deu certo: confira a senha e o código e tente de novo em Contas na nuvem")


def _code(value: str) -> str:
    value = value.strip().replace(" ", "")
    if not (value.isdigit() and len(value) == 6):
        raise ValueError("o código tem 6 dígitos")
    return value
