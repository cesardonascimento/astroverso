# apps

Cada pasta é um serviço autônomo do Astroverso, reconhecido pelo gerenciador (`astroverso`) quando tem um `app.py`.

- Não conhece nenhum outro app e não depende de ordem de instalação.
- Usa só o código de `packages/`.
- Instala as próprias dependências pela camada `kit.distro`.
- Guarda o que gera em `~/.astroverso/<app>`.
- Containers pelo `kit.container` (Quadlet), na rede `astroverso`, com o nome `astroverso-<app>[-<parte>]`.

Cada app tem um `README.md` com a tabela **Mudança | Por quê** de tudo que o instalador muda na máquina e dos
passos fora dela, sempre atualizada junto com o instalador.

**Passos em plataformas de terceiros** (Tailscale, Cloudflare, Discord, roteador, firewall de outro computador)
ficam em `apps/<app>/docs/<plataforma>.md`, com o passo a passo completo, e uma seção para cada passo. Na etapa
que precisa de um deles, o instalador mostra só uma frase curta (o que fazer, com os valores desta máquina) e o
link do doc no GitHub, montado pelo `kit.docs.link`:

```python
DOCS = Path(__file__).with_name("docs")
ui.note(f"Falta o Split DNS no painel do Tailscale ({domain} → {address}).")
ui.link("passo a passo", docs.link(DOCS / "tailscale.md", "split-dns"))
```

O que explica o próprio Astroverso (o que é o AdGuard, para que serve uma pergunta) continua como `ui.note` na
tela. Os docs usam só marcadores (`<ip>`, `<domínio>`, `<nome-da-máquina>`). Um teste do app confere que toda âncora
usada no código existe no doc.

## Contrato do `app.py`

Funções simples no módulo (o `Protocol` `kit.app.App` documenta os tipos):

| Nome | Obrigatório | O que faz |
|---|---|---|
| `DESCRIPTION` | sim | Uma linha, mostrada ao lado do nome nos menus |
| `status() -> bool` | sim | Diz se o app está instalado |
| `install()` | sim | Pergunta, instala e sobe o app; também é o "Reinstalar" |
| `remove()` | sim | Desfaz tudo o que o app criou, sem falhar no que já não existe |
| `backup(pasta)` / `restore(pasta)` | sim | Copia a configuração para a pasta e a traz de volta (usados pelo pacote `backup`) |
| `actions() -> list[Action]` | não | Ações de pós-configuração: `Action(id, rótulo, função)` do `kit.app` |

A pasta do app é carregada como pacote: o `app.py` pode importar os outros arquivos dela (`from . import tailscale`).
Testes de um app: `python3 -m unittest discover -s apps/<app>/tests`.

O nome do app é o da pasta. O gerenciador troca o prefixo das mensagens para `[<app>]` enquanto roda o app.
Um `ui.fail` ou uma exceção encerram só aquela operação: o erro aparece e o gerenciador segue. Um app sem
alguma função obrigatória aparece como "app inválido" e fica de fora.
