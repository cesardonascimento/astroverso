from __future__ import annotations

import io
import struct
import zlib
from collections.abc import Sequence

PADROES = ("00110", "10001", "01001", "11000", "00101", "10100", "01100", "00011", "10010", "01010")
FINO = 1
LARGO = 3
MARGEM = 10
ALTURA_SVG = 50
ALTURA_PNG = 100
ESCALA_PNG = 2


def barras_itf(codigo: str) -> tuple[list[tuple[int, int]], int]:
    if not codigo.isdigit() or len(codigo) % 2:
        raise ValueError("o código de barras tem de ter só dígitos, em número par (44 num boleto)")
    barras: list[tuple[int, int]] = []
    x = MARGEM

    def desenhar(largura: int, barra: bool) -> None:
        nonlocal x
        if barra:
            barras.append((x, largura))
        x += largura

    for barra in (True, False, True, False):
        desenhar(FINO, barra)
    for i in range(0, len(codigo), 2):
        a, b = PADROES[int(codigo[i])], PADROES[int(codigo[i + 1])]
        for j in range(5):
            desenhar(LARGO if a[j] == "1" else FINO, True)
            desenhar(LARGO if b[j] == "1" else FINO, False)
    desenhar(LARGO, True)
    desenhar(FINO, False)
    desenhar(FINO, True)
    return barras, x + MARGEM


def barras_svg(codigo: str) -> str:
    barras, largura = barras_itf(codigo)
    retangulos = "".join(f'<rect x="{x}" y="0" width="{w}" height="{ALTURA_SVG}"/>' for x, w in barras)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {largura} {ALTURA_SVG}" width="{largura * 2}" '
            f'height="{ALTURA_SVG * 2}" shape-rendering="crispEdges"><rect width="{largura}" height="{ALTURA_SVG}" fill="#fff"/>'
            f'<g fill="#000">{retangulos}</g></svg>')


def png_cinza(largura: int, altura: int, linha: bytes) -> bytes:
    def bloco(tipo: bytes, dados: bytes) -> bytes:
        return struct.pack(">I", len(dados)) + tipo + dados + struct.pack(">I", zlib.crc32(tipo + dados) & 0xFFFFFFFF)

    cabecalho = struct.pack(">IIBBBBB", largura, altura, 8, 0, 0, 0, 0)
    imagem = zlib.compress((b"\x00" + linha) * altura, 9)
    return b"\x89PNG\r\n\x1a\n" + bloco(b"IHDR", cabecalho) + bloco(b"IDAT", imagem) + bloco(b"IEND", b"")


def barras_png(codigo: str) -> tuple[bytes, int]:
    barras, largura = barras_itf(codigo)
    linha = bytearray(b"\xff" * (largura * ESCALA_PNG))
    for x, w in barras:
        linha[x * ESCALA_PNG:(x + w) * ESCALA_PNG] = b"\x00" * (w * ESCALA_PNG)
    return png_cinza(largura * ESCALA_PNG, ALTURA_PNG, bytes(linha)), largura


def _qr(codigo: str):
    import segno

    if not codigo:
        raise ValueError("código vazio")
    return segno.make(codigo, error="m", micro=False, boost_error=False)


def pix_svg(codigo: str, largura: int = 220) -> str:
    qr = _qr(codigo)
    lado = qr.symbol_size(border=2)[0]
    return qr.svg_inline(scale=largura / lado, border=2, omitsize=False)


def pix_png(codigo: str, largura: int = 300) -> bytes:
    qr = _qr(codigo)
    lado = qr.symbol_size(border=2)[0]
    saida = io.BytesIO()
    qr.save(saida, kind="png", scale=max(1, round(largura / lado)), border=2)
    return saida.getvalue()


def _decodificar(imagem) -> list[str]:
    import zxingcpp

    return [item.text for item in zxingcpp.read_barcodes(imagem, formats=zxingcpp.BarcodeFormat.QRCode) if item.valid and item.text]


def ler_qrcodes(dados: bytes, tipo: str = "pdf", senhas: Sequence[str] = (), paginas: int = 5,
                resolucoes: Sequence[int] = (150, 300)) -> list[str]:
    from PIL import Image

    achados: list[str] = []

    def guardar(textos: list[str]) -> None:
        for texto in textos:
            if texto not in achados:
                achados.append(texto)

    if tipo != "pdf":
        guardar(_decodificar(Image.open(io.BytesIO(dados)).convert("RGB")))
        return achados
    import pymupdf

    documento = pymupdf.open(stream=dados, filetype="pdf")
    try:
        if documento.needs_pass and not any(documento.authenticate(senha) for senha in ("", *senhas)):
            return []
        for numero in range(min(documento.page_count, paginas)):
            pagina = documento.load_page(numero)
            for dpi in resolucoes:
                mapa = pagina.get_pixmap(dpi=dpi, alpha=False)
                textos = _decodificar(Image.frombytes("RGB", (mapa.width, mapa.height), mapa.samples))
                guardar(textos)
                if textos:
                    break
    finally:
        documento.close()
    return achados
