# mailserver

Caixa de e-mail só de entrada, para automações. Os e-mails encaminhados para um endereço no seu domínio chegam
pela Cloudflare (Email Routing + Worker + KV) e são buscados pelo Astroverso para uma caixa IMAP local (Dovecot), lida
pelas automações e pelo app Mail do Nextcloud. Nenhuma porta fica aberta para a internet. A caixa não envia
e-mails, mas o mesmo Worker envia os e-mails das automações (pelo Email Routing, só para destinatários
cadastrados e confirmados).

```bash
./project.sh install           # perguntas, Cloudflare, container, busca periódica e conta no Nextcloud Mail
./project.sh fetch             # busca os e-mails agora (o mesmo que o timer faz)
./project.sh remove            # desfaz tudo o que o projeto criou (usado pelo Implodir Astroverso)
```

## Como funciona

```
seu e-mail (filtro com encaminhamento)
   ↓
inbox@<domínio>                  Cloudflare Email Routing (domínio sem outro e-mail)
   ↓
Worker astroverso-mailserver     confere o remetente e grava o e-mail bruto no KV astroverso-mailserver
   ↓  campainha conferida de 5 em 5 minutos, das 08:00 às 20:00 (astroverso-mailserver-fetch.timer)
project.sh fetch                 baixa cada e-mail, entrega com doveadm save e só então apaga do KV
   ↓
astroverso-mailserver (Dovecot)  usuário inbox, pastas INBOX e Quarentena
   ├─ automações (IMAP)
   └─ Nextcloud Mail ("Astro Inbox")
```

- **Remetente conferido:** o Worker lê o primeiro `Authentication-Results`, o que a Cloudflare acrescenta
  (`mx.cloudflare.net`), e aceita o e-mail na INBOX só com `spf=pass` ou `dmarc=pass` e o remetente do envelope
  com o domínio na lista `ALLOWED_DOMAINS`. O resto vai para a **Quarentena**. Cada e-mail ganha no
  topo o cabeçalho `X-Astroverso-Mailserver: inbox|quarentena; <motivo>`. A pasta é decidida pelo prefixo da chave
  no KV (`inbox.` ou `quarentena.`), não pelo cabeçalho, que um remetente poderia forjar.
- **Sem perda:** um e-mail só sai do KV depois que o Dovecot o aceita. Falhas ficam para a próxima rodada e
  avisam no Discord (uma vez por dia), com aviso de volta quando passam. Rodadas não se sobrepõem (`flock`).
- **Envio:** o Worker também atende `POST https://astroverso-mailserver.<subdomínio>.workers.dev/enviar`, com o
  cabeçalho `X-Astro-Chave` (`SEND_KEY`, gerada na instalação; sem ela, 401) e o corpo `{"para": [...], "assunto",
  "texto", "html", "anexos": [{"nome", "tipo", "base64", "cid"}]}` (anexo com `cid` vai embutido no HTML, como
  `<img src="cid:...">`). Envia um e-mail por destinatário, de `<endereço da caixa>`, pela ligação `send_email` do
  Worker, e responde `{"enviados": [...], "erros": [...]}`. A Cloudflare só entrega para os endereços de destino
  verificados da conta (sem custo); os outros voltam em `erros`.
- **Limites do plano gratuito:** e-mails de até 24 MiB (o resto é recusado); o KV aceita 1.000 gravações e
  1.000 listagens por dia (a busca só lista quando a campainha tocou).

## Perguntas da instalação

| Pergunta | Padrão |
|---|---|
| Endereço da caixa | `inbox@<domínio do Caddy>` |
| Domínios autorizados | (separados por vírgula; ex.: o domínio do seu e-mail) |
| Usuário do Nextcloud que recebe a caixa no app Mail | o administrador do Nextcloud (só com o Nextcloud instalado) |
| Token da Cloudflare | (secreto, conferido na API) |

O token precisa de **Account → Workers Scripts → Edit**, **Account → Workers KV Storage → Edit**, **Account →
Email Routing Addresses → Edit**, **Zone → Email Routing Rules → Edit**, **Zone → Zone Settings → Edit**, **Zone → Zone → Read** e **Zone → DNS → Read**, na conta e na zona do endereço, sem
expiração. É separado do token do Caddy.

## O que a instalação faz

- **Email Routing:** confere pelo DNS os MX do domínio do endereço. Com os da Cloudflare, segue. Sem nenhum,
  ativa pela API (`POST zones/<zona>/email/routing/dns`, que cria e trava os MX e o SPF; o campo `name` só vai para um subdomínio, porque a Cloudflare o recusa com o domínio da zona) e
  espera os MX aparecerem (até 2 minutos). Com MX de outro serviço, para sem mudar nada: ativar desviaria o
  e-mail que chega por eles.
- **Cloudflare pela API:** cria o KV `astroverso-mailserver` (se não existir), publica o Worker `astroverso-mailserver`
  (`worker.js`, com o KV em `MAIL`, a lista em `ALLOWED_DOMAINS`, o remetente em `REMETENTE`, a chave de envio
  como segredo em `CHAVE_ENVIO` e o envio em `ENVIO`, do tipo `send_email`) e cria ou atualiza a regra `endereço →
  Worker`. Liga o endereço `workers.dev` do Worker (cria o subdomínio da conta, `astroverso-<aleatório>`, se ainda não
  houver) e grava a URL em `SEND_URL`, que o n8n usa para enviar.
- **Caixa local:** container `astroverso-mailserver` (imagem oficial `dovecot/dovecot`, versão fixada no
  `docker-compose.yml`), sem porta na máquina: o IMAP (`31143`, sem TLS) só existe na rede `astroverso_default`. O
  `dovecot.conf` liga o login sem TLS e troca a senha da imagem por um `passwd-file` com um usuário só, `inbox`,
  cuja senha é gerada na instalação (`IMAP_PASSWORD` no `.env`; o hash vai para `data/users`). Mensagens em
  `~/.astroverso/mailserver/data/vmail` (Maildir), dentro do backup das configurações.
- **Busca:** `astroverso-mailserver-fetch.service` e `.timer` do usuário, de 5 em 5 minutos das 08:00 às 20:00
  (`OnCalendar`), rodando `project.sh fetch`. A cada e-mail guardado, o Worker grava também a chave `campainha` no KV.
  A busca agendada só lê essa chave (uma leitura, barata): sem ela, para ali; com ela, apaga a campainha antes de
  listar, para um e-mail que chegue no meio da rodada tocar de novo, e então busca. Fora do horário, os e-mails
  esperam no KV e chegam na primeira rodada das 08:00. "Buscar os e-mails agora" (Gerenciar Astroverso e Discord
  `mailserver:fetch`) e a instalação ignoram a campainha e listam direto.
- **Nextcloud Mail:** com um usuário do Nextcloud configurado, instala e ativa o app Mail e cria a conta "Astro
  Inbox" (IMAP `astroverso-mailserver:31143`, sem TLS). A senha não vai como argumento do `occ`: um script PHP pela
  entrada padrão monta os argumentos e lê a senha de uma variável de ambiente. Uma conta com o mesmo endereço não é
  recriada.

## Ações

- **Domínios autorizados:** mostra a lista, adiciona ou remove domínios, grava `ALLOWED_DOMAINS` e republica o
  Worker na hora. Ao adicionar um domínio, oferece mover para a entrada os e-mails dele que estavam na Quarentena
  (busca pelo cabeçalho `X-Astroverso-Mailserver`). Uma lista antiga de remetentes (`ALLOWED_SENDERS`) vira a lista dos
  domínios deles.
- **Destinatários de e-mail:** lista os endereços de destino da conta na Cloudflare (confirmados ou aguardando
  confirmação), cadastra um novo (a Cloudflare manda a ele um e-mail com o link de confirmação) e remove os
  escolhidos. Só os confirmados recebem os envios do Astroverso.
- **Reprocessar e-mails:** lista os e-mails da entrada (data e assunto), você marca quais (ou todos), e cada um é
  copiado de novo para a entrada como novo (`doveadm fetch text` → `doveadm save`) e só então a cópia antiga é
  apagada. As rotinas do n8n que leem a caixa (como Contas: leitura) os processam outra vez. Pelo Discord,
  `mailserver:reprocess` faz o mesmo com os e-mails dos últimos 30 dias, com confirmação.
- **Buscar os e-mails agora** e **Mostrar os dados de acesso à caixa (IMAP)**.

## Arquivos gerados

| Caminho | Conteúdo |
|---|---|
| `~/.astroverso/mailserver/.env` | Endereço, domínios autorizados, usuário do Nextcloud, token, senha do IMAP, IDs da zona, da conta e do KV, chave (`SEND_KEY`) e URL (`SEND_URL`) do envio (600) |
| `~/.astroverso/mailserver/data/users` | Usuário `inbox` com o hash da senha |
| `~/.astroverso/mailserver/data/vmail` | Mensagens (Maildir) |
| `~/.config/systemd/user/astroverso-mailserver-fetch.{service,timer}` | Busca periódica |

## Remoção

`remove` desliga a busca, apaga o container e a imagem, a regra do Email Routing, o Worker e o KV (com os
e-mails ainda não buscados), a conta "Astro Inbox" do Nextcloud Mail e `~/.astroverso/mailserver`. Também desliga o
Email Routing do domínio (`DELETE zones/<zona>/email/routing/dns`, que tira os MX e o SPF); se a Cloudflare
recusar, avisa para desligar pelo painel. Os destinatários de e-mail ficam cadastrados na conta da Cloudflare (o
subdomínio `workers.dev` também), prontos para uma nova instalação.
