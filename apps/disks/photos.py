from __future__ import annotations

import json
import time
from datetime import date, datetime, timedelta
from pathlib import Path

from kit import changes, config, discord, disks, run, ui, units
from kit.watch import Problem

APP = "disks"
UNIT = "astroverso-disks-photos"
COMMAND = Path(__file__).resolve().parents[2] / "astroverso"
KEEP_DAYS = 30
LIMIT = 10
FULL = 90
CURRENT = "atual"
HISTORY = "versoes"


def pairs_file() -> Path:
    return config.state(APP) / "photos.json"


def state_file() -> Path:
    return config.state(APP) / "photos-state.json"


def _read(path: Path, empty: object) -> object:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return empty


def _write(path: Path, data: object) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    temporary.chmod(0o600)
    temporary.replace(path)


def pairs() -> list[dict[str, str]]:
    found = _read(pairs_file(), [])
    return [item for item in found if isinstance(item, dict) and item.get("source") and item.get("target")] if isinstance(found, list) else []


def save_pairs(items: list[dict[str, str]]) -> None:
    _write(pairs_file(), items)


def states() -> dict[str, dict]:
    found = _read(state_file(), {})
    return found if isinstance(found, dict) else {}


def record(target: str, **values: object) -> None:
    current = states()
    current[target] = {**current.get(target, {}), **values}
    _write(state_file(), current)


def by_uuid() -> dict[str, disks.Disk]:
    return {disk.uuid: disk for disk in disks.mounts()}


def label(uuid: str, known: dict[str, disks.Disk] | None = None) -> str:
    disk = (known or by_uuid()).get(uuid)
    return disk.name if disk else f"disco {uuid[:8]}"


def mark(target: disks.Disk, source: disks.Disk) -> None:
    content = {"source_uuid": source.uuid, "source_name": source.name, "since": date.today().isoformat()}
    (target.path / disks.PHOTO).write_text(json.dumps(content, ensure_ascii=False, indent=2) + "\n")


def unmark(target: disks.Disk) -> None:
    (target.path / disks.PHOTO).unlink(missing_ok=True)


def rsync_args(source: Path, target: Path, day: str, dry: bool = False) -> list[str]:
    return ["podman", "unshare", "rsync", "-aH", "--numeric-ids", "--delete", "--backup", f"--backup-dir={target / HISTORY / day}",
            "--exclude=/lost+found", *(["--dry-run", "--itemize-changes"] if dry else []), f"{source}/", f"{target / CURRENT}/"]


def count_files(path: Path) -> int:
    if not path.is_dir():
        return 0
    code, output = run.output(["podman", "unshare", "find", str(path), "-mindepth", "1", "-not", "-type", "d"])
    return len(output.splitlines()) if code == 0 else 0


def deletions(source: Path, target: Path) -> tuple[list[str], str]:
    code, output = run.output(rsync_args(source, target, date.today().isoformat(), dry=True))
    if code not in (0, 24):
        return [], _tail(output)
    return [line.split(None, 1)[1] for line in output.splitlines() if line.startswith("*deleting") and len(line.split(None, 1)) > 1], ""


def _tail(output: str) -> str:
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    return lines[-1][:300] if lines else "sem mensagem"


def history(target: Path) -> list[Path]:
    folder = target / HISTORY
    if not folder.is_dir():
        return []
    found = []
    for item in folder.iterdir():
        try:
            date.fromisoformat(item.name)
        except ValueError:
            continue
        if item.is_dir():
            found.append(item)
    return sorted(found, key=lambda item: item.name)


def _remove(path: Path) -> None:
    run.cmd(["podman", "unshare", "rm", "-rf", "--", str(path)])


def prune(target: Path, today: date | None = None) -> int:
    limit = (today or date.today()) - timedelta(days=KEEP_DAYS)
    gone = 0
    for item in history(target):
        if date.fromisoformat(item.name) < limit:
            _remove(item)
            gone += 1
    return gone


def _percent(path: Path) -> int:
    used, total = disks.usage(path)
    return round(used * 100 / total) if total else 0


def make_room(target: Path) -> int:
    gone = 0
    for item in history(target):
        if _percent(target) < FULL:
            break
        if item.name == date.today().isoformat():
            break
        _remove(item)
        gone += 1
    return gone


def shoot(pair: dict[str, str], force: bool = False) -> str:
    known = by_uuid()
    source, target = known.get(pair["source"]), known.get(pair["target"])
    if source is None or target is None:
        return "um dos discos saiu do cadastro"
    for disk in (source, target):
        if not disks.mounted(disk.path) or not disks.responds(disk.path):
            return f"o disco {disk.name} não está montado ou não responde: nada foi feito"
    (target.path / CURRENT).mkdir(exist_ok=True)
    if not force:
        gone, problem = deletions(source.path, target.path)
        if problem:
            return f"o rsync não conseguiu comparar os discos: {problem}"
        total = count_files(target.path / CURRENT)
        if gone and total and len(gone) * 100 > total * LIMIT:
            record(target.uuid, blocked=len(gone), total=total)
            return f"tiraria {len(gone)} de {total} arquivos do {CURRENT}/ (mais de {LIMIT}%): nada foi feito; confira e use Liberar a fotografia"
    make_room(target.path)
    day = date.today().isoformat()
    code, output = run.output(rsync_args(source.path, target.path, day))
    if code not in (0, 24):
        return f"o rsync falhou: {_tail(output)}"
    prune(target.path)
    make_room(target.path)
    record(target.uuid, last=datetime.now().isoformat(timespec="minutes"), blocked=0, error="")
    return ""


def run_all(force: bool = False, notify: bool = True) -> bool:
    items = pairs()
    if not items:
        ui.info("nenhuma fotografia cadastrada: adicione em Fotografias dos discos")
        return True
    known = by_uuid()
    ok = True
    for pair in items:
        name = f"{label(pair['source'], known)} → {label(pair['target'], known)}"
        ui.info(f"fotografando {name} (pode demorar)...")
        started = time.monotonic()
        problem = shoot(pair, force)
        if problem:
            ok = False
            record(pair["target"], error=problem)
            ui.warn(f"fotografia {name}: {problem}")
            if notify:
                discord.notify(APP, "erro", f"Fotografia {name} falhou", problem, actions=(("Tentar de novo", f"{APP}:photos-now"),))
            continue
        seconds = int(time.monotonic() - started)
        ui.ok(f"fotografia {name} pronta em {seconds} s")
        if notify:
            discord.notify(APP, "info", f"Fotografia {name} pronta", f"Em {seconds} s.")
    return ok


def units_text() -> dict[str, str]:
    return {
        f"{UNIT}.timer": "\n".join([
            "[Unit]",
            "Description=Astroverso disks: fotografia dos discos toda noite",
            "",
            "[Timer]",
            "OnCalendar=*-*-* 03:00:00",
            "Persistent=true",
            "",
            "[Install]",
            "WantedBy=timers.target",
            "",
        ]),
        f"{UNIT}.service": "\n".join([
            "[Unit]",
            "Description=Astroverso disks: fotografia dos discos",
            "",
            "[Service]",
            "Type=oneshot",
            f"ExecStart={COMMAND} {APP} action photos-timer",
            "",
        ]),
    }


def change() -> changes.Change:
    texts = units_text()
    return changes.Change(
        "photos", "Tirar a fotografia dos discos toda noite (03:00)",
        f"Um timer do usuário ({UNIT}.timer) deixa a pasta {CURRENT}/ de cada disco de fotografias igual ao disco de origem "
        f"(rsync) e guarda em {HISTORY}/<data>/ o que mudou ou foi apagado naquela noite, por {KEEP_DAYS} dias. Não roda com um "
        f"dos discos desligado, e para (avisando no Discord) se fosse tirar mais de {LIMIT}% dos arquivos de uma vez.",
        lambda: units.active(f"{UNIT}.timer"),
        lambda: units.install(texts, [f"{UNIT}.timer"]),
        lambda: units.remove(list(texts)),
    )


def _candidates(exclude: set[str]) -> list[disks.Disk]:
    return [disk for disk in disks.mounts() if disk.uuid not in exclude and disks.responds(disk.path)]


def add() -> None:
    taken = {uuid for pair in pairs() for uuid in (pair["source"], pair["target"])}
    sources = [disk for disk in _candidates(taken) if not (disk.path / disks.PHOTO).exists()]
    if len(sources) < 1 or len(_candidates(taken)) < 2:
        ui.fail("a fotografia precisa de dois discos montados e livres (um de origem e um de fotografias): cadastre em Discos da máquina")
    ui.note(
        "A fotografia copia, toda noite, um disco inteiro (a origem) para outro (o disco de fotografias): a pasta "
        f"{CURRENT}/ fica igual à origem e {HISTORY}/<data>/ guarda o que mudou ou foi apagado em cada noite. Nada mais "
        "grava no disco de fotografias, e é dele que sai o Resgatar um disco."
    )
    source = sources[ui.menu("Qual disco fotografar?", [disk.name for disk in sources])]
    targets = [disk for disk in _candidates(taken | {source.uuid})]
    target = targets[ui.menu("Em qual disco guardar as fotografias?", [disk.name for disk in targets])]
    used, _ = disks.usage(source.path)
    _, total = disks.usage(target.path)
    if total < used:
        ui.fail(f"o disco {target.name} é menor que o que já está em {source.name}")
    if (target.path / CURRENT).is_dir():
        ui.info(f"o disco {target.name} já tem uma pasta {CURRENT}/: a primeira fotografia só copia o que mudou")
    ui.warn(f"o disco {target.name} passa a ser só de fotografias: nenhum app grava mais nele (o que já existe nele fica)")
    if not ui.confirm(f"Fotografar {source.name} em {target.name} toda noite?", default=False):
        return
    mark(target, source)
    save_pairs(pairs() + [{"source": source.uuid, "target": target.uuid}])
    ui.ok(f"fotografia cadastrada: {source.name} → {target.name}")
    item = change()
    if not item.applied():
        item.apply()
        config.save(APP, {changes.key(item): "yes"})


def drop() -> None:
    items = pairs()
    known = by_uuid()
    chosen = ui.checklist("Quais fotografias tirar?", [f"{label(p['source'], known)} → {label(p['target'], known)}" for p in items],
                          cancel=True) or []
    if not chosen:
        return
    ui.warn("as fotografias que já estão nos discos ficam; os discos voltam a ser comuns")
    if not ui.confirm("confirma?", default=False):
        return
    for index in chosen:
        target = known.get(items[index]["target"])
        if target is not None:
            unmark(target)
    save_pairs([item for i, item in enumerate(items) if i not in chosen])
    ui.ok("fotografias tiradas")


def rows() -> list[list[str | ui.Cell]]:
    known = by_uuid()
    found = states()
    result: list[list[str | ui.Cell]] = []
    for pair in pairs():
        info = found.get(pair["target"], {})
        if info.get("blocked"):
            situation: str | ui.Cell = ui.bad(f"parada: {info['blocked']} exclusões")
        elif info.get("error"):
            situation = ui.bad(str(info["error"])[:60])
        elif info.get("last"):
            situation = ui.good(str(info["last"]).replace("T", " "))
        else:
            situation = ui.pending("nenhuma ainda")
        target = known.get(pair["target"])
        kept = len(history(target.path)) if target and disks.responds(target.path) else 0
        result.append([label(pair["source"], known), label(pair["target"], known), situation, f"{kept} dia(s)"])
    return result


def manage() -> None:
    while True:
        if pairs():
            ui.table(rows(), ["Origem", "Fotografias em", "Última", "Histórico"])
        options = ["Adicionar uma fotografia"] + (["Tirar fotografias"] if pairs() else []) + ["Pronto"]
        choice = options[ui.menu("Fotografias dos discos", options)]
        if choice == "Pronto":
            return
        if choice.startswith("Adicionar"):
            add()
        else:
            drop()


def release() -> None:
    known = by_uuid()
    blocked = [pair for pair in pairs() if states().get(pair["target"], {}).get("blocked")]
    if not blocked:
        ui.info("nenhuma fotografia parada")
        return
    index = ui.menu("Qual?", [f"{label(p['source'], known)} → {label(p['target'], known)}" for p in blocked] + ["Voltar"])
    if index >= len(blocked):
        return
    pair = blocked[index]
    source, target = known.get(pair["source"]), known.get(pair["target"])
    if source is None or target is None:
        ui.fail("um dos discos saiu do cadastro")
    gone, problem = deletions(source.path, target.path)
    if problem:
        ui.fail(problem)
    ui.info(f"{len(gone)} arquivo(s) sairiam de {CURRENT}/ (e iriam para {HISTORY}/{date.today().isoformat()}/), por exemplo:")
    ui.prefixed("\n".join(gone[:20]) or "(nenhum)")
    if not ui.confirm("Liberar e fotografar agora?", default=False):
        return
    problem = shoot(pair, force=True)
    if problem:
        ui.fail(problem)
    ui.ok("fotografia pronta")


def collect() -> dict[str, Problem]:
    found: dict[str, Problem] = {}
    known = by_uuid()
    info = states()
    for pair in pairs():
        name = f"{label(pair['source'], known)} → {label(pair['target'], known)}"
        current = info.get(pair["target"], {})
        if current.get("blocked"):
            found[f"photo:{pair['target']}"] = Problem("erro", f"Fotografia {name} parada",
                                                       f"Ela tiraria {current['blocked']} arquivos de uma vez: confira e use Liberar a fotografia.", "photo")
            continue
        last = current.get("last")
        try:
            age = datetime.now() - datetime.fromisoformat(str(last)) if last else None
        except ValueError:
            age = None
        if age is not None and age > timedelta(hours=36):
            found[f"photo:{pair['target']}"] = Problem("erro", f"Fotografia {name} sem rodar há {int(age.total_seconds() // 3600)} h",
                                                       str(current.get("error") or "Veja o canal #disks."), "photo")
    return found
