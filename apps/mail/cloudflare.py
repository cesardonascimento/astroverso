from __future__ import annotations

import json
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://api.cloudflare.com/client/v4"
COMPATIBILITY_DATE = "2026-10-01"
WORKER = "astroverso-mail"
KV_TITLE = "astroverso-mail"
SCRIPT = Path(__file__).with_name("worker.js")


class CloudflareError(Exception):
    pass


def _send(token: str, method: str, path: str, data: bytes | None = None, content_type: str = "application/json") -> tuple[int, bytes]:
    headers = {"Authorization": f"Bearer {token}", "User-Agent": "astroverso"}
    if data is not None:
        headers["Content-Type"] = content_type
    request = urllib.request.Request(f"{API}/{path}", data, headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as problem:
        with problem:
            return problem.code, problem.read()
    except OSError as problem:
        raise CloudflareError(f"a Cloudflare não respondeu ({getattr(problem, 'reason', problem)})") from None


def call(token: str, method: str, path: str, payload: object = None) -> object:
    code, body = _send(token, method, path, None if payload is None else json.dumps(payload).encode())
    try:
        data = json.loads(body or b"{}")
    except ValueError:
        raise CloudflareError(f"resposta inválida da Cloudflare ({method} {path.split('?')[0]}, HTTP {code})") from None
    if not data.get("success"):
        errors = "; ".join(str(item.get("message", item)) for item in data.get("errors") or []) or f"HTTP {code}"
        raise CloudflareError(f"a Cloudflare recusou {method} {path.split('?')[0]}: {errors}")
    return data.get("result")


def verify(token: str) -> bool:
    try:
        result = call(token, "GET", "user/tokens/verify")
    except CloudflareError:
        return False
    return isinstance(result, dict) and result.get("status") == "active"


def zone(token: str, domain: str) -> tuple[str, str, str]:
    labels = domain.split(".")
    for start in range(len(labels) - 1):
        name = ".".join(labels[start:])
        found = call(token, "GET", f"zones?name={urllib.parse.quote(name)}")
        if isinstance(found, list) and found:
            return str(found[0]["id"]), str(found[0]["account"]["id"]), str(found[0]["name"])
    raise CloudflareError(f"o token não enxerga a zona de {domain}: confira a permissão Zone → Zone → Read nessa zona")


def mx(token: str, zone_id: str, domain: str) -> list[str]:
    found = call(token, "GET", f"zones/{zone_id}/dns_records?type=MX&name={urllib.parse.quote(domain)}")
    return [str(item.get("content", "")) for item in found] if isinstance(found, list) else []


def routing_enable(token: str, zone_id: str, domain: str, zone_name: str) -> None:
    call(token, "POST", f"zones/{zone_id}/email/routing/dns", {} if domain == zone_name else {"name": domain})


def routing_disable(token: str, zone_id: str, domain: str, zone_name: str) -> None:
    payload = {} if domain == zone_name else {"name": domain}
    code, body = _send(token, "DELETE", f"zones/{zone_id}/email/routing/dns", json.dumps(payload).encode())
    if code >= 300:
        raise CloudflareError(f"a Cloudflare recusou desligar o Email Routing (HTTP {code})")


def kv_list(token: str, account: str) -> list[dict]:
    found = call(token, "GET", f"accounts/{account}/storage/kv/namespaces?per_page=100")
    return [item for item in found if isinstance(item, dict)] if isinstance(found, list) else []


def kv_ensure(token: str, account: str, title: str = KV_TITLE) -> tuple[str, bool]:
    existing = next((item["id"] for item in kv_list(token, account) if item.get("title") == title), "")
    if existing:
        return str(existing), False
    created = call(token, "POST", f"accounts/{account}/storage/kv/namespaces", {"title": title})
    if not isinstance(created, dict) or not created.get("id"):
        raise CloudflareError("a Cloudflare não devolveu o KV criado")
    return str(created["id"]), True


def kv_delete(token: str, account: str, kv: str) -> None:
    call(token, "DELETE", f"accounts/{account}/storage/kv/namespaces/{kv}")


def kv_keys(token: str, account: str, kv: str) -> list[str]:
    found = call(token, "GET", f"accounts/{account}/storage/kv/namespaces/{kv}/keys?limit=1000")
    return [str(item["name"]) for item in found] if isinstance(found, list) else []


def kv_get(token: str, account: str, kv: str, key: str) -> bytes | None:
    code, body = _send(token, "GET", f"accounts/{account}/storage/kv/namespaces/{kv}/values/{urllib.parse.quote(key)}")
    if code == 404:
        return None
    if code != 200:
        raise CloudflareError(f"não foi possível ler {key} no KV (HTTP {code})")
    return body


def kv_remove(token: str, account: str, kv: str, key: str) -> None:
    call(token, "DELETE", f"accounts/{account}/storage/kv/namespaces/{kv}/values/{urllib.parse.quote(key)}")


def worker_publish(token: str, account: str, kv: str, allowed: str, sender: str, key: str) -> None:
    metadata = {
        "main_module": "worker.js",
        "compatibility_date": COMPATIBILITY_DATE,
        "bindings": [
            {"type": "kv_namespace", "name": "MAIL", "namespace_id": kv},
            {"type": "plain_text", "name": "ALLOWED_DOMAINS", "text": allowed},
            {"type": "plain_text", "name": "REMETENTE", "text": sender},
            {"type": "secret_text", "name": "CHAVE_ENVIO", "text": key},
            {"type": "send_email", "name": "ENVIO"},
        ],
    }
    boundary = f"astroverso{secrets.token_hex(12)}"
    parts = [
        ("metadata", "", "application/json", json.dumps(metadata).encode()),
        ("worker.js", "worker.js", "application/javascript+module", SCRIPT.read_bytes()),
    ]
    body = b""
    for name, filename, kind, content in parts:
        disposition = f'form-data; name="{name}"' + (f'; filename="{filename}"' if filename else "")
        body += f"--{boundary}\r\nContent-Disposition: {disposition}\r\nContent-Type: {kind}\r\n\r\n".encode() + content + b"\r\n"
    body += f"--{boundary}--\r\n".encode()
    code, answer = _send(token, "PUT", f"accounts/{account}/workers/scripts/{WORKER}", body, f"multipart/form-data; boundary={boundary}")
    try:
        data = json.loads(answer or b"{}")
    except ValueError:
        data = {}
    if code >= 300 or not data.get("success"):
        errors = "; ".join(str(item.get("message", item)) for item in data.get("errors") or []) or f"HTTP {code}"
        raise CloudflareError(f"a Cloudflare recusou publicar o Worker: {errors}")


def workers_dev(token: str, account: str) -> str:
    try:
        found = call(token, "GET", f"accounts/{account}/workers/subdomain")
        subdomain = str(found.get("subdomain") or "") if isinstance(found, dict) else ""
    except CloudflareError:
        subdomain = ""
    if not subdomain:
        subdomain = f"astroverso-{secrets.token_hex(4)}"
        call(token, "PUT", f"accounts/{account}/workers/subdomain", {"subdomain": subdomain})
    call(token, "POST", f"accounts/{account}/workers/scripts/{WORKER}/subdomain", {"enabled": True})
    return f"https://{WORKER}.{subdomain}.workers.dev"


def workers(token: str, account: str) -> list[str]:
    found = call(token, "GET", f"accounts/{account}/workers/scripts")
    return [str(item.get("id")) for item in found if isinstance(item, dict)] if isinstance(found, list) else []


def worker_delete(token: str, account: str, name: str) -> None:
    call(token, "DELETE", f"accounts/{account}/workers/scripts/{name}")


def _rules(token: str, zone_id: str) -> list[dict]:
    found = call(token, "GET", f"zones/{zone_id}/email/routing/rules?per_page=50")
    return [item for item in found if isinstance(item, dict)] if isinstance(found, list) else []


def rule_id(token: str, zone_id: str, address: str) -> str:
    for rule in _rules(token, zone_id):
        if any(matcher.get("value") == address for matcher in rule.get("matchers") or []):
            return str(rule.get("id") or rule.get("tag") or "")
    return ""


def rule_ensure(token: str, zone_id: str, address: str) -> None:
    body = {
        "name": "astroverso mail",
        "enabled": True,
        "matchers": [{"type": "literal", "field": "to", "value": address}],
        "actions": [{"type": "worker", "value": [WORKER]}],
    }
    existing = rule_id(token, zone_id, address)
    if existing:
        call(token, "PUT", f"zones/{zone_id}/email/routing/rules/{existing}", body)
    else:
        call(token, "POST", f"zones/{zone_id}/email/routing/rules", body)


def rule_delete(token: str, zone_id: str, address: str) -> bool:
    existing = rule_id(token, zone_id, address)
    if existing:
        call(token, "DELETE", f"zones/{zone_id}/email/routing/rules/{existing}")
    return bool(existing)


def addresses(token: str, account: str) -> list[dict]:
    found = call(token, "GET", f"accounts/{account}/email/routing/addresses?per_page=50")
    return [item for item in found if isinstance(item, dict)] if isinstance(found, list) else []


def address_add(token: str, account: str, email: str) -> None:
    call(token, "POST", f"accounts/{account}/email/routing/addresses", {"email": email})


def address_remove(token: str, account: str, identifier: str) -> None:
    call(token, "DELETE", f"accounts/{account}/email/routing/addresses/{identifier}")


def wait_mx(token: str, zone_id: str, domain: str, seconds: float = 120) -> bool:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if any("mx.cloudflare.net" in item for item in mx(token, zone_id, domain)):
            return True
        time.sleep(5)
    return False
