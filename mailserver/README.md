# mailserver

Caixa de e-mail só de entrada, para automações. Os e-mails encaminhados para um endereço no seu domínio chegam
pela Cloudflare (Email Routing + Worker + KV) e são buscados pelo astro para uma caixa IMAP local (Dovecot), lida
pelas automações e pelo app Mail do Nextcloud. Nenhuma porta fica aberta para a internet, e a caixa não envia
e-mails.

```bash
./project.sh install           # perguntas, Cloudflare, container, busca periódica e conta no Nextcloud Mail
./project.sh fetch             # busca os e-mails agora (o mesmo que o timer faz)
./project.sh remove            # desfaz tudo o que o projeto criou (usado pelo Implodir Astro)
```

## Como funciona

```
seu e-mail (filtro com encaminhamento)
   ↓
inbox@<domínio>                  Cloudflare Email Routing (domínio sem outro e-mail)
   ↓
Worker astro-mailserver          confere o remetente e grava o e-mail bruto no KV astro-mailserver
   ↓  de 5 em 5 minutos (astro-mailserver-fetch.timer)
project.sh fetch                 baixa cada e-mail, entrega com doveadm save e só então apaga do KV
   ↓
astro-mailserver (Dovecot)       usuário inbox, pastas INBOX e Quarentena
   ├─ automações (IMAP)
   └─ Nextcloud Mail ("Astro Inbox")
```

- **Remetente conferido:** o Worker lê o primeiro `Authentication-Results`, o que a Cloudflare acrescenta
  (`mx.cloudflare.net`), e aceita o e-mail na INBOX só com `spf=pass` ou `dmarc=pass` e o remetente do envelope
  na lista `ALLOWED_SENDERS` (endereço ou `@domínio`). O resto vai para a **Quarentena**. Cada e-mail ganha no
  topo o cabeçalho `X-Astro-Mailserver: inbox|quarentena; <motivo>`. A pasta é decidida pelo prefixo da chave
  no KV (`inbox.` ou `quarentena.`), não pelo cabeçalho, que um remetente poderia forjar.
- **Sem perda:** um e-mail só sai do KV depois que o Dovecot o aceita. Falhas ficam para a próxima rodada e
  avisam no Discord (uma vez por dia), com aviso de volta quando passam. Rodadas não se sobrepõem (`flock`).
- **Limites do plano gratuito:** e-mails de até 24 MiB (o resto é recusado); o KV aceita 1.000 gravações e
  1.000 listagens por dia (a busca usa 288).

## Perguntas da instalação

| Pergunta | Padrão |
|---|---|
| Endereço da caixa | `inbox@<domínio do Caddy>` |
| Remetentes aceitos | (endereços ou `@domínio`, separados por vírgula) |
| Usuário do Nextcloud que recebe a caixa no app Mail | o administrador do Nextcloud (só com o Nextcloud instalado) |
| Token da Cloudflare | (secreto, conferido na API) |

O token precisa de **Account → Workers Scripts → Edit**, **Account → Workers KV Storage → Edit**, **Zone → Email
Routing Rules → Edit**, **Zone → Zone → Read** e **Zone → DNS → Read**, na conta e na zona do endereço, sem
expiração. É separado do token do Caddy.

## O que a instalação faz

- **Email Routing:** confere pelo DNS se o domínio do endereço tem os MX da Cloudflare. Se não tiver, mostra como
  ativar pelo painel (Email → Email Routing → começar e aceitar os registros) e espera. Se o domínio já tiver
  outros MX, avisa que ativar desviaria o e-mail que chega por eles. A ativação fica manual: a API não garante
  deixar outros registros de e-mail como estão.
- **Cloudflare pela API:** cria o KV `astro-mailserver` (se não existir), publica o Worker `astro-mailserver`
  (`worker.js`, com o KV em `MAIL` e a lista em `ALLOWED_SENDERS`) e cria ou atualiza a regra `endereço →
  Worker`.
- **Caixa local:** container `astro-mailserver` (imagem oficial `dovecot/dovecot`, versão fixada no
  `docker-compose.yml`), sem porta na máquina: o IMAP (`31143`, sem TLS) só existe na rede `astro_default`. O
  `dovecot.conf` liga o login sem TLS e troca a senha da imagem por um `passwd-file` com um usuário só, `inbox`,
  cuja senha é gerada na instalação (`IMAP_PASSWORD` no `.env`; o hash vai para `data/users`). Mensagens em
  `~/.astro/mailserver/data/vmail` (Maildir), dentro do backup das configurações.
- **Busca:** `astro-mailserver-fetch.service` e `.timer` do usuário, a cada 5 minutos (e 2 minutos depois do
  boot), rodando `project.sh fetch`. Também em Gerenciar Astro e pelo Discord (`mailserver:fetch`).
- **Nextcloud Mail:** com um usuário do Nextcloud configurado, instala e ativa o app Mail e cria a conta "Astro
  Inbox" (IMAP `astro-mailserver:31143`, sem TLS). A senha não vai como argumento do `occ`: um script PHP pela
  entrada padrão monta os argumentos e lê a senha de uma variável de ambiente. Uma conta com o mesmo endereço não é
  recriada.

## Arquivos gerados

| Caminho | Conteúdo |
|---|---|
| `~/.astro/mailserver/.env` | Endereço, remetentes, usuário do Nextcloud, token, senha do IMAP e IDs da zona, da conta e do KV (600) |
| `~/.astro/mailserver/data/users` | Usuário `inbox` com o hash da senha |
| `~/.astro/mailserver/data/vmail` | Mensagens (Maildir) |
| `~/.config/systemd/user/astro-mailserver-fetch.{service,timer}` | Busca periódica |

## Remoção

`remove` desliga a busca, apaga o container e a imagem, a regra do Email Routing, o Worker e o KV (com os
e-mails ainda não buscados), a conta "Astro Inbox" do Nextcloud Mail e `~/.astro/mailserver`. O Email Routing do
domínio continua ativo: desligue pelo painel, se quiser.
