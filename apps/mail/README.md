# mail

O e-mail do Astroverso, em duas partes:

- **Caixa de entrada para automações** (ex.: `inbox@<domínio>`): os e-mails que você encaminha do seu e-mail de
  sempre chegam pela Cloudflare e ficam numa caixa IMAP local (Dovecot), lida pelas automações e pelo **Nextcloud
  Mail** (a conta aparece sozinha lá). Nenhuma porta fica aberta para a internet.
- **Envio para qualquer app** pelo `kit.mail.send`, de qualquer máquina, pelo mesmo Worker da Cloudflare (só para
  destinatários confirmados na conta).

Uma máquina tem a **caixa**; as outras instalam o app no modo **só envio** (endereço e chave de envio).

## Como funciona

```
seu e-mail (filtro que encaminha)
   ↓
<caixa>                          Cloudflare Email Routing (domínio sem outro e-mail)
   ↓
Worker astroverso-mail           confere o remetente e grava o e-mail no KV astroverso-mail (e toca a "campainha")
   ↓  de 5 em 5 minutos, das 08:00 às 20:00 (astroverso-mail-fetch.timer), só lista o KV se a campainha tocou
busca (astroverso mail action fetch-scheduled)
   ↓  doveadm save; só apaga do KV depois que o Dovecot aceitou
astroverso-mail (Dovecot)        usuário inbox, pastas INBOX e Quarentena, IMAP 31143 só na rede dos containers
   ├─ automações (IMAP)
   └─ Nextcloud Mail             o app mail publica a caixa em ~/.astroverso/mailboxes/mail.json (kit.mailboxes)
```

- **Remetente conferido:** o Worker lê o `Authentication-Results` que a Cloudflare acrescenta e manda para a entrada
  só e-mails com `spf=pass` ou `dmarc=pass` e o remetente do envelope num **domínio autorizado**. O resto vai para a
  **Quarentena**, com o cabeçalho `X-Astroverso-Mail: inbox|quarentena; <motivo>` no topo. A pasta vem do prefixo da
  chave no KV, não do cabeçalho (que um remetente poderia forjar).
- **Sem perda:** um e-mail só sai do KV depois que o Dovecot o aceita; falhas ficam para a rodada seguinte.
- **Envio:** `POST <Worker>/enviar` com o cabeçalho `X-Astroverso-Chave` e `{"para", "assunto", "texto", "html",
  "anexos": [{"nome", "tipo", "base64", "cid"}]}` (anexo com `cid` vai no HTML como `<img src="cid:...">`); responde
  `{"enviados", "erros"}`. `GET <Worker>/conferir` confere a chave sem enviar nada. É o que o `kit.mail` faz.

## Envio pelos apps (`kit.mail`)

```python
from kit import mail

mail.send("eu@exemplo.com", "Contas de dezembro", "texto", html="<p>...</p>",
          attachments=[mail.Attachment("qr.png", "image/png", dados, cid="qr")])
```

Devolve a lista de quem recebeu. Sem o envio configurado na máquina, não faz nada; se o Worker não responder ou um
destinatário não estiver confirmado, mostra um aviso e segue.

## O que a instalação faz (modo caixa)

| Pergunta | Padrão |
|---|---|
| Esta máquina | tem a caixa / só envia |
| Endereço da caixa | `inbox@<domínio>` |
| Domínios autorizados | (os de quem encaminha, ex.: `gmail.com`) |
| Token da Cloudflare do app mail | (com o link para o passo a passo; conferido na API) |

1. **Cloudflare:** confere os MX do domínio do endereço. Com os da Cloudflare, segue; sem nenhum, liga o Email
   Routing pela API e espera os MX (até 2 minutos); com MX de outro serviço, para sem mudar nada. Cria o KV (se
   faltar), publica o Worker (`worker.js`, com o KV, os domínios autorizados, o remetente, a chave de envio como
   segredo e a ligação `send_email`), liga o endereço `workers.dev` dele (cria o subdomínio da conta, se faltar) e
   cria ou atualiza a regra `<caixa> → Worker`.
2. **Caixa:** gera a senha do IMAP (`secrets/imap_password`, `600`; no Dovecot, só o hash `SHA512-CRYPT`), sobe o
   container e cria a pasta Quarentena.
3. Pergunta as mudanças no sistema (abaixo), publica a caixa para os outros apps, liga o envio desta máquina e faz
   a primeira busca.
4. Sem destinatário confirmado na conta, oferece cadastrar um.
5. Mostra o link do passo a passo do filtro de encaminhamento.

No modo **só envio**, pergunta o endereço e a chave de envio e os confere no Worker.

## Mudanças na máquina

| Mudança | Por quê |
|---|---|
| Podman instalado e *linger* ligado (modo caixa) | A caixa roda em container, como serviço do usuário, e sobe no boot sem ninguém logado |
| Container `astroverso-mail` (imagem oficial `dovecot/dovecot`, versão fixada), sem porta na máquina, unidade Quadlet | A caixa IMAP; o IMAP (31143, sem TLS) só existe na rede dos containers |
| `~/.astroverso/mail/` (`.env` `600` com o endereço, os domínios, o token, os IDs da Cloudflare, a chave e o endereço do envio; `secrets/imap_password`; `users`; `vmail/` com os e-mails; `fetch.json`) | A configuração, as senhas e os e-mails |
| `~/.astroverso/mailboxes/mail.json` (`600`) | A caixa publicada para os outros apps (o Nextcloud cria a conta no Mail a partir dela) |
| `~/.astroverso/mail.env` (`600`, `MAIL_URL`, `MAIL_KEY`) | Liga esta máquina ao envio: é o que o `kit.mail` usa |
| ⚠ Unidades do usuário `astroverso-mail-fetch.timer` e `.service` (perguntada) | A busca dos e-mails; sem ela, eles ficam na Cloudflare |
| Unidades do usuário `astroverso-mail-watch.timer` e `.service` (perguntada) | A verificação de hora em hora |
| Unidades do usuário `astroverso-mail-backup.timer` e `.service` (perguntada, padrão sim) | Backup diário da configuração do app no servidor de backup (`kit.backup`), com aviso no `#backup` |

Na Cloudflare (pela API, com o seu token): o Email Routing do domínio (MX e SPF), o KV e o Worker `astroverso-mail`,
o subdomínio `workers.dev` da conta (se faltava) e a regra do endereço.

## Fora da máquina (passos seus)

| Passo | Por quê | Como fazer |
|---|---|---|
| Criar o token da Cloudflare do app mail (sete permissões) | O app mantém o Email Routing, o Worker e o KV pela API | [cloudflare.md](docs/cloudflare.md#criar-o-token) |
| Confirmar os destinatários (clicar no link da Cloudflare) | A Cloudflare só entrega envios a endereços verificados | [cloudflare.md](docs/cloudflare.md#destinatários) |
| Criar no seu e-mail o filtro que encaminha para a caixa | A caixa só recebe o que você encaminha | [encaminhamento.md](docs/encaminhamento.md) |

## Ações

| Ação | O que faz |
|---|---|
| Resumo do e-mail | Caixa, última busca, contagem da entrada e da Quarentena, domínios, token e endereço de envio. Também no Discord: `/astro mail:summary` |
| Buscar os e-mails agora | Busca sem esperar a campainha. Também no Discord: `mail:fetch` |
| Domínios autorizados | Adiciona e remove domínios e republica o Worker; ao adicionar, oferece mover da Quarentena os e-mails do domínio |
| Destinatários de e-mail | Lista (confirmado ou aguardando), cadastra (a Cloudflare manda o link) e remove |
| Reprocessar e-mails | Os e-mails escolhidos voltam à entrada como novos, para as automações lerem de novo. No Discord, `mail:reprocess-recent` faz isso com os dos últimos 30 dias (com confirmação) |
| Mostrar o endereço e a chave de envio | Para ligar outra máquina no modo só envio |
| Limpar Workers e KV antigos da Cloudflare | Lista os da conta, menos os deste app, e apaga os marcados |
| Enviar um e-mail de teste | Pelo `kit.mail`, para um destinatário confirmado (em qualquer modo) |
| Mudanças no sistema / Verificar agora | Como nos outros apps |
| Fazer backup agora / Restaurar uma versão | Backup da configuração na hora (também no Discord) e restauração de uma versão guardada no servidor de backup (app `backup`), com uma cópia "antes-da-restauracao" |

## Verificação de hora em hora

Avisa no canal `#mail` do Discord só quando algo muda, com os botões **Resumo do e-mail** e **Buscar agora**:

| O que confere | Nível |
|---|---|
| Caixa parada | erro |
| Busca dos e-mails falhando | erro |
| Token da Cloudflare recusado | erro |
| E-mails parados no KV há mais de 30 minutos (das 08:00 às 20:00) | aviso |
| E-mails na Quarentena (pode faltar autorizar um domínio) | info |

## Remover

Desfaz as mudanças, faz uma última busca, apaga na Cloudflare a regra, o Worker, o KV e o Email Routing do domínio,
remove o container, retira a caixa dos outros apps (o Nextcloud apaga a conta do Mail) e desliga o envio desta
máquina. Os e-mails da caixa (`vmail/`) só são apagados se você confirmar (padrão não). Os destinatários e o
subdomínio `workers.dev` ficam na conta da Cloudflare.

## Backup

O `.env`, a senha do IMAP e os e-mails (`vmail/`, por `podman unshare tar`). Ao restaurar, a instalação roda com as
respostas salvas.

Testes: `python3 -m unittest discover -s apps/mail/tests`.
