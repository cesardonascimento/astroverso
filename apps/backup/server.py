from __future__ import annotations

import json
import secrets
import shutil
import time
import zlib
from datetime import datetime, timezone
from pathlib import Path

from kit import backup as kit_backup
from kit import changes, clouds, config, container, discord, disks, folders, routes, run, ui, units, validate

APP = "backup"
NAME = "astroverso-backup"
IMAGE = "docker.io/rclone/rclone:1.76.0"
PORT = 8080
MAINTENANCE = "astroverso-backup-maintenance"
COMMAND = Path(__file__).resolve().parents[2] / "astroverso"


def folder() -> Path:
    return config.state(APP)


def clients_folder() -> Path:
    return folder() / "clients"


def htpasswd() -> Path:
    return folder() / "htpasswd"


def maintenance_file() -> Path:
    return folder() / "maintenance.json"


def destinations_file() -> Path:
    return folder() / "destinations.json"


def destinations() -> list[kit_backup.Destination]:
    try:
        items = json.loads(destinations_file().read_text())
    except (OSError, ValueError):
        return []
    return [kit_backup.Destination(str(item["id"]), str(item["path"]), clouds.mark(Path(str(item["path"]))))
            for item in items if isinstance(item, dict) and item.get("id") and item.get("path")] if isinstance(items, list) else []


def save_destinations(items: list[kit_backup.Destination]) -> None:
    temporary = destinations_file().with_suffix(".tmp")
    temporary.write_text(json.dumps([{"id": item.id, "path": item.path} for item in items], ensure_ascii=False, indent=2) + "\n")
    temporary.chmod(0o600)
    temporary.replace(destinations_file())


def new_id(path: str, taken: set[str]) -> str:
    salt = 0
    while True:
        value = f"{zlib.crc32(f'{path}#{salt}'.encode()):08x}"
        if value not in taken:
            return value
        salt += 1


def repository(destination: kit_backup.Destination, name: str) -> Path:
    return Path(destination.path) / name


def available() -> list[kit_backup.Destination]:
    return [item for item in destinations() if reachable(item)]


def reachable(destination: kit_backup.Destination) -> bool:
    path = Path(destination.path)
    return disks.available(path) and path.is_dir()


def address() -> str:
    return f"backup.{config.saved_domain()}"


def spec() -> container.Container:
    return container.Container(
        name=NAME,
        image=IMAGE,
        description="Astroverso backup: servidor dos repositórios (rclone serve restic)",
        volumes=[*_volumes(), container.Volume(htpasswd(), "/config/htpasswd", "ro,Z")],
        command=["serve", "restic", "/data", "--addr", f":{PORT}", "--append-only", "--private-repos", "--htpasswd", "/config/htpasswd"],
        read_only=True,
    )


def _volumes() -> list[container.Volume]:
    found = []
    for name in clients():
        for item in available():
            options = "rw" if disks.containing(Path(item.path)) else "Z"
            found.append(container.Volume(repository(item, name), f"/data/{name}/{item.id}", options))
    return found


def installed() -> bool:
    return container.active(NAME)


def clients() -> dict[str, dict[str, str]]:
    found: dict[str, dict[str, str]] = {}
    for path in sorted(clients_folder().glob("*.env")) if clients_folder().exists() else []:
        found[path.stem] = config.read_env(path)
    return found


def _write_htpasswd() -> None:
    lines = []
    for name, values in clients().items():
        digest = run.capture(["openssl", "passwd", "-apr1", "-stdin"], input=values["PASSWORD"])
        lines.append(f"{name}:{digest}\n")
    htpasswd().write_text("".join(lines))
    htpasswd().chmod(0o644)


def add(name: str, repo_password: str = "") -> dict[str, str]:
    clients_folder().mkdir(mode=0o700, exist_ok=True)
    values = {"PASSWORD": secrets.token_urlsafe(24), "REPO_PASSWORD": repo_password or secrets.token_urlsafe(32)}
    config.write_env(clients_folder() / f"{name}.env", values)
    _write_htpasswd()
    return values


def validate_destination(value: str) -> str:
    path = Path(value.strip()).expanduser()
    if not path.is_absolute():
        raise ValueError("use um caminho completo")
    resolved = path.resolve()
    if resolved in (Path.home().resolve(), Path("/")) or resolved == config.home().resolve() or config.home().resolve() in resolved.parents:
        raise ValueError("escolha uma pasta só para os backups (fora do ~/.astroverso)")
    if str(path) in [item.path for item in destinations()]:
        raise ValueError("essa pasta já é uma pasta de destino")
    return str(path)


def _count(value: str) -> str:
    if not value.strip().isdigit() or not 1 <= int(value) <= 999:
        raise ValueError("um número de 1 a 999")
    return value.strip()


def ask(reuse: bool) -> None:
    current = config.load(APP)
    if reuse and current.get("KEEP_DAILY") and destinations():
        return
    ui.note("Quantas versões guardar de cada app: uma por dia nos últimos dias e uma por mês nos últimos meses.")
    daily = ui.ask("versões diárias", default=current.get("KEEP_DAILY") or "30", validate=_count)
    monthly = ui.ask("versões mensais", default=current.get("KEEP_MONTHLY") or "12", validate=_count)
    config.save(APP, {"KEEP_DAILY": daily, "KEEP_MONTHLY": monthly})
    if not destinations():
        manage_destinations()


def _add_destination() -> None:
    ui.note(
        "Uma pasta de destino guarda os backups das máquinas, uma subpasta (repositório criptografado) por máquina. "
        "Cada app escolhe para quais pastas vai o backup dele. A marca ☁ só mostra que a pasta está ligada a uma nuvem."
    )
    path = folders.pick("pasta de destino", validate=validate_destination)
    items = destinations()
    items.append(kit_backup.Destination(new_id(path, {item.id for item in items}), path, clouds.mark(Path(path))))
    save_destinations(items)
    ui.ok(f"pasta de destino {path} cadastrada")


def _drop_destinations() -> None:
    items = destinations()
    chosen = ui.checklist("Quais pastas deixam de ser destino?", [item.path for item in items], cancel=True) or []
    if not chosen:
        return
    ui.warn("os backups que já estão nelas ficam onde estão; os apps que mandavam para elas param de mandar e avisam no #backup")
    if not ui.confirm("confirma?", default=False):
        return
    save_destinations([item for i, item in enumerate(items) if i not in chosen])
    for i in chosen:
        ui.ok(f"{items[i].path} não é mais destino (os backups ficaram na pasta)")


def manage_destinations() -> None:
    before = destinations()
    while True:
        items = destinations()
        if items:
            ui.table([[item.path, free_space(item), item.detail()] for item in items], ["Pasta de destino", "Espaço", "Nuvem"])
        options = ["Adicionar uma pasta"] + (["Tirar pastas"] if items else []) + ["Pronto"]
        choice = options[ui.menu("Pastas de destino", options)]
        if choice == "Adicionar uma pasta":
            _add_destination()
        elif choice == "Tirar pastas":
            _drop_destinations()
        elif items:
            break
        else:
            ui.warn("cadastre pelo menos uma pasta de destino")
    if destinations() != before:
        apply_destinations()


def apply_destinations() -> None:
    if installed():
        start()
    sync_local()
    if len(clients()) > 1:
        ui.info("nas outras máquinas, use a ação Atualizar as pastas de destino do app backup, com o código de Mostrar os dados de uma máquina")


def sync_local() -> None:
    if kit_backup.settings().get("BACKUP_URL") == f"https://{address()}":
        kit_backup.save_destinations(destinations())


def link_code(name: str) -> str:
    return kit_backup.link_code(f"https://{address()}", name, destinations())


def prepare_folders() -> None:
    for item in destinations():
        if disks.available(Path(item.path)):
            Path(item.path).mkdir(parents=True, exist_ok=True, mode=0o700)
        if not reachable(item):
            ui.warn(f"pasta de destino indisponível: {item.path} (disco desligado ou travado?)")
            continue
        for name in clients():
            repository(item, name).mkdir(exist_ok=True, mode=0o700)


def start() -> None:
    prepare_folders()
    if not htpasswd().exists():
        _write_htpasswd()
    routes.publish(APP, [routes.Route(address(), f"http://{NAME}:{PORT}")])
    if not available():
        ui.warn("nenhuma pasta de destino disponível (discos desligados?): o servidor de backup fica parado até uma voltar")
        return
    container.prepare()
    container.start(spec())


def heal() -> None:
    if not htpasswd().exists():
        return
    prepare_folders()
    if available():
        container.start(spec())
    elif installed():
        run.succeeds(["systemctl", "--user", "stop", container.unit(NAME)])
        ui.warn("nenhuma pasta de destino disponível: servidor de backup parado até uma voltar")


def restart() -> None:
    if installed():
        prepare_folders()
        container.start(spec())
        container.restart(spec())


def _local(path: Path, values: dict[str, str]) -> dict[str, str]:
    return {"RESTIC_REPOSITORY": str(path), "RESTIC_PASSWORD": values["REPO_PASSWORD"]}


def snapshots(path: Path, values: dict[str, str]) -> list[dict]:
    if not (path / "config").exists():
        return []
    code, output = run.output(["restic", "snapshots", "--json", "--no-lock"], env=_local(path, values), timeout=120)
    try:
        found = json.loads(output) if code == 0 else []
    except ValueError:
        return []
    return [item for item in found if isinstance(item, dict)]


def latest(items: list[dict]) -> dict[str, datetime]:
    found: dict[str, datetime] = {}
    for item in items:
        try:
            moment = datetime.fromisoformat(str(item["time"]).replace("Z", "+00:00"))
        except (KeyError, ValueError):
            continue
        tags = [str(tag) for tag in item.get("tags") or []]
        app = next((tag[4:] for tag in tags if tag.startswith("app:")), "")
        data = next((tag[6:] for tag in tags if tag.startswith("dados:")), "")
        key = f"{app} ({data})" if data else app
        if app and (key not in found or moment > found[key]):
            found[key] = moment
    return found


def maintain() -> bool:
    current = config.load(APP)
    keep = ["--keep-daily", current.get("KEEP_DAILY", "30"), "--keep-monthly", current.get("KEEP_MONTHLY", "12")]
    problems: dict[str, str] = {}
    for item in destinations():
        if not reachable(item):
            problems[item.path] = "pasta indisponível (disco desligado ou travado?)"
            ui.warn(f"{item.path}: {problems[item.path]}")
            continue
        for name, values in clients().items():
            path = repository(item, name)
            if not (path / "config").exists():
                continue
            ui.info(f"manutenção do repositório de {name} em {item.path}...")
            code, output = run.output(["restic", "forget", "--prune", *keep], env=_local(path, values))
            if code == 0:
                code, output = run.output(["restic", "check"], env=_local(path, values))
            where = f"{name} em {item.path}"
            if code:
                lines = [line for line in output.splitlines() if line.strip()]
                problems[where] = lines[-1][:300] if lines else f"restic saiu com {code}"
                ui.warn(f"{where}: {problems[where]}")
            else:
                ui.ok(f"{where}: versões antigas apagadas e repositório conferido")
    maintenance_file().write_text(json.dumps({"time": int(time.time()), "problems": problems}, ensure_ascii=False) + "\n")
    if problems:
        discord.notify(APP, "erro", "Manutenção dos backups com problema",
                       "\n".join(f"{name}: {problem}" for name, problem in problems.items()))
    return not problems


def _units() -> dict[str, str]:
    return {
        f"{MAINTENANCE}.timer": "\n".join([
            "[Unit]",
            "Description=Astroverso backup: manutenção semanal dos repositórios",
            "",
            "[Timer]",
            "OnCalendar=Sun *-*-* 04:00:00",
            "Persistent=true",
            "",
            "[Install]",
            "WantedBy=timers.target",
            "",
        ]),
        f"{MAINTENANCE}.service": "\n".join([
            "[Unit]",
            "Description=Astroverso backup: apaga as versões antigas e confere os repositórios",
            "",
            "[Service]",
            "Type=oneshot",
            f"ExecStart={COMMAND} backup action maintenance",
            "",
        ]),
    }


def change() -> changes.Change:
    return changes.Change(
        "maintenance", "Apagar as versões antigas e conferir os backups todo domingo",
        f"Um timer do usuário ({MAINTENANCE}.timer) apaga, nos repositórios de todas as máquinas, as versões além da "
        "regra (diárias e mensais) e confere a integridade de cada um. Só o servidor pode apagar: as máquinas só "
        "acrescentam versões.",
        lambda: units.active(f"{MAINTENANCE}.timer"),
        lambda: units.install(_units(), [f"{MAINTENANCE}.timer"]),
        lambda: units.remove([f"{MAINTENANCE}.timer", f"{MAINTENANCE}.service"]),
        danger=True,
    )


def free_space(destination: kit_backup.Destination) -> str:
    if not reachable(destination):
        return "indisponível"
    try:
        usage = shutil.disk_usage(destination.path)
    except OSError:
        return "-"
    return f"{folders.human(usage.free)} livres de {folders.human(usage.total)}"


def ago(moment: datetime) -> str:
    hours = (datetime.now(timezone.utc) - moment).total_seconds() / 3600
    return moment.astimezone().strftime("%d/%m %H:%M") + (f" (há {hours / 24:.0f} dias)" if hours > 48 else "")


def validate_new(value: str) -> str:
    value = validate.name(value)
    if value in clients():
        raise ValueError(f"a máquina {value} já está cadastrada (os dados dela estão em Mostrar os dados de uma máquina)")
    return value


def existing(name: str) -> list[Path]:
    return [repository(item, name) for item in destinations()
            if reachable(item) and (repository(item, name) / "config").exists()]


def check_password(name: str, password: str) -> str:
    for path in existing(name):
        code, _ = run.output(["restic", "cat", "config", "--no-lock"], env={"RESTIC_REPOSITORY": str(path), "RESTIC_PASSWORD": password}, timeout=60)
        if code:
            return f"essa senha não abre os backups de {name} em {path.parent}"
    return ""
