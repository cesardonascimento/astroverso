# Cloudflare: e-mail do Astroverso

O app `mail` usa três recursos da Cloudflare, todos no plano gratuito, e cria e mantém os três sozinho pela API:

| Recurso | Para quê |
|---|---|
| **Email Routing** | Recebe os e-mails do endereço da caixa (ex.: `inbox@<domínio>`) e os entrega ao Worker |
| **Worker** `astroverso-mail` | Confere o remetente, guarda cada e-mail no KV e envia os e-mails dos apps (`/enviar`) |
| **KV** `astroverso-mail` | Guarda cada e-mail até a caixa da máquina buscá-lo |

A única coisa que você faz no site é **criar o token** e, depois, **confirmar os destinatários**. Requisito: o DNS do
domínio na Cloudflare (o mesmo do Caddy serve).

Nos exemplos, `<domínio>` é o domínio do endereço da caixa. O instalador mostra os valores certos na tela.

## Criar o token

O token do Caddy não serve: este precisa de outras permissões, e é bom que cada app tenha o seu (se um vazar, você
apaga só ele).

1. Abra <https://dash.cloudflare.com/profile/api-tokens> (ícone da conta → **My Profile** → **API Tokens**).
2. Clique em **Create Token**.
3. Desça até **Custom token** e clique em **Get started**.
4. Em **Token name**, coloque `astroverso mail`.
5. Em **Permissions**, monte as sete linhas abaixo. A primeira já aparece; para as outras, clique em **+ Add more**.
   Em cada linha, escolha os três campos da esquerda para a direita:

   | 1º campo | 2º campo | 3º campo | Para quê |
   |---|---|---|---|
   | Account | Workers Scripts | Edit | Publicar e atualizar o Worker |
   | Account | Workers KV Storage | Edit | Criar o KV e buscar os e-mails guardados nele |
   | Account | Email Routing Addresses | Edit | Cadastrar os destinatários dos envios |
   | Zone | Email Routing Rules | Edit | Criar a regra "endereço da caixa → Worker" |
   | Zone | Zone Settings | Edit | Ligar o Email Routing no domínio |
   | Zone | Zone | Read | Achar a zona do domínio |
   | Zone | DNS | Read | Conferir os registros MX |

   Dica: no 2º campo, dá para digitar parte do nome (ex.: `KV`, `Routing`) para filtrar a lista.
6. Em **Account Resources**, deixe **Include** e escolha **a sua conta**.
7. Em **Zone Resources**, escolha **Include** → **Specific zone** → `<domínio>`.
8. Deixe **Client IP Address Filtering** vazio (o IP de casa muda).
9. Em **TTL**, deixe sem data de fim. Se o token expirar, os e-mails param de chegar e de ser enviados.
10. Clique em **Continue to summary**. Confira: as sete permissões, a sua conta e a zona `<domínio>`.
11. Clique em **Create Token** e copie o token. **Ele só aparece uma vez**: guarde no seu gerenciador de senhas.

Cole o token quando o instalador pedir. Ele não aparece na tela e é conferido na hora (se está ativo e se enxerga a
zona). Fica só na máquina da caixa, em `~/.astroverso/mail/.env`, com acesso só do seu usuário.

**Se o instalador reclamar de permissão** numa etapa (ex.: "a Cloudflare recusou POST .../email/routing/dns"), volte
ao token (**API Tokens** → **⋯** ao lado dele → **Edit**), confira a linha que falta e salve: o mesmo token passa a
valer com a permissão nova, sem trocar nada na máquina.

## Email Routing

**Para que serve:** é o serviço da Cloudflare que recebe e-mails num domínio seu sem servidor de e-mail. Ao ligar, a
Cloudflare cria (e trava) os registros **MX** e **SPF** do domínio, apontando para ela.

O instalador liga sozinho quando o domínio **não tem nenhum MX**. Se o domínio **já recebe e-mail** por outro
serviço (Gmail do Google Workspace, Outlook, o e-mail do provedor do domínio...), o instalador **para sem mudar
nada**: ligar o Email Routing desviaria todos esses e-mails para a Cloudflare. Nesse caso:

- use um endereço num domínio sem outro e-mail (o domínio do Astroverso, se ele não tem e-mail, é o ideal); ou
- use um subdomínio (ex.: `inbox@mail.<domínio>`): o Email Routing pode ficar só nele, sem mexer no e-mail do domínio
  principal.

Para conferir à mão: painel da Cloudflare → o domínio → **Email** → **Email Routing**. Depois da instalação, aparece
lá a regra `inbox@<domínio>` → **Send to a Worker** → `astroverso-mail`.

## Destinatários

O envio do Worker (pela ligação `send_email` do Email Routing) só entrega para **endereços de destino verificados
na sua conta**. É uma regra da Cloudflare contra spam, e não tem custo. Serve para avisos para você e sua família; não
para mandar e-mail a qualquer pessoa.

Para cadastrar, use a ação **Destinatários de e-mail** (ou responda que sim na instalação):

1. Digite o e-mail do destinatário.
2. A Cloudflare manda para ele um e-mail **"Verify your email address"** (de `noreply@notify.cloudflare.com`).
3. A pessoa abre e clica em **Verify email address**. Pronto: a situação muda para **confirmado** na ação.

Um destinatário não confirmado recebe nada: o envio volta com o erro "destination address is not a verified address".
Os destinatários ficam na conta (**Email** → **Email Routing** → **Destination addresses**), mesmo se o app for removido.

## Envio de outras máquinas

O Worker fica em `https://astroverso-mail.<subdomínio-da-conta>.workers.dev`. O subdomínio `workers.dev` da conta é
criado pelo instalador se ainda não existir (ex.: `astroverso-1a2b3c4d`). Qualquer máquina com o endereço e a **chave
de envio** manda e-mails: na máquina da caixa, a ação **Mostrar o endereço e a chave de envio** mostra os dois; na
outra máquina, instale o app `mail` e escolha **Só envia e-mails**.

Sem a chave, o Worker responde 401 a qualquer pedido.

## Limpar recursos antigos

A ação **Limpar Workers e KV antigos da Cloudflare** lista os Workers e os KV da conta, menos os deste app, e apaga os
que você marcar (de instalações antigas, por exemplo). Apagar um KV apaga os e-mails que ainda estivessem nele.

## Limites do plano gratuito

| Limite | Efeito |
|---|---|
| E-mail de até 25 MiB (o Worker recusa acima de 24 MiB) | E-mails maiores voltam para quem mandou |
| KV: 1.000 gravações e 1.000 listagens por dia | A busca só lista o KV quando a "campainha" tocou; dá para centenas de e-mails por dia |
| Worker: 100.000 pedidos por dia | Muito acima do uso de uma casa |

## Problemas comuns

| Sintoma | O que conferir |
|---|---|
| E-mails não chegam e o Resumo mostra "Token recusado" | O token foi apagado ou expirou: crie outro (acima) e reinstale o app `mail` |
| O instalador parou em "já recebe e-mail por ..." | O domínio tem MX de outro serviço: veja **Email Routing** acima |
| E-mail encaminhado foi para a Quarentena | O domínio de quem encaminha não está na lista: ação **Domínios autorizados** |
| Envio volta com "not a verified address" | O destinatário ainda não clicou no link da Cloudflare: veja **Destinatários** |
