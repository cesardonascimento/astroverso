# Módulos do n8n

Cada pasta aqui é um **módulo**: uma API pequena em Python que as rotinas do n8n chamam pelo nó **HTTP Request**,
para o que não cabe bem num nó Code (ler PDFs e QR Codes, converter vídeo, regras longas). Não aparece no instalador:
a instalação do n8n sobe todos os módulos desta pasta, sem perguntar.

```
modules/<módulo>/
  Containerfile   a imagem do módulo: Python e as dependências dele, com as versões fixadas
  service.py      a API: rotas /v1/..., servidor HTTP da biblioteca padrão
  tests/          unittest (rodam na máquina; o que depende das bibliotecas da imagem roda dentro dela)
  README.md       as rotas: o que recebem e o que devolvem
```

## O contrato

- **Nome:** letras minúsculas, números e `-` (o nome da pasta). Vira o container `astroverso-n8n-<módulo>`, na rede
  `astroverso`, sem porta na máquina e sem endereço no Caddy: só o n8n (e os outros containers da rede) o alcança, em
  `http://astroverso-n8n-<módulo>:8080`.
- **Porta 8080** (também na variável `PORT`) e a rota **`GET /v1/saude`**, que responde 200 quando o módulo está pronto:
  é a verificação do container e da verificação de hora em hora.
- **Rotas versionadas:** `/v1/...`. Uma mudança incompatível vira `/v2/...`, e a `/v1` continua respondendo até as
  rotinas migrarem: nenhuma rotina quebra em silêncio.
- **Arquivos** (PDF, imagem, vídeo) chegam pelo corpo da requisição (o HTTP Request do n8n manda o binário sem código),
  e a resposta é JSON.
- **Parar no SIGTERM:** no container, o Python é o processo 1 e ignora o SIGTERM sem um tratador; sem ele, cada
  parada espera 10 s e termina à força (o esqueleto já trata).
- **Sem segredos no módulo:** credenciais (ex.: chave de uma API externa) ficam no n8n e vão na requisição, quando
  preciso.
- **Dependências** só dentro da imagem (`pip install` com versões fixadas no `Containerfile`): é a exceção à regra "só
  biblioteca padrão", que vale para o código que roda na máquina.

A imagem é `localhost/astroverso-n8n-<módulo>:<resumo>`, com um resumo (hash) dos arquivos do módulo: mudou um arquivo,
a próxima instalação do n8n monta a imagem de novo e troca o container. Um módulo que sai desta pasta tem o container
removido na instalação seguinte.

## Esqueleto

```dockerfile
FROM docker.io/library/python:3.13-slim
WORKDIR /app
COPY service.py .
USER 1000
CMD ["python3", "-I", "service.py"]
```

```python
import json
import os
import signal
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path == "/v1/saude":
            self.answer(200, {"ok": True})
        else:
            self.answer(404, {"erro": "rota desconhecida"})

    def answer(self, code: int, body: dict) -> None:
        data = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
ThreadingHTTPServer(("0.0.0.0", int(os.environ.get("PORT", "8080"))), Handler).serve_forever()
```
