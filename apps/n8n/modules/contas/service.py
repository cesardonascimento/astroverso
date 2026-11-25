from __future__ import annotations

import base64
import binascii
import json
import os
import signal
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import contas

LIMITE = 80 * 1024 * 1024


def _arquivo(corpo: dict) -> bytes:
    try:
        return base64.b64decode(str(corpo.get("arquivo") or ""), validate=True)
    except (binascii.Error, ValueError):
        raise ValueError("arquivo tem de vir em base64") from None


def qrcodes(corpo: dict) -> dict:
    dados = _arquivo(corpo)
    if not dados:
        raise ValueError("arquivo vazio")
    tipo = "imagem" if corpo.get("tipo") == "imagem" else "pdf"
    senhas = [str(item) for item in corpo.get("senhas") or [] if str(item)]
    try:
        return {"codigos": contas.ler_qrcodes(dados, tipo, senhas, int(corpo.get("paginas") or 5))}
    except Exception as erro:
        return {"codigos": [], "erro": f"não abriu o {tipo}: {erro}"}


def pix(corpo: dict) -> dict:
    codigo = str(corpo.get("codigo") or "")
    if corpo.get("formato") == "png":
        return {"png": base64.b64encode(contas.pix_png(codigo, int(corpo.get("largura") or 300))).decode()}
    return {"svg": contas.pix_svg(codigo, int(corpo.get("largura") or 220))}


def barras(corpo: dict) -> dict:
    codigo = str(corpo.get("barras") or "")
    if corpo.get("formato") == "png":
        imagem, largura = contas.barras_png(codigo)
        return {"png": base64.b64encode(imagem).decode(), "largura": largura}
    return {"svg": contas.barras_svg(codigo), "largura": contas.barras_itf(codigo)[1]}


ROTAS = {"/v1/qrcodes": qrcodes, "/v1/pix": pix, "/v1/barras": barras}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path == "/v1/saude":
            self.answer(200, {"ok": True})
        else:
            self.answer(404, {"erro": "rota desconhecida"})

    def do_POST(self) -> None:
        rota = ROTAS.get(self.path)
        if rota is None:
            self.answer(404, {"erro": "rota desconhecida"})
            return
        tamanho = int(self.headers.get("Content-Length") or 0)
        if tamanho > LIMITE:
            self.answer(413, {"erro": "pedido grande demais"})
            return
        try:
            corpo = json.loads(self.rfile.read(tamanho) or b"{}")
            if not isinstance(corpo, dict):
                raise ValueError("o corpo tem de ser um objeto JSON")
            self.answer(200, rota(corpo))
        except ValueError as erro:
            self.answer(400, {"erro": str(erro)})

    def answer(self, code: int, body: dict) -> None:
        data = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format: str, *args: object) -> None:
        sys.stderr.write(f"[contas] {self.address_string()} {format % args}\n")


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    ThreadingHTTPServer(("0.0.0.0", int(os.environ.get("PORT", "8080"))), Handler).serve_forever()
