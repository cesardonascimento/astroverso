# apps

Cada pasta é um serviço autônomo do Astroverso, reconhecido pelo gerenciador (`astroverso`) quando tem um `app.py`.

- Não conhece nenhum outro app e não depende de ordem de instalação.
- Usa só o código de `packages/`.
- Instala as próprias dependências pela camada `kit.distro`.
- Guarda o que gera em `~/.astroverso/<app>`.
- Containers pelo `kit.container` (Quadlet), na rede `astroverso`, com o nome `astroverso-<app>[-<parte>]`.
- Endereço `https://<serviço>.<domínio>` pelo `kit.routes` (`publish` na instalação, `withdraw` no `remove`).

Cada app tem um `README.md` com a tabela **Mudança | Por quê** de tudo que o instalador muda na máquina e dos
passos fora dela, sempre atualizada junto com o instalador.

**Mudanças perguntadas e reversíveis.** Toda mudança que o app faz no sistema (firewall, arquivos em `/etc`,
unidades do systemd, ajustes do kernel...), por menor que seja, é um `kit.changes.Change`: perguntada na instalação
(padrão sim), listada e desfeita ou refeita na ação **Mudanças no sistema**, e desfeita no `remove`. As essenciais
para o app funcionar levam `danger=True` e aparecem em vermelho com ⚠. Os componentes do próprio app (os containers,
o estado em `~/.astroverso/<app>`) não são mudanças: são o app.

**Backup: cada app manda o seu.** Todo app põe `kit.backup.change(APP)` nas mudanças perguntadas e ganha as ações
`Action("backup-now", "Fazer backup agora", lambda: kit_backup.run_backup(APP, backup), remote=True)` e
`Action("restore-version", "Restaurar uma versão", lambda: kit_backup.restore(APP, backup, restore))`.

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
| `ORDER` | não | Posição na ordem recomendada de instalação (menor primeiro; sem ela, no fim): só uma dica do menu, o app continua instalando sozinho em qualquer ordem |
| `status() -> bool` | sim | Diz se o app está instalado |
| `install()` | sim | Pergunta, instala e sobe o app; também é o "Reinstalar" |
| `remove()` | sim | Desfaz tudo o que o app criou, sem falhar no que já não existe |
| `backup(pasta)` / `restore(pasta)` | sim | Copia a configuração para a pasta e a traz de volta (mandados ao servidor pelo `kit.backup`) |
| `actions() -> list[Action]` | não | Ações de pós-configuração: `Action(id, rótulo, função, remote=, confirm=, menu=)` do `kit.app` |

**Ações pelo Discord.** Uma ação com `remote=True` vira o comando `/astro <app>:<id>` no Discord (com `confirm=True`,
pede confirmação por botão antes). Ela roda sem terminal (`astroverso <app> action <id>`, pelo agente do app
`discord`), então não pode perguntar nada; a saída vai para o Discord. `menu=False` esconde a ação do menu do
gerenciador (ex.: o próprio agente). Os avisos do `kit.discord.notify(..., actions=[("Rótulo", "<app>:<id>")])`
podem trazer botões que rodam essas ações.

A pasta do app é carregada como pacote: o `app.py` pode importar os outros arquivos dela (`from . import tailscale`).
Testes de um app: `python3 -m unittest discover -s apps/<app>/tests`.

O nome do app é o da pasta. O gerenciador troca o prefixo das mensagens para `[<app>]` enquanto roda o app.
Um `ui.fail` ou uma exceção encerram só aquela operação: o erro aparece e o gerenciador segue. Um app sem
alguma função obrigatória aparece como "app inválido" e fica de fora.
