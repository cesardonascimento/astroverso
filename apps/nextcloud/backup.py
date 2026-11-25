from __future__ import annotations

import re
import shutil
from pathlib import Path

from kit import config, container, run, ui

from . import nextcloud

KEEP = ("config", "custom_apps", "themes", "version.php")


def save(folder: Path) -> None:
    if not nextcloud.installed():
        ui.fail("o Nextcloud precisa estar no ar para o backup (o banco é copiado com ele rodando)")
    dump = container.exec(nextcloud.DB, ["pg_dump", "-U", "nextcloud", "-d", "nextcloud"])
    (folder / "nextcloud.sql").write_text(dump + "\n")
    present = [name for name in KEEP if run.succeeds(["podman", "unshare", "test", "-e", str(nextcloud.html() / name)])]
    run.cmd(["podman", "unshare", "tar", "-C", str(nextcloud.html()), "-cf", str(folder / "html.tar"), *present])
    shutil.copy2(config.env_file(nextcloud.APP), folder / ".env")
    shutil.copytree(nextcloud.secrets_folder(), folder / "secrets", dirs_exist_ok=True)
    ui.ok(f"backup do Nextcloud em {folder}: banco, {', '.join(present)}, respostas e senhas")


def _database_user(config_php: str) -> tuple[str, str]:
    user = re.search(r"'dbuser'\s*=>\s*'([^']+)'", config_php)
    password = re.search(r"'dbpassword'\s*=>\s*'([^']*)'", config_php)
    if not user or not password:
        ui.fail("o config.php do backup não tem o usuário do banco")
    return user.group(1), password.group(1)


def load(folder: Path) -> None:
    for name in (".env", "nextcloud.sql", "html.tar"):
        if not (folder / name).exists():
            ui.fail(f"backup incompleto do Nextcloud: falta {name}")
    nextcloud.remove_containers(images=False)
    config.state(nextcloud.APP)
    shutil.copy2(folder / ".env", config.env_file(nextcloud.APP))
    config.env_file(nextcloud.APP).chmod(0o600)
    nextcloud.secrets_folder().mkdir(mode=0o700, exist_ok=True)
    for item in (folder / "secrets").iterdir():
        shutil.copy2(item, nextcloud.secrets_folder() / item.name)
        (nextcloud.secrets_folder() / item.name).chmod(0o644)
    nextcloud.html().mkdir(exist_ok=True)
    run.cmd(["podman", "unshare", "tar", "-C", str(nextcloud.html()), "-xf", str(folder / "html.tar")])
    if nextcloud.db_folder().exists():
        run.cmd(["podman", "unshare", "rm", "-rf", "--", str(nextcloud.db_folder())])
    nextcloud.db_folder().mkdir()
    db, *_ = nextcloud.specs()
    container.start(db)
    user, password = _database_user(run.capture(["podman", "unshare", "cat", str(nextcloud.html() / "config" / "config.php")]))
    escaped = password.replace("'", "''")
    container.exec(nextcloud.DB, ["psql", "-q", "-U", "nextcloud", "-d", "nextcloud"],
                   input=f"CREATE ROLE \"{user}\" LOGIN PASSWORD '{escaped}' CREATEDB;\n")
    container.exec(nextcloud.DB, ["psql", "-q", "-v", "ON_ERROR_STOP=1", "-U", "nextcloud", "-d", "nextcloud"],
                   input=(folder / "nextcloud.sql").read_text())
    ui.ok("banco do Nextcloud restaurado")
