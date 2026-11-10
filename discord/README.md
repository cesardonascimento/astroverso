# discord

Bot do Discord que manda os avisos do servidor num canal e aceita comandos `/astro`. O bot roda num container
sem acesso à máquina: ele só troca arquivos numa pasta de fila com um executor no host, que roda apenas as
ações de uma lista.

```bash
./project.sh install           # perguntas, imagem, executor de comandos, container e mensagem de teste
./project.sh remove           # desfaz tudo o que o projeto criou (usado pelo Implodir Astro)
```

## Perguntas da instalação

| Pergunta | Padrão |
|---|---|
| Token do bot | (secreto, conferido na API do Discord) |
| ID do canal dos avisos | (o bot precisa enxergar o canal; o assistente mostra o link de convite) |
| IDs dos usuários autorizados | separados por espaço |

O link de convite pede os escopos `bot` e `applications.commands` e só as permissões de ver o canal, enviar mensagens, incorporar
links e ler o histórico (`84992`). O bot não lê as mensagens do servidor (sem intents privilegiadas).

## Como funciona

```
Discord ⇄ astro-discord (bot) ⇄ ~/.astro/discord/fila ⇄ astro-discord-runner (host) → <projeto>/project.sh remote
```

| Pasta ou arquivo | Quem grava | Conteúdo |
|---|---|---|
| `fila/catalogo.json` | executor | Lista de ações permitidas (o autocompletar do `/astro` vem daqui) |
| `fila/pedidos/<id>.json` | bot | Ação, argumento e quem pediu |
| `fila/respostas/<id>.json` | executor | Resultado (o bot responde no Discord e apaga; sobras somem depois de 1 dia) |
| `fila/saida/<n>.json` | `notify_send` (qualquer projeto) | Aviso e botões, enviados pelo bot ao canal |
| `fila/tmp/` | todos | Arquivos em escrita: só entram nas outras pastas prontos (`mv`) |

1. `/astro command:<projeto>:<ação> argument:<opcional>` ou um botão de um aviso. Os nomes dos comandos são
   sempre em inglês.
2. O bot confere se quem pediu está em `DISCORD_USERS`. Ações marcadas pedem confirmação (botões Confirmar e
   Cancelar).
3. O bot grava o pedido. O `astro-discord-runner.path` (systemd do usuário) acorda o executor (`runner.sh run`).
4. O executor refaz o catálogo, recusa o que não está nele (ou argumento fora de `[A-Za-z0-9._-]`, até 64
   caracteres), roda a ação com até 10 minutos de limite e grava a resposta.
5. O bot responde no Discord (até 14 minutos de espera). Cada pedido fica no journal do executor e no canal.

## Comandos

| Comando | Confirmação | O que faz |
|---|---|---|
| `help` | | Lista os comandos |
| `host:status` | | Containers do astro, espaço nos discos, kernel novo pendente e próximos agendamentos |
| `<projeto>:start` | | `podman start` nos containers `astro-<projeto>*` |
| `<projeto>:stop` | sim | `podman stop`. Com `restart: always`, o container fica parado até o `start`, mesmo depois de reiniciar a máquina |
| `<projeto>:restart` | sim | `podman restart` |
| `<projeto>:<ação>` | conforme o projeto | Ações de `remote-actions` do projeto (ex.: `rclone:sync`; ver o README de cada um) |

O próprio bot não aparece em `start`/`stop`/`restart`: parado, ele não voltaria pelo Discord.

## Ações (Gerenciar Astro → discord)

| Ação | O que faz |
|---|---|
| Enviar uma mensagem de teste | Aviso com o botão "Estado da máquina", pelo caminho completo (fila, bot, executor) |
| Listar os comandos disponíveis no Discord | Refaz e mostra o catálogo |

## Arquivos gerados

| Caminho | Conteúdo |
|---|---|
| `~/.astro/discord/.env` | `DISCORD_TOKEN`, `DISCORD_CHANNEL`, `DISCORD_USERS` (`600`) |
| `~/.astro/discord/fila/` | A fila (fora do backup das configurações) |
| `~/.config/systemd/user/astro-discord-runner.{path,service}` | O executor de comandos |

Logs: `podman logs -f astro-discord` (bot) e `journalctl --user -fu astro-discord-runner` (comandos executados).

## Remoção

`remove` tira o container, as imagens e o executor de comandos (`astro-discord-runner`), e apaga
`~/.astro/discord` (token, canal e fila).
