from __future__ import annotations

from pathlib import Path

from kit import config, docs, ui, validate

from . import rclone

NAME = "nextcloud"
LABEL = "Nextcloud"
OPTIONS: tuple[str, ...] = ()
DOCS = Path(__file__).with_name("docs")


def _url(value: str) -> str:
    value = value.strip().rstrip("/")
    if not value.startswith("https://") or " " in value:
        raise ValueError("endereço com https://, como https://nextcloud.casa.com")
    return value


def login(section: str, user: str = "") -> str:
    ui.note(
        "A conta do Nextcloud, pelo WebDAV, com uma senha de app só para o app cloud (não a sua senha de login). Assim, "
        "tudo o que vem da nuvem passa pelo Nextcloud: ele fica sempre em dia, com lixeira e versões."
    )
    ui.link("criar a senha de app no Nextcloud", docs.link(DOCS / "nextcloud.md"))
    domain = config.saved_domain()
    url = ui.ask("endereço do Nextcloud", default=f"https://nextcloud.{domain}" if domain else None, validate=_url)
    user = ui.ask("usuário do Nextcloud", default=user or None, validate=validate.name)
    for _ in range(3):
        password = ui.secret("senha de app do Nextcloud", confirm=False)
        rclone.set_section(section, {"type": "webdav", "url": f"{url}/remote.php/dav/files/{user}", "vendor": "nextcloud",
                                     "user": user, "pass": rclone.obscure(password)})
        code, output = rclone.call(["lsjson", "--max-depth", "1", f"{section}:"], timeout=180)
        if code == 0:
            ui.ok(f"conectado ao Nextcloud como {user}")
            return user
        ui.warn(f"o Nextcloud recusou: {rclone.tail(output, 2)}")
    rclone.drop_section(section)
    ui.fail("o login no Nextcloud não deu certo: confira o usuário e a senha de app e tente de novo em Contas na nuvem")
