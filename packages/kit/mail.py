from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from kit import config, ui


class MailError(Exception):
    pass


@dataclass(frozen=True)
class Attachment:
    name: str
    type: str
    data: bytes
    cid: str = ""


def settings_file() -> Path:
    return config.home() / "mail.env"


def settings() -> dict[str, str]:
    return config.read_env(settings_file())


def configured() -> bool:
    values = settings()
    return bool(values.get("MAIL_URL") and values.get("MAIL_KEY"))


def save(url: str, key: str) -> None:
    config.home().mkdir(mode=0o700, exist_ok=True)
    config.write_env(settings_file(), {"MAIL_URL": url.rstrip("/"), "MAIL_KEY": key})


def forget() -> None:
    if settings_file().exists():
        settings_file().unlink()
        ui.ok("esta máquina deixou de enviar e-mails")


def _request(method: str, path: str, payload: object = None, url: str = "", key: str = "", timeout: float = 60) -> dict:
    values = settings()
    base = (url or values.get("MAIL_URL", "")).rstrip("/")
    secret = key or values.get("MAIL_KEY", "")
    if not base or not secret:
        raise MailError("envio de e-mail não configurado nesta máquina")
    headers = {"Content-Type": "application/json", "X-Astroverso-Chave": secret, "User-Agent": "astroverso"}
    data = None if payload is None else json.dumps(payload).encode()
    try:
        with urllib.request.urlopen(urllib.request.Request(base + path, data, headers, method=method), timeout=timeout) as response:
            return json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as problem:
        with problem:
            try:
                body = json.loads(problem.read())
            except ValueError:
                body = {}
        if problem.code == 502 and isinstance(body, dict) and "erros" in body:
            return body
        raise MailError(f"{problem.code} {body.get('erro', '') if isinstance(body, dict) else ''}".strip() or str(problem)) from None
    except (OSError, ValueError) as problem:
        raise MailError(f"{base} não respondeu ({getattr(problem, 'reason', problem)})") from None


def check(url: str = "", key: str = "") -> None:
    _request("GET", "/conferir", url=url, key=key, timeout=20)


def send(
    to: str | Sequence[str],
    subject: str,
    text: str = "",
    html: str = "",
    attachments: Sequence[Attachment] = (),
) -> list[str]:
    if not configured():
        return []
    recipients = [to] if isinstance(to, str) else list(to)
    payload = {
        "para": recipients,
        "assunto": subject,
        "texto": text,
        "html": html,
        "anexos": [{"nome": item.name, "tipo": item.type, "base64": base64.b64encode(item.data).decode(), "cid": item.cid}
                   for item in attachments],
    }
    try:
        answer = _request("POST", "/enviar", payload)
    except MailError as problem:
        ui.warn(f"e-mail não enviado: {problem}")
        return []
    for error in answer.get("erros") or []:
        ui.warn(f"e-mail não entregue a {error.get('para')}: {error.get('erro')} (o destinatário está confirmado na Cloudflare?)")
    return [str(item) for item in answer.get("enviados") or []]
