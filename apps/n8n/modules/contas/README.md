# Módulo contas

A API das rotinas de contas a pagar do n8n: lê os QR Codes do Pix em PDFs e imagens e desenha o QR Code do Pix e o
código de barras dos boletos. Container `astroverso-n8n-contas`, em `http://astroverso-n8n-contas:8080` (só na rede
dos containers). Imagem com PyMuPDF (abre e desenha os PDFs, com senha), Pillow, zxing-cpp (lê os QR Codes) e segno
(desenha o QR Code), versões fixadas no `Containerfile`.

## Rotas

Todas recebem e devolvem JSON. Arquivos vão e voltam em base64.

| Rota | Recebe | Devolve |
|---|---|---|
| `GET /v1/saude` | — | `{"ok": true}` |
| `POST /v1/qrcodes` | `arquivo` (PDF ou imagem em base64), `tipo` (`pdf` ou `imagem`), `senhas` (lista, para PDF trancado), `paginas` (padrão 5) | `{"codigos": [...]}`: o texto de cada QR Code válido (PDF: cada página a 150 dpi e, sem achar, a 300 dpi). Arquivo que não abre: `codigos` vazio e `erro` |
| `POST /v1/pix` | `codigo`, `formato` (`svg`, padrão, ou `png`), `largura` (padrão 220 no SVG e 300 no PNG) | `{"svg": "..."}` ou `{"png": "<base64>"}`: QR Code com correção M e margem 2 |
| `POST /v1/barras` | `barras` (os 44 dígitos do código de barras), `formato` (`svg` ou `png`) | `{"svg" ou "png", "largura"}`: Intercalado 2 de 5, igual ao desenho das rotinas antigas (SVG 2× a largura, 100 px de altura; PNG em escala 2) |

Pedido inválido: 400 com `{"erro": "..."}`.

## Nas rotinas

Os nós Code chamam o módulo pelo `this.helpers.httpRequest`, com o endereço no nó **⚙️ Configuração**
(`config.modulo_contas`):

```js
const MODULO = $('⚙️ Configuração').first().json.config.modulo_contas;
const chamarModulo = async (rota, corpo) => this.helpers.httpRequest({ method: 'POST', url: `${MODULO}${rota}`, body: corpo, json: true, timeout: 120000 });
const lerQrCodes = async (buffer, opcoes) => (await chamarModulo('/v1/qrcodes', { arquivo: buffer.toString('base64'), ...opcoes })).codigos || [];
```

As rotinas de contas (`Contas: leitura` e `Contas: notificação mensal`) ficam só no n8n, não aqui: guardam dados
pessoais (destinatários, pastas, senhas dos PDFs) no nó **⚙️ Configuração**. Elas usam:

| Credencial | Tipo | Origem |
|---|---|---|
| Astroverso: caixa inbox (IMAP) | IMAP | Conexão do Astroverso (app `mail`) |
| Astroverso: envio de e-mail | Header Auth | Conexão do Astroverso (app `mail`) |
| Astroverso: Discord | Header Auth | Conexão do Astroverso (app `discord`) |
| Astroverso: chamadas do Astroverso | Header Auth | Conexão do Astroverso (o webhook da notificação mensal) |
| **Astroverso: API da Anthropic** | Header Auth (`x-api-key` = a chave) | Criada por você no n8n |
| **Astroverso: Nextcloud** | Nextcloud (`https://nextcloud.<domínio>/remote.php/dav/files/<usuário>`, sem barra no fim, e uma senha de app do Nextcloud) | Criada por você no n8n |

Crie as duas últimas **antes** de importar as rotinas, com esses nomes exatos: a importação liga cada nó à credencial
de mesmo nome e tipo.

Testes: `python3 -m unittest discover -s apps/n8n/modules/contas/tests` (os que dependem das bibliotecas da imagem
rodam dentro dela, com a pasta montada: `podman run --rm -v ./tests:/app/tests:ro,Z --entrypoint python3 <imagem> -I -m unittest discover -s /app/tests`).
