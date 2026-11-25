from __future__ import annotations

import os
import re
import shutil
import tempfile
from collections.abc import Mapping
from pathlib import Path

from kit import run, ui, validate

APP = re.compile(r"^[a-z][a-z0-9-]*$")
KEY = re.compile(r"^[A-Z][A-Z0-9_]*$")


def home() -> Path:
    return Path.home() / ".astroverso"


def _folder(app: str) -> Path:
    if not APP.match(app):
        ui.fail(f"nome de app inválido: {app!r}")
    return home() / app


def state(app: str) -> Path:
    folder = _folder(app)
    home().mkdir(mode=0o700, exist_ok=True)
    folder.mkdir(mode=0o700, exist_ok=True)
    return folder


def env_file(app: str) -> Path:
    return _folder(app) / ".env"


def read_env(path: Path) -> dict[str, str]:
    try:
        lines = path.read_text().splitlines()
    except FileNotFoundError:
        return {}
    values: dict[str, str] = {}
    for line in lines:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        key, sep, value = line.partition("=")
        if sep:
            values[key.strip()] = value
    return values


def write_env(path: Path, values: Mapping[str, str]) -> None:
    for key, value in values.items():
        if not KEY.match(key):
            ui.fail(f"chave inválida no {path.name}: {key!r}")
        if "\n" in value or "\r" in value:
            ui.fail(f"valor com quebra de linha em {key}")
    handle, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        os.fchmod(handle, 0o600)
        with os.fdopen(handle, "w") as file:
            file.write("".join(f"{key}={value}\n" for key, value in values.items()))
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def load(app: str) -> dict[str, str]:
    return read_env(env_file(app))


def save(app: str, values: Mapping[str, str | None]) -> None:
    state(app)
    merged = load(app)
    for key, value in values.items():
        if value is None:
            merged.pop(key, None)
        else:
            merged[key] = value
    write_env(env_file(app), merged)


def reuse(app: str) -> bool:
    if not env_file(app).exists():
        return False
    return ui.confirm("usar a configuração já salva?", default=True)


def saved_domain() -> str:
    return read_env(home() / "astroverso.env").get("DOMAIN", "")


def domain() -> str:
    path = home() / "astroverso.env"
    values = read_env(path)
    if values.get("DOMAIN"):
        return values["DOMAIN"]
    chosen = ui.ask("domínio dos endereços (ex.: casa.com)", validate=validate.domain)
    home().mkdir(mode=0o700, exist_ok=True)
    write_env(path, {**values, "DOMAIN": chosen})
    ui.ok(f"domínio {chosen} guardado para todos os apps")
    return chosen


def purge(app: str) -> None:
    folder = _folder(app)
    if folder.resolve().parent != home().resolve() or folder.is_symlink():
        ui.fail(f"recusado: {folder} não é uma pasta de app em {home()}")
    if not folder.exists():
        return
    try:
        shutil.rmtree(folder)
    except PermissionError:
        run.cmd(["podman", "unshare", "rm", "-rf", str(folder)])
    ui.ok(f"configuração apagada: {folder}")


def timezone() -> str:
    target = str(Path("/etc/localtime").resolve())
    return target.split("zoneinfo/", 1)[1] if "zoneinfo/" in target else "UTC"


def region(zone: str = "") -> str:
    zone = zone or timezone()
    try:
        lines = Path("/usr/share/zoneinfo/zone.tab").read_text().splitlines()
    except OSError:
        return ""
    for line in lines:
        parts = line.split("\t")
        if len(parts) >= 3 and not line.startswith("#") and parts[2] == zone:
            return parts[0]
    return ""
