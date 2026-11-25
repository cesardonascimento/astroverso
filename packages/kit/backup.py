from __future__ import annotations

import base64
import json
import time
import zlib
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from kit import changes, config, discord, disks, net, run, ui, units

COMMAND = Path(__file__).resolve().parents[2] / "astroverso"
TAG = "astroverso"
CHANNEL = "backup"
KEYS = ("BACKUP_URL", "BACKUP_USER", "BACKUP_PASSWORD", "BACKUP_REPO_PASSWORD")
TARGETS = "BACKUP_TO"
CODE = "astroverso-backup:"


@dataclass(frozen=True)
class Destination:
    id: str
    path: str
    cloud: str = ""

    def detail(self) -> str:
        return f"☁ {self.cloud}" if self.cloud else ""


def settings_file() -> Path:
    return config.home() / "backup.env"


def destinations_file() -> Path:
    return config.home() / "backup-destinations.json"


def settings() -> dict[str, str]:
    return config.read_env(settings_file())


def configured() -> bool:
    values = settings()
    return all(values.get(key) for key in KEYS) and bool(destinations())


def save(url: str, user: str, password: str, repository: str) -> None:
    config.home().mkdir(mode=0o700, exist_ok=True)
    config.write_env(settings_file(), dict(zip(KEYS, (url.rstrip("/"), user, password, repository))))


def destinations() -> list[Destination]:
    try:
        items = json.loads(destinations_file().read_text())
    except (OSError, ValueError):
        return []
    return [Destination(str(item["id"]), str(item["path"]), str(item.get("cloud") or ""))
            for item in items if isinstance(item, dict) and item.get("id") and item.get("path")] if isinstance(items, list) else []


def _dump(items: Sequence[Destination]) -> list[dict[str, str]]:
    return [{"id": item.id, "path": item.path, **({"cloud": item.cloud} if item.cloud else {})} for item in items]


def save_destinations(items: Sequence[Destination]) -> None:
    config.home().mkdir(mode=0o700, exist_ok=True)
    temporary = config.home() / ".backup-destinations.json.tmp"
    temporary.write_text(json.dumps(_dump(items), ensure_ascii=False, indent=2) + "\n")
    temporary.chmod(0o600)
    temporary.replace(destinations_file())


def forget() -> None:
    found = False
    for path in (settings_file(), destinations_file()):
        if path.exists():
            path.unlink()
            found = True
    if found:
        ui.ok("esta máquina deixou de mandar backups")


def link_code(url: str, user: str, items: Sequence[Destination]) -> str:
    content = json.dumps({"url": url, "user": user, "destinations": _dump(items)}, ensure_ascii=False, separators=(",", ":"))
    return CODE + base64.urlsafe_b64encode(content.encode()).decode().rstrip("=")


def read_code(text: str) -> tuple[str, str, list[Destination]]:
    value = "".join(text.split())
    if not value.startswith(CODE):
        raise ValueError(f"o código começa com {CODE}")
    try:
        payload = value[len(CODE):]
        data = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        items = [Destination(str(item["id"]), str(item["path"]), str(item.get("cloud") or "")) for item in data["destinations"]]
        url, user = str(data["url"]), str(data["user"])
    except (ValueError, KeyError, TypeError, AttributeError):
        raise ValueError("código incompleto: copie de novo, inteiro") from None
    if not url or not user or not items:
        raise ValueError("código sem pastas de destino: cadastre uma no servidor")
    return url, user, items


def environment(destination: Destination, values: dict[str, str] | None = None) -> dict[str, str]:
    values = values or settings()
    return {
        "RESTIC_REPOSITORY": f"rest:{values['BACKUP_URL']}/{values['BACKUP_USER']}/{destination.id}/",
        "RESTIC_REST_USERNAME": values["BACKUP_USER"],
        "RESTIC_REST_PASSWORD": values["BACKUP_PASSWORD"],
        "RESTIC_PASSWORD": values["BACKUP_REPO_PASSWORD"],
    }


def restic(*args: str, destination: Destination, values: dict[str, str] | None = None, timeout: float | None = None,
           unshare: bool = False) -> tuple[int, str]:
    prefix = ["podman", "unshare"] if unshare else []
    return run.output([*prefix, "restic", *args], env=environment(destination, values), timeout=timeout)


def tail(output: str) -> str:
    lines = [line.split("     ", 1)[-1].strip() for line in output.splitlines() if line.strip()]
    return lines[-1][:300] if lines else "sem mensagem"


def ensure_repository(values: dict[str, str], destination: Destination) -> str:
    code, output = restic("cat", "config", destination=destination, values=values, timeout=60)
    if code == 0:
        return ""
    if "401" in output or "Unauthorized" in output:
        return "o servidor recusou o usuário ou a senha de acesso"
    if "wrong password" in output:
        return "a senha do repositório não confere"
    if "403" in output or "Forbidden" in output:
        return "o servidor não deixa este usuário abrir esse repositório"
    if any(text in output for text in ("does not exist", "Is there a repository", "unable to open config file")):
        code, output = restic("init", destination=destination, values=values, timeout=120)
        if code == 0:
            ui.ok(f"repositório desta máquina criado em {destination.path}")
            return ""
    return tail(output)


def targets(app: str, key: str = TARGETS) -> list[Destination]:
    wanted = [item for item in config.load(app).get(key, "").split(",") if item]
    known = {item.id: item for item in destinations()}
    return [known[item] for item in wanted if item in known]


def lost(app: str, key: str = TARGETS) -> list[str]:
    known = {item.id for item in destinations()}
    return [item for item in config.load(app).get(key, "").split(",") if item and item not in known]


def pick(question: str, current: Sequence[Destination] = ()) -> list[Destination] | None:
    items = destinations()
    ids = [item.id for item in current]
    chosen = ui.checklist(question, [item.path for item in items], details=[item.detail() for item in items],
                          selected=[i for i, item in enumerate(items) if item.id in ids] or [0], cancel=True)
    if not chosen:
        return None
    return [items[i] for i in chosen]


def choose(app: str, key: str, what: str) -> bool:
    if not configured():
        ui.warn("esta máquina não está ligada a um servidor de backup (app backup): ligue o backup depois, em Mudanças no sistema")
        return False
    if targets(app, key) and not lost(app, key):
        return True
    ui.note("As pastas de destino ficam na máquina do servidor de backup. Pode marcar mais de uma: o backup vai para todas.")
    chosen = pick(f"Para quais pastas vai o backup {what}?", targets(app, key))
    if not chosen:
        ui.warn("nenhuma pasta escolhida: o backup fica desligado")
        return False
    config.save(app, {key: ",".join(item.id for item in chosen)})
    return True


def unit(app: str, part: str = "") -> str:
    return f"astroverso-{app}-backup" + (f"-{part}" if part else "")


def minute(app: str) -> int:
    return zlib.crc32(app.encode()) % 60


def units_text(app: str, part: str = "", action: str = "backup-now", hour: int = 1, what: str = "da configuração") -> dict[str, str]:
    name = unit(app, part)
    return {
        f"{name}.timer": "\n".join([
            "[Unit]",
            f"Description=Astroverso {app}: backup {what} todo dia",
            "",
            "[Timer]",
            f"OnCalendar=*-*-* {hour:02d}:{minute(app):02d}:00",
            "Persistent=true",
            "",
            "[Install]",
            "WantedBy=timers.target",
            "",
        ]),
        f"{name}.service": "\n".join([
            "[Unit]",
            f"Description=Astroverso {app}: backup {what}",
            "After=network-online.target",
            "",
            "[Service]",
            "Type=oneshot",
            f"ExecStart={COMMAND} {app} action {action}",
            "",
        ]),
    }


def _enable(app: str, key: str | None, what: str, texts: dict[str, str]) -> None:
    if key is None or choose(app, key, what):
        units.install(texts, [name for name in texts if name.endswith(".timer")])


def _disable(app: str, key: str | None, texts: dict[str, str]) -> None:
    units.remove(list(texts))
    if key:
        config.save(app, {key: None})


def change(app: str) -> changes.Change:
    texts = units_text(app)
    return changes.Change(
        "backup", f"Fazer o backup da configuração do {app} todo dia (01:{minute(app):02d})",
        f"Um timer do usuário ({unit(app)}.timer) guarda a configuração do {app}, criptografada, nas pastas de destino "
        "que você escolher no servidor de backup do Astroverso (app backup), e avisa no canal #backup do Discord. Se a "
        "máquina estava desligada no horário, o backup roda ao ligar. Para trocar as pastas, desligue e ligue de novo.",
        lambda: units.active(f"{unit(app)}.timer"),
        lambda: _enable(app, TARGETS, f"da configuração do {app}", texts),
        lambda: _disable(app, TARGETS, texts),
    )


def data_change(app: str, part: str, label: str, why: str, action: str, key: str | None, what: str) -> changes.Change:
    texts = units_text(app, part, action, 2, what)
    return changes.Change(
        f"backup-{part}", f"{label} (02:{minute(app):02d})",
        f"{why} Um timer do usuário ({unit(app, part)}.timer) faz o backup todo dia, criptografado, no servidor de backup "
        "do Astroverso (app backup), com a mesma regra de versões das configurações, e avisa no canal #backup.",
        lambda: units.active(f"{unit(app, part)}.timer"),
        lambda: _enable(app, key, what, texts),
        lambda: _disable(app, key, texts),
    )


def _stage(app: str) -> Path:
    return config.home() / ".backup-stage" / app


def _clean(folder: Path) -> None:
    if folder.exists():
        run.cmd(["podman", "unshare", "rm", "-rf", "--", str(folder)])


def _report(app: str, what: str, problems: list[str], seconds: int, retry: str, notify: bool, done: Sequence[Destination]) -> bool:
    host = net.hostname()
    if problems:
        for problem in problems:
            ui.warn(f"backup {what} falhou: {problem}")
        if notify:
            discord.notify(CHANNEL, "erro", f"Backup {what} falhou em {host}", "\n".join(problems),
                           actions=(("Tentar de novo", f"{app}:{retry}"),))
        return False
    places = ", ".join(item.path for item in done)
    ui.ok(f"backup {what} guardado em {seconds} s ({places})")
    if notify:
        discord.notify(CHANNEL, "info", f"Backup {what} feito em {host}", f"Em {seconds} s, em {places}.")
    return True


def _lost_problems(missing: Sequence[str]) -> list[str]:
    return [f"a pasta de destino {item} não existe mais no servidor: escolha de novo" for item in missing]


def run_backup(app: str, save_function: Callable[[Path], None], label: str = "", notify: bool = True) -> bool:
    if not configured():
        ui.info("esta máquina não está ligada a um servidor de backup (instale o app backup): nada a fazer")
        return False
    what = f"do {app}"
    chosen = targets(app)
    problems = _lost_problems(lost(app))
    if not chosen:
        return _report(app, what, problems or ["nenhuma pasta de destino escolhida: ligue o backup em Mudanças no sistema"],
                       0, "backup-now", notify, [])
    started = time.monotonic()
    folder = _stage(app)
    _clean(folder)
    folder.mkdir(parents=True, mode=0o700)
    host = net.hostname()
    try:
        save_function(folder)
    except SystemExit:
        problems.append("o backup do app falhou (veja a mensagem acima)")
    except Exception as error:
        problems.append(f"falha inesperada: {error}")
    else:
        tags = ["--tag", TAG, "--tag", f"app:{app}", *(["--tag", label] if label else [])]
        for item in chosen:
            code, output = restic("backup", str(folder), "--host", host, *tags, destination=item)
            if code:
                problems.append(f"o restic não guardou em {item.path}: {tail(output)}")
    _clean(folder)
    return _report(app, what, problems, int(time.monotonic() - started), "backup-now", notify, chosen)


def run_data(app: str, name: str, path: Path, chosen: Sequence[Destination], retry: str, unshare: bool = False,
             missing: Sequence[str] = (), exclude: Sequence[str] = (), notify: bool = True) -> bool:
    if not configured():
        ui.info("esta máquina não está ligada a um servidor de backup (instale o app backup): nada a fazer")
        return False
    what = f"de {name} ({app})"
    problems = _lost_problems(missing)
    if not chosen:
        return _report(app, what, problems or ["nenhuma pasta de destino escolhida"], 0, retry, notify, [])
    if not path.is_dir() or not disks.available(path):
        return _report(app, what, [f"{path} indisponível (disco desligado, travado ou pasta apagada): nada foi guardado"],
                       0, retry, notify, [])
    started = time.monotonic()
    tags = ["--tag", TAG, "--tag", f"app:{app}", "--tag", f"dados:{name}", *[f"--exclude={rule}" for rule in exclude]]
    for item in chosen:
        ui.info(f"guardando {path} em {item.path}...")
        code, output = restic("backup", str(path), "--host", net.hostname(), *tags, destination=item, unshare=unshare)
        if code:
            problems.append(f"o restic não guardou em {item.path}: {tail(output)}")
    return _report(app, what, problems, int(time.monotonic() - started), retry, notify, chosen)


def versions(app: str, destination: Destination, data: str = "") -> list[dict]:
    code, output = restic("snapshots", "--json", "--tag", f"app:{app}", "--host", net.hostname(), destination=destination, timeout=120)
    try:
        found = json.loads(output) if code == 0 else []
    except ValueError:
        found = []
    wanted = f"dados:{data}" if data else ""
    chosen = [item for item in found if isinstance(item, dict) and (
        wanted in (item.get("tags") or []) if data else not any(str(tag).startswith("dados:") for tag in item.get("tags") or []))]
    return sorted(chosen, key=lambda item: item.get("time", ""), reverse=True)


def when(item: dict) -> str:
    try:
        return datetime.fromisoformat(str(item["time"])[:19]).strftime("%d/%m/%Y %H:%M")
    except (KeyError, ValueError):
        return "-"


def label(item: dict) -> str:
    extra = [tag for tag in item.get("tags") or [] if tag != TAG and not tag.startswith(("app:", "dados:"))]
    return f" ({', '.join(extra)})" if extra else ""


def _source(app: str, data: str = "") -> tuple[Destination, dict] | None:
    items = destinations()
    if len(items) > 1:
        index = ui.menu("De qual pasta de destino?", [item.path for item in items] + ["Voltar"], [item.detail() for item in items])
        if index >= len(items):
            return None
        place = items[index]
    else:
        place = items[0]
    found = versions(app, place, data)[:30]
    if not found:
        ui.fail(f"ainda não há nenhuma versão {f'de {data} ' if data else ''}do {app} desta máquina em {place.path}")
    index = ui.menu(f"De quando restaurar{f' {data}' if data else ''}?", [when(item) + label(item) for item in found] + ["Voltar"])
    return None if index >= len(found) else (place, found[index])


def restore(app: str, save_function: Callable[[Path], None], restore_function: Callable[[Path], None]) -> None:
    if not configured():
        ui.fail("esta máquina não está ligada a um servidor de backup: instale o app backup")
    picked = _source(app)
    if picked is None:
        return
    place, chosen = picked
    ui.warn(f"restaurar troca a configuração atual do {app} pela de {when(chosen)}")
    if not ui.confirm("Restaurar?", default=False):
        return
    if targets(app):
        ui.info("guardando antes a situação atual (versão \"antes-da-restauracao\")...")
        run_backup(app, save_function, "antes-da-restauracao", notify=False)
    target = config.home() / ".backup-restore" / app
    _clean(target)
    target.mkdir(parents=True, mode=0o700)
    code, output = restic("restore", f"{chosen['id']}:{chosen['paths'][0]}", "--target", str(target), destination=place)
    if code:
        _clean(target)
        ui.fail(f"o restic não trouxe a versão: {tail(output)}")
    try:
        restore_function(target)
    finally:
        _clean(target)
    ui.ok(f"{app} restaurado da versão de {when(chosen)}")


@contextmanager
def opened(app: str) -> Iterator[tuple[Path, str] | None]:
    if not configured():
        ui.fail("esta máquina não está ligada a um servidor de backup: instale o app backup")
    picked = _source(app)
    if picked is None:
        yield None
        return
    place, chosen = picked
    target = config.home() / ".backup-restore" / app
    _clean(target)
    target.mkdir(parents=True, mode=0o700)
    code, output = restic("restore", f"{chosen['id']}:{chosen['paths'][0]}", "--target", str(target), destination=place)
    if code:
        _clean(target)
        ui.fail(f"o restic não trouxe a versão: {tail(output)}")
    try:
        yield target, when(chosen)
    finally:
        _clean(target)


def _empty_target(value: str) -> str:
    path = Path(value.strip()).expanduser()
    if not path.is_absolute():
        raise ValueError("use um caminho completo")
    if path.exists() and any(path.iterdir()):
        raise ValueError("essa pasta já tem arquivos: escolha uma nova ou vazia")
    return str(path)


def restore_data(app: str, name: str) -> None:
    if not configured():
        ui.fail("esta máquina não está ligada a um servidor de backup: instale o app backup")
    picked = _source(app, name)
    if picked is None:
        return
    place, chosen = picked
    ui.note("A versão é restaurada numa pasta nova, sem mexer na original: depois, copie dela o que precisar.")
    stamp = when(chosen).replace("/", "-").replace(" ", "-").replace(":", "")
    slug = "".join(char if char.isalnum() else "-" for char in name).strip("-")
    target = Path(ui.ask("restaurar na pasta", default=str(Path.home() / "Restaurado" / f"{app}-{slug}-{stamp}"), validate=_empty_target))
    target.mkdir(parents=True, exist_ok=True)
    code, output = restic("restore", f"{chosen['id']}:{chosen['paths'][0]}", "--target", str(target), destination=place)
    if code:
        ui.fail(f"o restic não trouxe a versão: {tail(output)}")
    ui.ok(f"{name} de {when(chosen)} restaurado em {target}")


def summary(app: str, data: Sequence[tuple[str, str, str, str]] = ()) -> None:
    ui.section("Backup")
    if not configured():
        ui.table([["Servidor de backup", ui.pending("esta máquina não está ligada (app backup)")]])
        return
    rows: list[list[str | ui.Cell]] = [["Servidor", settings()["BACKUP_URL"]]]
    for title, part, key, name in [("Configuração", "", TARGETS, ""), *data]:
        on = units.active(f"{unit(app, part)}.timer")
        rows.append([f"{title}: backup diário", ui.good("ligado") if on else ui.pending("desligado")])
        for item in targets(app, key):
            found = versions(app, item, name)
            rows.append([f"  em {item.path}", ui.good(f"{when(found[0])} ({len(found)} versões)") if found else ui.pending("nenhum ainda")])
    ui.table(rows)
