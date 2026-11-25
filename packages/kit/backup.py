from __future__ import annotations

import json
import time
import zlib
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from kit import changes, config, discord, net, run, ui, units

COMMAND = Path(__file__).resolve().parents[2] / "astroverso"
TAG = "astroverso"
CHANNEL = "backup"
KEYS = ("BACKUP_URL", "BACKUP_USER", "BACKUP_PASSWORD", "BACKUP_REPO_PASSWORD")


def settings_file() -> Path:
    return config.home() / "backup.env"


def settings() -> dict[str, str]:
    return config.read_env(settings_file())


def configured() -> bool:
    values = settings()
    return all(values.get(key) for key in KEYS)


def save(url: str, user: str, password: str, repository: str) -> None:
    config.home().mkdir(mode=0o700, exist_ok=True)
    config.write_env(settings_file(), dict(zip(KEYS, (url.rstrip("/"), user, password, repository))))


def forget() -> None:
    if settings_file().exists():
        settings_file().unlink()
        ui.ok("esta máquina deixou de mandar backups")


def environment(values: dict[str, str] | None = None) -> dict[str, str]:
    values = values or settings()
    return {
        "RESTIC_REPOSITORY": f"rest:{values['BACKUP_URL']}/{values['BACKUP_USER']}/",
        "RESTIC_REST_USERNAME": values["BACKUP_USER"],
        "RESTIC_REST_PASSWORD": values["BACKUP_PASSWORD"],
        "RESTIC_PASSWORD": values["BACKUP_REPO_PASSWORD"],
    }


def restic(*args: str, values: dict[str, str] | None = None, timeout: float | None = None) -> tuple[int, str]:
    return run.output(["restic", *args], env=environment(values), timeout=timeout)


def tail(output: str) -> str:
    lines = [line.split("     ", 1)[-1].strip() for line in output.splitlines() if line.strip()]
    return lines[-1][:300] if lines else "sem mensagem"


def ensure_repository(values: dict[str, str]) -> str:
    code, output = restic("cat", "config", values=values, timeout=60)
    if code == 0:
        return ""
    if "401" in output or "Unauthorized" in output:
        return "o servidor recusou o usuário ou a senha de acesso"
    if "wrong password" in output:
        return "a senha do repositório não confere"
    if "403" in output or "Forbidden" in output:
        return "o servidor não deixa este usuário abrir esse repositório"
    if any(text in output for text in ("does not exist", "Is there a repository", "unable to open config file")):
        code, output = restic("init", values=values, timeout=120)
        if code == 0:
            ui.ok("repositório de backup desta máquina criado")
            return ""
    return tail(output)


def unit(app: str) -> str:
    return f"astroverso-{app}-backup"


def minute(app: str) -> int:
    return zlib.crc32(app.encode()) % 60


def units_text(app: str) -> dict[str, str]:
    name = unit(app)
    return {
        f"{name}.timer": "\n".join([
            "[Unit]",
            f"Description=Astroverso {app}: backup da configuração todo dia",
            "",
            "[Timer]",
            f"OnCalendar=*-*-* 01:{minute(app):02d}:00",
            "Persistent=true",
            "",
            "[Install]",
            "WantedBy=timers.target",
            "",
        ]),
        f"{name}.service": "\n".join([
            "[Unit]",
            f"Description=Astroverso {app}: backup da configuração",
            "After=network-online.target",
            "",
            "[Service]",
            "Type=oneshot",
            "Nice=19",
            "IOSchedulingClass=idle",
            f"ExecStart={COMMAND} {app} action backup-now",
            "",
        ]),
    }


def change(app: str) -> changes.Change:
    name = unit(app)
    return changes.Change(
        "backup", f"Fazer o backup da configuração do {app} todo dia (01:{minute(app):02d})",
        f"Um timer do usuário ({name}.timer) guarda a configuração do {app}, criptografada, no servidor de backup do "
        "Astroverso (app backup), e avisa no canal #backup do Discord. Se a máquina estava desligada no horário, o "
        "backup roda ao ligar. Sem o servidor configurado nesta máquina, ele só avisa e não faz nada.",
        lambda: units.active(f"{name}.timer"),
        lambda: units.install(units_text(app), [f"{name}.timer"]),
        lambda: units.remove([f"{name}.timer", f"{name}.service"]),
    )


def _stage(app: str) -> Path:
    return config.home() / ".backup-stage" / app


def _clean(folder: Path) -> None:
    if folder.exists():
        run.cmd(["podman", "unshare", "rm", "-rf", "--", str(folder)])


def run_backup(app: str, save_function: Callable[[Path], None], label: str = "", notify: bool = True) -> bool:
    if not configured():
        ui.info("esta máquina não está ligada a um servidor de backup (instale o app backup): nada a fazer")
        return False
    started = time.monotonic()
    folder = _stage(app)
    _clean(folder)
    folder.mkdir(parents=True, mode=0o700)
    host = net.hostname()
    try:
        save_function(folder)
    except SystemExit:
        problem = "o backup do app falhou (veja a mensagem acima)"
    except Exception as error:
        problem = f"falha inesperada: {error}"
    else:
        tags = ["--tag", TAG, "--tag", f"app:{app}", *(["--tag", label] if label else [])]
        code, output = restic("backup", str(folder), "--host", host, *tags)
        problem = "" if code == 0 else f"o restic não guardou: {tail(output)}"
    _clean(folder)
    seconds = int(time.monotonic() - started)
    if problem:
        ui.warn(f"backup do {app} falhou: {problem}")
        if notify:
            discord.notify(CHANNEL, "erro", f"Backup do {app} falhou em {host}", problem,
                           actions=(("Tentar de novo", f"{app}:backup-now"),))
        return False
    ui.ok(f"backup do {app} guardado em {seconds} s")
    if notify:
        discord.notify(CHANNEL, "info", f"Backup do {app} feito em {host}", f"Em {seconds} s.")
    return True


def versions(app: str) -> list[dict]:
    code, output = restic("snapshots", "--json", "--tag", f"app:{app}", "--host", net.hostname(), timeout=120)
    try:
        found = json.loads(output) if code == 0 else []
    except ValueError:
        found = []
    return sorted((item for item in found if isinstance(item, dict)), key=lambda item: item.get("time", ""), reverse=True)


def when(item: dict) -> str:
    try:
        return datetime.fromisoformat(str(item["time"])[:19]).strftime("%d/%m/%Y %H:%M")
    except (KeyError, ValueError):
        return "-"


def label(item: dict) -> str:
    extra = [tag for tag in item.get("tags") or [] if tag != TAG and not tag.startswith("app:")]
    return f" ({', '.join(extra)})" if extra else ""


def restore(app: str, save_function: Callable[[Path], None], restore_function: Callable[[Path], None]) -> None:
    if not configured():
        ui.fail("esta máquina não está ligada a um servidor de backup: instale o app backup")
    found = versions(app)[:30]
    if not found:
        ui.fail(f"ainda não há nenhuma versão do {app} desta máquina no servidor")
    index = ui.menu(f"De quando restaurar o {app}?", [when(item) + label(item) for item in found] + ["Voltar"])
    if index >= len(found):
        return
    chosen = found[index]
    ui.warn(f"restaurar troca a configuração atual do {app} pela de {when(chosen)}")
    if not ui.confirm("Restaurar?", default=False):
        return
    ui.info("guardando antes a situação atual (versão \"antes-da-restauracao\")...")
    run_backup(app, save_function, "antes-da-restauracao", notify=False)
    target = config.home() / ".backup-restore" / app
    _clean(target)
    target.mkdir(parents=True, mode=0o700)
    code, output = restic("restore", f"{chosen['id']}:{chosen['paths'][0]}", "--target", str(target))
    if code:
        _clean(target)
        ui.fail(f"o restic não trouxe a versão: {tail(output)}")
    try:
        restore_function(target)
    finally:
        _clean(target)
    ui.ok(f"{app} restaurado da versão de {when(chosen)}")


def summary(app: str) -> None:
    ui.section("Backup")
    if not configured():
        ui.table([["Servidor de backup", ui.pending("esta máquina não está ligada (app backup)")]])
        return
    found = versions(app)
    ui.table([
        ["Servidor", settings()["BACKUP_URL"]],
        ["Backup diário", ui.good(f"ligado (01:{minute(app):02d})") if units.active(f"{unit(app)}.timer") else ui.pending("desligado")],
        ["Último backup", ui.good(when(found[0])) if found else ui.pending("nenhum ainda")],
        ["Versões guardadas", str(len(found))],
    ])
