from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Mapping, Sequence
from pathlib import Path

from kit import config, ui

LEVELS = ("info", "sucesso", "aviso", "erro")


class DiscordError(Exception):
    pass


def settings_file() -> Path:
    return config.home() / "discord.env"


def settings() -> dict[str, str]:
    return config.read_env(settings_file())


def configured() -> bool:
    values = settings()
    return bool(values.get("DISCORD_URL") and values.get("DISCORD_KEY"))


def save(url: str, key: str) -> None:
    config.home().mkdir(mode=0o700, exist_ok=True)
    config.write_env(settings_file(), {"DISCORD_URL": url.rstrip("/"), "DISCORD_KEY": key})


def forget() -> None:
    if settings_file().exists():
        settings_file().unlink()
        ui.ok("esta máquina deixou de usar o Discord")


def request(method: str, path: str, payload: object = None, url: str = "", key: str = "", timeout: float = 15) -> dict:
    values = settings()
    base = (url or values.get("DISCORD_URL", "")).rstrip("/")
    secret = key or values.get("DISCORD_KEY", "")
    if not base:
        raise DiscordError("Discord não configurado nesta máquina")
    headers = {"Content-Type": "application/json"}
    if secret:
        headers["Authorization"] = f"Bearer {secret}"
    data = None if payload is None else json.dumps(payload).encode()
    try:
        with urllib.request.urlopen(urllib.request.Request(base + path, data, headers, method=method), timeout=timeout) as response:
            return json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as problem:
        with problem:
            try:
                reason = json.loads(problem.read()).get("erro", "")
            except ValueError:
                reason = ""
        raise DiscordError(f"{problem.code} {reason or problem.reason}".strip()) from None
    except (OSError, ValueError) as problem:
        raise DiscordError(f"{base} não respondeu ({getattr(problem, 'reason', problem)})") from None


def whoami(url: str = "", key: str = "") -> str:
    return str(request("GET", "/v1/eu", url=url, key=key).get("cliente", ""))


def notify(
    app: str,
    level: str,
    title: str,
    text: str = "",
    fields: Mapping[str, str] | None = None,
    actions: Sequence[tuple[str, str]] = (),
) -> bool:
    if level not in LEVELS:
        raise ValueError(f"nível inválido: {level}")
    if not configured():
        return False
    payload: dict[str, object] = {"app": app, "nivel": level, "titulo": title, "texto": text, "campos": dict(fields or {})}
    if actions:
        payload["botoes"] = [{"rotulo": label, "acao": command} for label, command in actions]
    try:
        request("POST", "/v1/mensagens", payload)
    except DiscordError as problem:
        ui.warn(f"aviso não enviado ao Discord: {problem}")
        return False
    return True
