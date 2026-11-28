from __future__ import annotations

import json
import re
import secrets
import shutil
import string
import time
from datetime import datetime, timezone
from pathlib import Path

from kit import config, container, disks, routes, run, ui, validate

APP = "nextcloud"
NAME = "astroverso-nextcloud"
DB = f"{NAME}-db"
REDIS = f"{NAME}-redis"
CRON = f"{NAME}-cron"
IMAGE = "docker.io/library/nextcloud:35.0.3-apache"
DB_IMAGE = "docker.io/library/postgres:18.7-alpine"
REDIS_IMAGE = "docker.io/valkey/valkey:9.1.4-alpine"
WWW = 33
SITE = Path(__file__).with_name("apache.conf")
DEFAULT_FILES = Path.home() / "Nextcloud"
FOLDER = "nextcloud"
MARKERS = (".ncdata", ".ocdata")
DRIVES = "DRIVES"


def folder() -> Path:
    return config.state(APP)


def secrets_folder() -> Path:
    return folder() / "secrets"


def html() -> Path:
    return folder() / "html"


def db_folder() -> Path:
    return folder() / "db"


def site_file() -> Path:
    return folder() / "apache.conf"


def files() -> Path:
    return Path(config.load(APP).get("FILES") or DEFAULT_FILES)


def host() -> str:
    return config.load(APP).get("HOST") or f"nextcloud.{config.saved_domain()}"


def admin() -> str:
    return config.load(APP).get("ADMIN_USER") or "astroverso"


def drives() -> list[tuple[str, bool]]:
    found: list[tuple[str, bool]] = []
    for item in (config.load(APP).get(DRIVES) or "").split(","):
        name, _, mode = item.strip().partition(":")
        if name:
            found.append((name, mode == "ro"))
    return found


def save_drives(items: list[tuple[str, bool]]) -> None:
    config.save(APP, {DRIVES: ",".join(f"{name}:ro" if readonly else name for name, readonly in items)})


def drive(name: str) -> Path:
    return disks.ROOT / name


def installed() -> bool:
    return container.active(NAME)


def created() -> bool:
    return (html() / "config" / "config.php").exists()


def _environment() -> dict[str, str]:
    return {
        "POSTGRES_HOST": DB,
        "POSTGRES_DB": "nextcloud",
        "POSTGRES_USER": "nextcloud",
        "POSTGRES_PASSWORD_FILE": "/run/secrets/db_password",
        "NEXTCLOUD_ADMIN_USER": admin(),
        "NEXTCLOUD_ADMIN_PASSWORD_FILE": "/run/secrets/admin_password",
        "NEXTCLOUD_TRUSTED_DOMAINS": host(),
        "REDIS_HOST": REDIS,
        "PHP_MEMORY_LIMIT": "1G",
        "PHP_UPLOAD_LIMIT": "16G",
        "APACHE_DISABLE_REWRITE_IP": "1",
    }


def _volumes() -> list[container.Volume]:
    return [
        container.Volume(html(), "/var/www/html", "z"),
        container.Volume(files(), "/var/www/html/data", "z"),
        container.Volume(secrets_folder(), "/run/secrets", "ro,z"),
        container.Volume(site_file(), "/etc/apache2/sites-enabled/000-default.conf", "ro,z"),
        *(container.Volume(drive(name), f"/srv/{name}", "ro" if readonly else "rw") for name, readonly in drives() if drive(name).is_dir()),
    ]


def specs() -> list[container.Container]:
    return [
        container.Container(
            name=DB, image=DB_IMAGE, description="Astroverso nextcloud: banco de dados (PostgreSQL)",
            volumes=[container.Volume(db_folder(), "/var/lib/postgresql"),
                     container.Volume(secrets_folder() / "db_password", "/run/secrets/db_password", "ro,z")],
            environment={"POSTGRES_DB": "nextcloud", "POSTGRES_USER": "nextcloud", "POSTGRES_PASSWORD_FILE": "/run/secrets/db_password"},
            health="pg_isready -U nextcloud -d nextcloud",
        ),
        container.Container(
            name=REDIS, image=REDIS_IMAGE, description="Astroverso nextcloud: cache e travas (Valkey)",
            command=["valkey-server", "--save", "", "--appendonly", "no"], health="valkey-cli ping",
        ),
        container.Container(
            name=NAME, image=IMAGE, description="Astroverso nextcloud: Nextcloud",
            volumes=_volumes(), environment=_environment(), requires=[DB, REDIS],
            health="curl -fsS -o /dev/null http://localhost/status.php", health_start="15m",
        ),
        container.Container(
            name=CRON, image=IMAGE, description="Astroverso nextcloud: tarefas em segundo plano",
            volumes=_volumes(), environment=_environment(), requires=[NAME], entrypoint="/cron.sh", stop_signal="SIGTERM",
        ),
    ]


def occ(*args: str) -> str:
    return container.exec(NAME, ["php", "occ", *args], user="www-data")


def occ_output(*args: str, env: dict[str, str] | None = None) -> tuple[int, str]:
    return container.exec_output(NAME, ["php", "occ", *args], user="www-data", env=env)


def status() -> dict:
    code, output = occ_output("status", "--output=json")
    try:
        return json.loads(output[output.index("{"):]) if code == 0 else {}
    except ValueError:
        return {}


def _secret_file(name: str) -> None:
    path = secrets_folder() / name
    if path.exists():
        return
    path.write_text(secrets.token_urlsafe(32))
    path.chmod(0o644)


def prepare_secrets() -> None:
    for path in (db_folder(), html()):
        path.mkdir(exist_ok=True)
    secrets_folder().mkdir(mode=0o700, exist_ok=True)
    _secret_file("db_password")
    _secret_file("admin_password")


def prepare_files(path: Path) -> None:
    if not path.exists():
        path.mkdir(parents=True, mode=0o770)
        ui.ok(f"pasta dos arquivos criada: {path}")
    if run.capture(["podman", "unshare", "stat", "-c", "%u", str(path)]) != str(WWW):
        run.cmd(["podman", "unshare", "chown", f"{WWW}:{WWW}", str(path)])
        run.cmd(["podman", "unshare", "chmod", "770", str(path)])
        ui.ok(f"pasta dos arquivos liberada para o Nextcloud: {path}")


def user_exists(user: str) -> bool:
    return occ_output("user:info", user)[0] == 0


def bring(source: Path, user: str, name: str) -> Path:
    base = files() / user / "files"
    target = base / name
    run.cmd(["podman", "unshare", "mkdir", "-p", str(base)])
    run.cmd(["podman", "unshare", "mv", "--", str(source), str(target)])
    ui.info("passando os arquivos para o Nextcloud (dono e permissões)...")
    run.cmd(["podman", "unshare", "chown", f"{WWW}:{WWW}", str(files() / user), str(base)])
    run.cmd(["podman", "unshare", "chown", "-R", f"{WWW}:{WWW}", str(target)])
    ui.info("catalogando os arquivos no Nextcloud (pode demorar com muitos arquivos)...")
    run.cmd(["podman", "exec", "-u", "www-data", NAME, "php", "occ", "files:scan", f"--path=/{user}/files/{name}"])
    return target


def render_site(address: str) -> None:
    text = string.Template(SITE.read_text()).substitute(HOST=address)
    if not site_file().exists() or site_file().read_text() != text:
        site_file().write_text(text)


def wait_ready(timeout: float = 1200) -> None:
    ui.info("esperando o Nextcloud terminar de instalar (alguns minutos na primeira vez)...")
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        state = status()
        if state.get("installed") and not state.get("maintenance"):
            ui.ok(f"Nextcloud {state.get('versionstring', '')} pronto".replace("  ", " "))
            return
        time.sleep(5)
    ui.fail("o Nextcloud não terminou de instalar (veja journalctl --user -u astroverso-nextcloud)")


def set_password(user: str, password: str) -> str:
    code, output = occ_output("user:resetpassword", "--password-from-env", user, env={"OC_PASS": password})
    if code == 0:
        return ""
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    return lines[-1] if lines else "o Nextcloud recusou a senha"


def change_password(user: str, password: str) -> None:
    while problem := set_password(user, password):
        ui.warn(f"o Nextcloud recusou a senha: {problem}")
        password = ui.secret(f"senha do administrador {user}")
    ui.ok(f"senha de {user} definida")


def _subnet() -> str:
    output = run.capture(["podman", "network", "inspect", container.NETWORK, "--format", "{{range .Subnets}}{{.Subnet}} {{end}}"])
    return output.split()[0] if output.split() else "10.89.0.0/24"


def _window() -> int:
    offset = datetime.now().astimezone().utcoffset()
    hours = int(offset.total_seconds() // 3600) if offset else 0
    return (3 - hours) % 24


def tune(address: str, first: bool) -> None:
    settings = [
        ("trusted_domains", "1", "--value", address),
        ("trusted_proxies", "0", "--value", _subnet()),
        ("overwriteprotocol", "--value", "https"),
        ("overwrite.cli.url", "--value", f"https://{address}"),
        ("default_timezone", "--value", config.timezone()),
        ("maintenance_window_start", "--type=integer", "--value", str(_window())),
        ("skeletondirectory", "--value", ""),
    ]
    region = config.region()
    if region:
        settings.append(("default_phone_region", "--value", region))
    for setting in settings:
        occ("config:system:set", *setting)
    occ("background:cron")
    ui.ok(f"Nextcloud ajustado para https://{address} (fuso {config.timezone()}, tarefas pelo cron)")
    if first:
        ui.info("conferindo o banco e reparando o que faltar...")
        occ("db:add-missing-indices")
        occ("maintenance:repair", "--include-expensive")
        ui.ok("banco conferido")


def start() -> None:
    for spec in specs():
        container.start(spec, timeout=1500 if spec.name == NAME else 180)


def publish(address: str) -> None:
    routes.publish(APP, [routes.Route(address, f"http://{NAME}:80")])


def remove_containers(images: bool = True) -> None:
    for spec in reversed(specs()):
        container.remove(spec.name)
    for image in dict.fromkeys(spec.image for spec in specs()) if images else ():
        container.remove_image(image)


def has_data(path: Path) -> bool:
    return any(run.succeeds(["podman", "unshare", "test", "-e", str(path / marker)]) for marker in MARKERS)


def empty(path: Path) -> bool:
    return run.capture(["podman", "unshare", "find", str(path), "-mindepth", "1", "-maxdepth", "1", "-print", "-quit"]) == ""


def remove_files(path: Path) -> None:
    if not path.is_dir() or not has_data(path) or path.resolve() in (Path.home().resolve(), Path("/")):
        ui.warn(f"{path} não parece uma pasta de arquivos do Nextcloud: ficou como está")
        return
    run.cmd(["podman", "unshare", "rm", "-rf", "--", str(path)])
    ui.ok(f"pasta dos arquivos apagada: {path}")


def free_space(path: Path) -> str:
    try:
        usage = shutil.disk_usage(path)
    except OSError:
        return "-"
    return f"{usage.free / 1024 ** 3:.0f} GB livres de {usage.total / 1024 ** 3:.0f} GB"


def last_cron() -> str:
    code, output = occ_output("config:app:get", "core", "lastcron")
    if code or not output.strip().isdigit():
        return ""
    moment = datetime.fromtimestamp(int(output.strip()), timezone.utc).astimezone()
    return moment.strftime("%d/%m %H:%M")


def checks() -> dict[str, str]:
    code, output = occ_output("setupchecks", "--output=json")
    if code not in (0, 1, 2) or "{" not in output:
        return {}
    try:
        data = json.loads(output[output.index("{"):])
    except ValueError:
        return {}
    found: dict[str, str] = {}
    for category in data.values() if isinstance(data, dict) else []:
        for check, result in (category or {}).items():
            if isinstance(result, dict) and result.get("severity") == "error":
                found[check] = re.sub(r"\s+", " ", str(result.get("description") or result.get("name") or check)).strip()[:300]
    return found


def validate_host(value: str) -> str:
    return validate.domain(value)


def validate_folder(value: str) -> str:
    path = Path(value.strip()).expanduser()
    if not path.is_absolute():
        raise ValueError("use um caminho completo, como ~/Nextcloud")
    if path.resolve() in (Path.home().resolve(), Path("/")) or str(path.resolve()).startswith(str(config.home().resolve())):
        raise ValueError("escolha uma pasta só para os arquivos do Nextcloud")
    if path.exists() and not empty(path) and not has_data(path):
        raise ValueError("essa pasta já tem arquivos: escolha uma vazia (ou a de um Nextcloud anterior)")
    return str(path)
