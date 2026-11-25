from __future__ import annotations

import configparser
import io
import shutil
from collections.abc import Sequence
from pathlib import Path

from kit import config, run, ui

APP = "cloud"


def conf() -> Path:
    return config.state(APP) / "rclone.conf"


def _parser() -> configparser.ConfigParser:
    parser = configparser.ConfigParser(interpolation=None)
    parser.optionxform = str
    try:
        parser.read_string(conf().read_text())
    except FileNotFoundError:
        pass
    return parser


def _write(parser: configparser.ConfigParser) -> None:
    buffer = io.StringIO()
    parser.write(buffer)
    temporary = conf().with_suffix(".tmp")
    temporary.write_text(buffer.getvalue())
    temporary.chmod(0o600)
    temporary.replace(conf())


def sections() -> list[str]:
    return _parser().sections()


def set_section(name: str, values: dict[str, str]) -> None:
    parser = _parser()
    if parser.has_section(name):
        parser.remove_section(name)
    parser[name] = values
    _write(parser)


def drop_section(name: str) -> None:
    parser = _parser()
    if parser.remove_section(name):
        _write(parser)


def obscure(secret: str) -> str:
    return run.capture(["rclone", "obscure", "-"], input=secret)


def command(args: Sequence[str], unshare: bool = False) -> list[str]:
    prefix = ["podman", "unshare"] if unshare and shutil.which("podman") else []
    return [*prefix, "rclone", *args, "--config", str(conf())]


def call(args: Sequence[str], env: dict[str, str] | None = None, unshare: bool = False, timeout: float | None = None) -> tuple[int, str]:
    return run.output(command(args, unshare), env=env, timeout=timeout)


def tail(output: str, lines: int = 3) -> str:
    found = [line.strip() for line in output.splitlines() if line.strip()]
    return "\n".join(found[-lines:])[:600] if found else "sem mensagem"


def folders(account: str, path: str) -> list[str] | None:
    code, output = call(["lsf", "--dirs-only", f"{account}:{path}"], timeout=180)
    if code:
        ui.warn(f"não deu para listar a pasta: {tail(output, 1)}")
        return None
    return sorted(line.rstrip("/") for line in output.splitlines() if line.strip())


def mkdir(account: str, path: str) -> bool:
    code, output = call(["mkdir", f"{account}:{path}"], timeout=180)
    if code:
        ui.warn(f"não deu para criar a pasta: {tail(output, 1)}")
    return code == 0
