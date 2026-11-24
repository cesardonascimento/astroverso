from __future__ import annotations

import ipaddress
import re

DOMAIN = re.compile(r"^(?=.{1,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")
NAME = re.compile(r"^[a-z][a-z0-9-]*$")
EMAIL = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")


def domain(value: str) -> str:
    text = value.strip().lower()
    for prefix in ("https://", "http://", "*."):
        text = text.removeprefix(prefix)
    text = text.rstrip("/").rstrip(".")
    if not DOMAIN.match(text):
        raise ValueError("domínio inválido: use algo como casa.com")
    return text


def ipv4(value: str) -> str:
    try:
        return str(ipaddress.IPv4Address(value.strip()))
    except ValueError:
        raise ValueError("IP inválido: quatro números de 0 a 255, como 192.168.0.10") from None


def port(value: str) -> str:
    text = value.strip()
    if not text.isdigit() or not 1 <= int(text) <= 65535:
        raise ValueError("a porta é um número entre 1 e 65535")
    return str(int(text))


def name(value: str) -> str:
    text = value.strip().lower()
    if not NAME.match(text) or len(text) > 63:
        raise ValueError("use letras, números e hífen, começando por letra")
    return text


def email(value: str) -> str:
    text = value.strip()
    if not EMAIL.match(text):
        raise ValueError("e-mail inválido: use algo como nome@casa.com")
    return text
