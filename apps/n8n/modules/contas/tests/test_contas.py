import base64
import importlib.util
import io
import json
import os
import socket
import struct
import subprocess
import sys
import threading
import time
import unittest
import urllib.request
import zlib
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import contas
import service

PIX = ("00020126580014br.gov.bcb.pix0136123e4567-e12b-12d1-a456-4266554400005204000053039865802BR5913Fulano de Tal"
       "6008BRASILIA62070503***63041D3D")
BARRAS = "23793381286000000000300000000400578390000010000"[:44]
IMAGENS = all(importlib.util.find_spec(name) for name in ("segno", "zxingcpp", "pymupdf", "PIL"))


def png_info(data: bytes) -> tuple[int, int, bytes]:
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    width, height = struct.unpack(">II", data[16:24])
    start = data.index(b"IDAT") + 4
    size = struct.unpack(">I", data[start - 8:start - 4])[0]
    return width, height, zlib.decompress(data[start:start + size])


class BarrasTest(unittest.TestCase):
    def test_itf(self) -> None:
        barras, largura = contas.barras_itf(BARRAS)
        self.assertEqual(barras[:2], [(10, 1), (12, 1)])
        self.assertEqual(largura, 10 + 4 + 22 * (2 * 3 + 3 * 1) * 2 + 5 + 10)
        with self.assertRaises(ValueError):
            contas.barras_itf("123")
        with self.assertRaises(ValueError):
            contas.barras_itf("12a4")

    def test_svg_and_png(self) -> None:
        svg = contas.barras_svg(BARRAS)
        largura = contas.barras_itf(BARRAS)[1]
        self.assertTrue(svg.startswith(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {largura} 50" width="{largura * 2}" height="100"'))
        self.assertEqual(svg.count("<rect "), len(contas.barras_itf(BARRAS)[0]) + 1)
        data, same = contas.barras_png(BARRAS)
        width, height, raw = png_info(data)
        self.assertEqual((width, height, same), (largura * 2, 100, largura))
        first = raw[1:width + 1]
        self.assertEqual(first[20:22], b"\x00\x00")
        self.assertEqual(first[:20], b"\xff" * 20)
        self.assertEqual(raw[width + 1:2 * width + 2], b"\x00" + first)


class StartTest(unittest.TestCase):
    def test_starts_like_the_container(self) -> None:
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        folder = Path(__file__).resolve().parents[1]
        process = subprocess.Popen([sys.executable, "-I", str(folder / "service.py")], env={**os.environ, "PORT": str(port)},
                                   cwd="/", stderr=subprocess.PIPE)
        self.addCleanup(process.kill)
        for _ in range(50):
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/v1/saude", timeout=1) as response:
                    self.assertEqual(json.loads(response.read()), {"ok": True})
                    break
            except OSError:
                if process.poll() is not None:
                    self.fail(process.stderr.read().decode())
                time.sleep(0.1)
        else:
            self.fail("o serviço não respondeu")
        process.terminate()
        self.assertEqual(process.wait(timeout=5), 0)


class ServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), service.Handler)
        self.addCleanup(self.server.server_close)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.shutdown)
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"

    def call(self, path: str, body: dict | None = None) -> tuple[int, dict]:
        data = None if body is None else json.dumps(body).encode()
        request = urllib.request.Request(self.base + path, data, {"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read())

    def test_routes(self) -> None:
        self.assertEqual(self.call("/v1/saude"), (200, {"ok": True}))
        self.assertEqual(self.call("/v1/nada")[0], 404)
        code, body = self.call("/v1/barras", {"barras": BARRAS})
        self.assertEqual((code, body["largura"]), (200, contas.barras_itf(BARRAS)[1]))
        self.assertTrue(body["svg"].startswith("<svg"))
        code, body = self.call("/v1/barras", {"barras": BARRAS, "formato": "png"})
        self.assertEqual(png_info(base64.b64decode(body["png"]))[1], 100)
        self.assertEqual(self.call("/v1/barras", {"barras": "1"})[0], 400)
        self.assertEqual(self.call("/v1/qrcodes", {"arquivo": "não é base64!"}), (400, {"erro": "arquivo tem de vir em base64"}))

    @unittest.skipUnless(IMAGENS, "bibliotecas da imagem do módulo (roda dentro dela)")
    def test_pix_and_qrcodes_round_trip(self) -> None:
        import pymupdf

        code, body = self.call("/v1/pix", {"codigo": PIX, "formato": "png"})
        imagem = base64.b64decode(body["png"])
        self.assertEqual(code, 200)
        self.assertEqual(contas.ler_qrcodes(imagem, "imagem"), [PIX])
        svg = self.call("/v1/pix", {"codigo": PIX})[1]["svg"]
        self.assertIn('width="220', svg)
        documento = pymupdf.open()
        pagina = documento.new_page()
        pagina.insert_text((72, 72), "Boleto de teste")
        pagina.insert_image(pymupdf.Rect(72, 100, 272, 300), stream=imagem)
        aberto = documento.tobytes()
        trancado = documento.tobytes(encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="1234", owner_pw="dono")
        arquivo = base64.b64encode(aberto).decode()
        self.assertEqual(self.call("/v1/qrcodes", {"arquivo": arquivo})[1], {"codigos": [PIX]})
        arquivo = base64.b64encode(trancado).decode()
        self.assertEqual(self.call("/v1/qrcodes", {"arquivo": arquivo})[1], {"codigos": []})
        self.assertEqual(self.call("/v1/qrcodes", {"arquivo": arquivo, "senhas": ["errada", "1234"]})[1], {"codigos": [PIX]})
        imagem_b64 = base64.b64encode(imagem).decode()
        self.assertEqual(self.call("/v1/qrcodes", {"arquivo": imagem_b64, "tipo": "imagem"})[1], {"codigos": [PIX]})
        self.assertIn("erro", self.call("/v1/qrcodes", {"arquivo": base64.b64encode(b"lixo").decode()})[1])


if __name__ == "__main__":
    unittest.main()
