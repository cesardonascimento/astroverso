# discord

O bot do Discord do Astroverso (o `astro`), num servidor do Discord dedicado ao Astroverso, com um canal para cada
app. Os apps de todas as máquinas da casa mandam avisos pelo `kit.discord`, num padrão único, e o comando `/astro`
roda ações deles.

Uma máquina **roda o bot**: container com o bot e a API, publicada em `https://discord.<domínio>` pelo Caddy do
`network`. As outras **usam o bot**: instalam o mesmo app, escolhem "Usa o bot que roda em outra máquina" e colam o
endereço e a chave de cliente.

## O que a instalação faz

Uma explicação curta aparece antes de cada etapa. Os passos no site do Discord aparecem como link para
[`docs/discord.md`](docs/discord.md).

**Na máquina que roda o bot:**

1. Pergunta o domínio (só na primeira vez de qualquer app).
2. Pede o token do bot (com o link para o passo a passo) e o confere no Discord.
3. Confere se a leitura de mensagens está ligada no portal e avisa se não estiver.
4. Mostra o convite do bot e espera ele aparecer num servidor. Com mais de um, pergunta qual usar.
5. Autoriza o dono do servidor e pergunta se mais alguém deve ser autorizado.
6. Cria a chave de cliente desta máquina, troca a foto do bot pelo logo do Astroverso, monta a imagem e sobe o
   container. Na primeira conexão, o bot cria a categoria **Astroverso** e os canais `#astro` e `#sistema`.
7. Publica `discord.<domínio>` no Caddy, liga esta máquina ao bot e manda uma mensagem de teste para `#discord`.

**Nas outras máquinas:** pergunta o endereço do bot e a chave de cliente, confere no bot e manda uma mensagem de
teste.

O "Reinstalar" pode reaproveitar as respostas salvas.

## Mudanças na máquina

| Mudança | Por quê |
|---|---|
| Podman instalado e *linger* ligado para o usuário (só na máquina do bot) | O bot roda em container, como serviço do usuário, e precisa subir no boot sem ninguém logado |
| Imagem local `localhost/astroverso-discord:<versão>` (Python oficial + `discord.py`, versões fixadas), montada na instalação; versões antigas são apagadas | O bot e a API rodam com a biblioteca `discord.py`, que fica só dentro do container |
| Container `astroverso-discord` na rede `astroverso`, sem porta aberta na máquina, unidade Quadlet | O bot conectado ao Discord e a API dos clientes (porta 8080 só dentro da rede dos containers, alcançada pelo Caddy) |
| `~/.astroverso/routes/discord.json` (`discord.<domínio>` → `http://astroverso-discord:8080`) | O Caddy do `network` publica a API com HTTPS para os clientes da casa (e de fora, pelo Tailscale) |
| `~/.astroverso/discord/.env` (`600`): `MODE`, e na máquina do bot `DISCORD_TOKEN`, `DISCORD_GUILD`, `DISCORD_USERS`, `DISCORD_CLIENTS` (nome e resumo SHA-256 de cada chave), `DISCORD_MESSAGE_CONTENT` | As respostas da instalação; o container lê o mesmo arquivo como `EnvironmentFile` |
| `~/.astroverso/discord/clients/<cliente>.key` (`600`) | A chave de cada cliente; o bot só guarda o resumo |
| `~/.astroverso/discord/data/` | Os manifestos dos clientes e os IDs dos canais criados |
| `~/.astroverso/discord.env` (`600`, `DISCORD_URL`, `DISCORD_KEY`) | Liga esta máquina ao bot: é o que o `kit.discord` de todos os apps usa para mandar avisos |
| Foto do bot trocada pelo logo do Astroverso | Para os avisos aparecerem com a marca do projeto |
| Unidade do usuário `astroverso-discord-agent.service` (em toda máquina com o app) | O agente: publica no bot os comandos desta máquina e roda os que forem pedidos no `/astro` (`astroverso discord action agent`) |

## Fora da máquina (passos seus)

| Passo | Por quê | Como fazer |
|---|---|---|
| Criar a aplicação e o bot no portal do Discord, com o bot privado, e copiar o token | É a conta do Discord que o Astroverso usa | [discord.md](docs/discord.md#criar-o-bot) |
| Ligar o **Message Content Intent** | Sem ele, o bot não lê as mensagens dos canais que os clientes escutam | [discord.md](docs/discord.md#ligar-a-leitura-de-mensagens) |
| Convidar o bot para o servidor do Astroverso | O bot só cria canais e manda avisos num servidor em que está | [discord.md](docs/discord.md#convidar-o-bot) |
| Copiar o ID de quem mais vai usar o bot (opcional) | Só usuários autorizados usam comandos, botões e mensagens | [discord.md](docs/discord.md#copiar-ids) |

## Ações

| Ação | O que faz |
|---|---|
| Resumo do Discord | Container, conexão com o Discord, endereço da API, leitura de mensagens, usuários autorizados, clientes e quando cada um apareceu; e se esta máquina está ligada ao bot |
| Mensagem de teste | Manda um aviso de teste para `#discord` pelo `kit.discord` |
| Mostrar a chave de um cliente | Endereço e chave, para colar na outra máquina (só na máquina do bot) |
| Adicionar um cliente | Cria a chave de uma máquina ou projeto novo e reinicia o bot (só na máquina do bot) |

## Comandos do `/astro`

Toda máquina com o app (servidor ou cliente) roda o **agente**, que publica no bot as ações dos apps instalados
marcadas com `remote=True` (veja `apps/README.md`) e roda as que forem pedidas. No Discord, elas aparecem como
`/astro command:<app>:<ação>` (com autocompletar), no painel (`/astro command:panel`) e na ajuda
(`/astro command:help`). Hoje:

| Comando | O que faz |
|---|---|
| `network:summary` | Resumo da rede |
| `network:watch` | Verifica a rede agora (e avisa no Discord) |
| `network:reload` | Recarrega os endereços do Caddy |
| `discord:summary` | Resumo do Discord |
| `discord:test` | Mensagem de teste |

O agente roda `astroverso <app> action <ação>` sem terminal, com até 13 minutos, e devolve a saída (sem cores) ao
Discord, com ✅ ou ❌. Um app instalado em mais de uma máquina publica o mesmo comando em cada uma: ele fica com a
primeira que publicou. O catálogo é atualizado a cada 5 minutos.

## Avisos dos apps (`kit.discord`)

```python
from kit import discord

discord.notify("network", "aviso", "Cadeado vence em 10 dias", "A renovação automática falhou.", {"Validade": "02/12"})
```

O aviso vai para o canal `#<app>` (criado no primeiro aviso), num quadro com o padrão do Astroverso:

| Nível | Visual | Notificação no celular |
|---|---|---|
| `info` | ℹ️ violeta | silenciosa |
| `sucesso` | ✅ verde | silenciosa |
| `aviso` | ⚠️ âmbar | sim |
| `erro` | ❌ vermelho | sim, com menção ao dono do servidor |

Com `actions=[("Resumo da rede", "network:summary")]`, o aviso traz botões que rodam esses comandos.

Sem o Discord configurado na máquina, o `notify` não faz nada e devolve `False`. Se o bot não responder, ele mostra
um aviso na tela e segue: um aviso nunca derruba o app.

## API (v1)

Contrato com os clientes, inclusive os de fora do monorepo: campos novos são opcionais; para quebrar, `/v2`. Toda
chamada, menos `/v1/saude`, leva `Authorization: Bearer <chave do cliente>`. Corpo e respostas em JSON.

| Chamada | O que faz |
|---|---|
| `GET /v1/saude` | `{"ok": <conectado ao Discord>, "clientes": {<nome>: {"visto_ha_s"}}}` |
| `GET /v1/eu` | `{"cliente": <nome>}`: confere a chave sem efeito colateral |
| `PUT /v1/cliente` | Publica o manifesto do cliente (abaixo). Responde `{"canais": {<nome>: <id>}, "comandos": n}` |
| `GET /v1/eventos?espera=25` | Espera até `espera` segundos (máx. 50) e devolve `{"eventos": [...]}` |
| `POST /v1/eventos/<id>/resposta` | Responde a um evento |
| `POST /v1/mensagens` | Manda uma mensagem ou um aviso. JSON, ou `multipart/form-data` com `dados` (o JSON) e `arquivo`. Responde `{"mensagem_id", "canal_id"}` |
| `POST /v1/reacoes` | `{"canal_id", "mensagem_id", "emoji"}` |

### Manifesto

```json
{
  "catalogo": [{"id": "network:summary", "descricao": "Rede: resumo", "confirmar": false, "tipo": "host"}],
  "ajuda": [{"grupo": "Rede", "nome": "Rede: resumo", "descricao": "...", "quando": "quando quiser", "comando": "network:summary"}],
  "canais": [{"nome": "dados", "escrita": false, "escuta": false}],
  "botoes": [{"padrao": "^cortes:[a-z_]+:\\d+$", "texto": {"padrao": "^cortes:(replan|revise):\\d+$", "titulo": "Pedido", "rotulo": "O que você quer?", "dica": "..."}}]
}
```

- **`catalogo`:** os comandos do `/astro` deste cliente (`confirmar` pede confirmação por botão; `tipo: container`
  vai para o menu do painel). Um comando com o mesmo `id` de outro cliente fica com quem publicou primeiro.
- **`ajuda`:** as linhas do `/astro command:help`.
- **`canais`:** criados (ou ajustados) na categoria **Astroverso**. `escrita: false` deixa só o bot escrever;
  `escuta: true` entrega ao cliente as mensagens dos usuários autorizados nesse canal.
- **`botoes`:** os `custom_id` dos botões que o cliente manda nas mensagens (expressão regular que precisa casar
  com o `custom_id` inteiro). Com `texto`, um clique num botão que casa com `texto.padrao` abre uma caixa de texto
  antes de virar evento.

### Eventos

| `tipo` | Campos | Resposta esperada |
|---|---|---|
| `comando` | `acao`, `arg`, `usuario` | `{"ok", "saida", "botoes"?}`; o bot mostra ✅/❌ e a saída. Até 14 min |
| `botao` | `custom_id`, `texto` (da caixa de texto, ou vazio), `usuario`, `canal_id`, `mensagem_id` | Uma mensagem (abaixo), mostrada a quem clicou. Até 14 min |
| `mensagem` | `canal`, `canal_id`, `mensagem_id`, `texto`, `usuario`, `responde_a` (`mensagem_id`, `do_bot`, `texto`, `quadros` [`titulo`, `rodape`], `anexos`) ou `null` | Uma mensagem, em resposta à do usuário (opcional). Até 2 min |

`usuario` é `{"id", "nome", "exibicao"}`. Um evento sem resposta no prazo é descartado. Reiniciar o bot perde os
eventos pendentes.

### Mensagens

Aviso no padrão do Astroverso (o que o `kit.discord.notify` manda):

```json
{"app": "network", "nivel": "aviso", "titulo": "Cadeado vence em 10 dias", "texto": "...", "campos": {"Validade": "02/12"}}
```

Com `nivel`, o canal é `#<app>` (ou `#sistema`, sem `app`), a menos que venha `canal`. Mensagem livre:

```json
{"canal": "dados", "canal_id": "...", "responde_a": "<mensagem_id>", "texto": "até 2000 caracteres",
 "quadro": {"titulo", "descricao", "cor", "rodape", "url"}, "silencioso": false,
 "botoes": [{"rotulo": "Rede: resumo", "acao": "network:summary", "arg": ""},
            {"rotulo": "Aprovar", "custom_id": "cortes:approve:12", "estilo": "success"}],
 "arquivo_nome": "corte.mp4"}
```

O canal vem de `canal` (nome de um canal conhecido) ou `canal_id` (um desses canais); sem eles, ou com um
desconhecido, `#astro`. Um botão com `acao` roda aquele comando do `/astro`; um com `custom_id` precisa casar com um
`padrao` do próprio cliente (`estilo`: `primary`, `success`, `danger`, `secondary`).

## Remover

Desliga e apaga o agente. Na máquina do bot: remove o container e as imagens, retira o endereço do Caddy e apaga `~/.astroverso/discord`
(token, chaves, manifestos). Em qualquer máquina: apaga `~/.astroverso/discord.env`. O servidor do Discord, os
canais e a aplicação no portal ficam: apague no Discord, se quiser.

## Backup

O `.env`, as chaves dos clientes e o `discord.env`. Ao restaurar, a instalação roda com as respostas salvas e os
clientes das outras máquinas continuam valendo.

Testes: `python3 -m unittest discover -s apps/discord/tests`.
