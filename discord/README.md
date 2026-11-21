# discord

Bot do Discord que manda os avisos do servidor em canais por assunto e aceita comandos `/astro`. O bot roda num container
sem acesso à máquina: ele só troca arquivos numa pasta de fila com um executor no host, que roda apenas as
ações de uma lista.

```bash
./project.sh install           # perguntas, imagem, executor de comandos, container e mensagem de teste
./project.sh remove           # desfaz tudo o que o projeto criou (usado pelo Implodir Astroverso)
```

## Perguntas da instalação

| Pergunta | Padrão |
|---|---|
| Token do bot | (secreto, conferido na API do Discord) |
| ID do canal principal (comandos) | (o bot precisa enxergar o canal; o assistente mostra o link de convite) |
| IDs dos usuários autorizados | separados por espaço |

O link de convite pede os escopos `bot` e `applications.commands` e as permissões de ver canais, enviar mensagens,
incorporar links, ler o histórico, gerenciar canais e permissões e as de tópicos (`378225642512`): as de gerenciar
servem só para criar os canais de avisos e deixá-los só de leitura. O bot não lê as mensagens do servidor (sem
intents privilegiadas). Para um bot já convidado, abrir o link de novo atualiza as permissões.

## Canais

| Canal | O que recebe | Quem escreve |
|---|---|---|
| principal (ex.: `#astro`) | comandos `/astro`, botões, respostas, `help`, mensagem de teste e avisos sem canal próprio | você e o bot |
| `#financeiro` | rotinas de contas a pagar (n8n: `canal_discord` no `⚙️ Configuração` de cada rotina) | só o bot |
| `#dados` | `rclone`: sincronização com a nuvem, backup diário e backup das configurações | só o bot |
| `#sistema` | discos da máquina (`astroverso-disk-check`), busca de e-mails do `mailserver` e, no futuro, outros avisos da máquina | só o bot |

A instalação (`channels.py`, token pela entrada padrão) descobre o servidor pelo canal principal, procura os
outros pelo nome e cria os que faltam na mesma categoria dele. Em todos eles, `@everyone` não pode enviar
mensagens, criar tópicos nem escrever em tópicos, e o bot pode ver, enviar, incorporar links e ler o histórico
(sobrescritas de permissão, refeitas a cada instalação). Os IDs ficam em `DISCORD_CHANNELS`
(`financeiro=<id> dados=<id> sistema=<id>`). Sem permissão (HTTP 403), a instalação mostra o link de convite de
novo; dá também para criar os canais à mão, com esses nomes, e rodar a instalação outra vez. Os botões dos avisos
funcionam nos canais só de leitura.

Cada aviso leva o canal na fila (`canal`, de `NOTIFY_CHANNEL` do projeto que avisa; sem ele, `astroverso`). O bot
entrega no canal de `DISCORD_CHANNELS` com esse nome; sem ele (ou se o canal sumiu), no principal.

## Foto do bot

A instalação troca a foto do bot por `logo/icone.png` (`PATCH users/@me`, token pelo cabeçalho na entrada
padrão). O hash da imagem fica em `~/.astroverso/discord/.avatar`: só troca de novo quando a logo muda. O Discord limita
trocas seguidas; se recusar (HTTP 429), a próxima instalação tenta de novo. O ícone do aplicativo no portal do
Discord não muda pela API: troque à mão em General Information → App Icon, se quiser.

## Como funciona

```
Discord ⇄ astroverso-discord (bot) ⇄ ~/.astroverso/discord/fila ⇄ astroverso-discord-runner (host) → <projeto>/project.sh remote
```

| Pasta ou arquivo | Quem grava | Conteúdo |
|---|---|---|
| `fila/catalogo.json` | executor | Lista de ações permitidas (o autocompletar do `/astro` vem daqui) |
| `fila/pedidos/<id>.json` | bot | Ação, argumento e quem pediu |
| `fila/respostas/<id>.json` | executor | Resultado (o bot responde no Discord e apaga; sobras somem depois de 1 dia) |
| `fila/saida/<n>.json` | `notify_send` / `notify_info` (qualquer projeto) | Aviso, canal e botões, enviados pelo bot ao canal do assunto; com `silencioso`, sai como mensagem silenciosa do Discord (sem notificar o celular) |
| `fila/tmp/` | todos | Arquivos em escrita: só entram nas outras pastas prontos (`mv`) |

1. `/astro command:<projeto>:<ação> argument:<opcional>` ou um botão de um aviso. Os nomes dos comandos são
   sempre em inglês.
2. O bot confere se quem pediu está em `DISCORD_USERS`. Ações marcadas pedem confirmação (botões Confirmar e
   Cancelar).
3. O bot grava o pedido. O `astroverso-discord-runner.path` (systemd do usuário) acorda o executor (`runner.sh run`).
4. O executor refaz o catálogo, recusa o que não está nele (ou argumento fora de `[A-Za-z0-9._-]`, até 64
   caracteres), roda a ação com até 10 minutos de limite e grava a resposta.
5. O bot responde no Discord (até 14 minutos de espera). Cada pedido fica no journal do executor e no canal.

## Comandos

| Comando | Confirmação | O que faz |
|---|---|---|
| `help` | | Lista as operações do Astroverso por grupo (nome, o que é, quando roda e o comando), em uma ou mais mensagens só para quem pediu |
| `machine:status` | | Máquina: estado. Containers do Astroverso, espaço nos discos, kernel novo pendente e próximos agendamentos |
| `machine:wake [nome]` | | Máquina: ligar. Manda o pacote mágico (Wake-on-LAN) para um computador cadastrado em Administração → Máquinas da rede e espera até 3 minutos ele responder. Sem o nome, responde com um botão por máquina (`astro\|run\|machine:wake\|<nome>`). Aparece no catálogo e na ajuda só com alguma máquina cadastrada |
| `<projeto>:start` | | `podman start` nos containers `astroverso-<projeto>*` |
| `<projeto>:stop` | sim | `podman stop`. Com `restart: always`, o container fica parado até o `start`, mesmo depois de reiniciar a máquina |
| `<projeto>:restart` | sim | `podman restart` |
| ações dos projetos | conforme o projeto | `remote-actions` de cada projeto, com o prefixo do projeto (`<projeto>:<ação>`) ou com um nome próprio, como `backup:cloud` (rclone); ver o README de cada um |

O catálogo (`fila/catalogo.json`) guarda, para cada comando, o projeto que o atende, a ação e o tipo (`host`,
`container` ou `remote`). A ajuda (`fila/ajuda.json`) junta as linhas do comando opcional `help` de cada projeto
(grupo, nome, o que é, quando, comando, ordem) com as da máquina e dos serviços. As duas são refeitas pelo
executor a cada rodada.

O próprio bot não aparece em `start`/`stop`/`restart`: parado, ele não voltaria pelo Discord.

## Ações (Gerenciar Astroverso → discord)

| Ação | O que faz |
|---|---|
| Enviar uma mensagem de teste | Aviso com o botão "Máquina: estado", pelo caminho completo (fila, bot, executor) |
| Listar os comandos disponíveis no Discord | Refaz e mostra o catálogo |

## Arquivos gerados

| Caminho | Conteúdo |
|---|---|
| `~/.astroverso/discord/.env` | `DISCORD_TOKEN`, `DISCORD_CHANNEL`, `DISCORD_USERS` (`600`) |
| `~/.astroverso/discord/fila/` | A fila (fora do backup das configurações) |
| `~/.config/systemd/user/astroverso-discord-runner.{path,service}` | O executor de comandos |

Logs: `podman logs -f astroverso-discord` (bot) e `journalctl --user -fu astroverso-discord-runner` (comandos executados).

## Remoção

`remove` tira o container, as imagens e o executor de comandos (`astroverso-discord-runner`), e apaga
`~/.astroverso/discord` (token, canal e fila).
