from __future__ import annotations

import json
import secrets
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

from kit import changes, config, container, discord, routes, run, ui, units, validate

APP = "backup"
NAME = "astroverso-backup"
IMAGE = "docker.io/rclone/rclone:1.76.0"
PORT = 8080
MAINTENANCE = "astroverso-backup-maintenance"
COMMAND = Path(__file__).resolve().parents[2] / "astroverso"
DEFAULT_REPOS = Path.home() / "Backups" / "astroverso"


def folder() -> Path:
    return config.state(APP)


def clients_folder() -> Path:
    return folder() / "clients"


def htpasswd() -> Path:
    return folder() / "htpasswd"


def maintenance_file() -> Path:
    return folder() / "maintenance.json"


def repos() -> Path:
    return Path(config.load(APP).get("REPOS") or DEFAULT_REPOS)


def address() -> str:
    return f"backup.{config.saved_domain()}"


def spec() -> container.Container:
    return container.Container(
        name=NAME,
        image=IMAGE,
        description="Astroverso backup: servidor dos repositórios (rclone serve restic)",
        volumes=[container.Volume(repos(), "/data"), container.Volume(htpasswd(), "/config/htpasswd", "ro,Z")],
        command=["serve", "restic", "/data", "--addr", f":{PORT}", "--append-only", "--private-repos", "--htpasswd", "/config/htpasswd"],
    )


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


def add(name: str) -> dict[str, str]:
    clients_folder().mkdir(mode=0o700, exist_ok=True)
    values = {"PASSWORD": secrets.token_urlsafe(24), "REPO_PASSWORD": secrets.token_urlsafe(32)}
    config.write_env(clients_folder() / f"{name}.env", values)
    _write_htpasswd()
    return values


def validate_repos(value: str) -> str:
    path = Path(value.strip()).expanduser()
    if not path.is_absolute():
        raise ValueError("use um caminho completo, como ~/Backups/astroverso")
    if path.resolve() in (Path.home().resolve(), Path("/")) or str(path.resolve()).startswith(str(config.home().resolve())):
        raise ValueError("escolha uma pasta só para os backups (fora do ~/.astroverso)")
    return str(path)


def _count(value: str) -> str:
    if not value.strip().isdigit() or not 1 <= int(value) <= 999:
        raise ValueError("um número de 1 a 999")
    return value.strip()


def ask(reuse: bool) -> None:
    current = config.load(APP)
    if reuse and current.get("REPOS"):
        return
    ui.note(
        "A pasta onde ficam os backups de todas as máquinas, um repositório por máquina, criptografado. Quando o app "
        "de discos existir, escolha aqui um disco de backup."
    )
    chosen = ui.ask("pasta dos backups", default=current.get("REPOS") or str(DEFAULT_REPOS), validate=validate_repos)
    ui.note("Quantas versões guardar de cada app: uma por dia nos últimos dias e uma por mês nos últimos meses.")
    daily = ui.ask("versões diárias", default=current.get("KEEP_DAILY") or "30", validate=_count)
    monthly = ui.ask("versões mensais", default=current.get("KEEP_MONTHLY") or "12", validate=_count)
    config.save(APP, {"REPOS": chosen, "KEEP_DAILY": daily, "KEEP_MONTHLY": monthly})


def start() -> None:
    repos().mkdir(parents=True, exist_ok=True, mode=0o700)
    if not htpasswd().exists():
        _write_htpasswd()
    container.prepare()
    container.start(spec())
    routes.publish(APP, [routes.Route(address(), f"http://{NAME}:{PORT}")])


def restart() -> None:
    if installed():
        container.restart(spec())


def _local(name: str, values: dict[str, str]) -> dict[str, str]:
    return {"RESTIC_REPOSITORY": str(repos() / name), "RESTIC_PASSWORD": values["REPO_PASSWORD"]}


def snapshots(name: str, values: dict[str, str]) -> list[dict]:
    if not (repos() / name / "config").exists():
        return []
    code, output = run.output(["restic", "snapshots", "--json", "--no-lock"], env=_local(name, values), timeout=120)
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
        for tag in item.get("tags") or []:
            if tag.startswith("app:") and (tag[4:] not in found or moment > found[tag[4:]]):
                found[tag[4:]] = moment
    return found


def maintain() -> bool:
    current = config.load(APP)
    keep = ["--keep-daily", current.get("KEEP_DAILY", "30"), "--keep-monthly", current.get("KEEP_MONTHLY", "12")]
    problems: dict[str, str] = {}
    for name, values in clients().items():
        if not (repos() / name / "config").exists():
            continue
        ui.info(f"manutenção do repositório de {name}...")
        code, output = run.output(["restic", "forget", "--prune", *keep], env=_local(name, values))
        if code == 0:
            code, output = run.output(["restic", "check"], env=_local(name, values))
        if code:
            lines = [line for line in output.splitlines() if line.strip()]
            problems[name] = lines[-1][:300] if lines else f"restic saiu com {code}"
            ui.warn(f"{name}: {problems[name]}")
        else:
            ui.ok(f"{name}: versões antigas apagadas e repositório conferido")
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
            "Nice=19",
            "IOSchedulingClass=idle",
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


def free_space() -> str:
    try:
        usage = shutil.disk_usage(repos())
    except OSError:
        return "-"
    return f"{usage.free / 1024 ** 3:.0f} GB livres de {usage.total / 1024 ** 3:.0f} GB"


def ago(moment: datetime) -> str:
    hours = (datetime.now(timezone.utc) - moment).total_seconds() / 3600
    return moment.astimezone().strftime("%d/%m %H:%M") + (f" (há {hours / 24:.0f} dias)" if hours > 48 else "")


def validate_new(value: str) -> str:
    value = validate.name(value)
    if value in clients():
        raise ValueError(f"a máquina {value} já está cadastrada")
    return value
