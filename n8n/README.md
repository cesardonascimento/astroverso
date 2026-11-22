# n8n

Plataforma de automações montadas pelo navegador, com blocos prontos para centenas de serviços. Roda isolada:
só na rede local, pelo Caddy, e sem comunicação com os servidores da empresa que a desenvolve.

```bash
./project.sh install           # perguntas, containers e rota no Caddy
./project.sh remove            # desfaz tudo o que o projeto criou (usado pelo Implodir Astroverso)
./project.sh remote contas:email [AAAA-MM]   # envia agora o e-mail das contas (padrão: mês atual; o mesmo do Discord)
```

## Perguntas da instalação

| Pergunta | Padrão |
|---|---|
| Endereço do n8n no Caddy | `n8n.<domínio>` |
| E-mail do administrador | `n8n@<domínio>` (só o login: não precisa existir, o n8n não manda e-mails) |
| Nome e sobrenome do administrador | — |
| Senha do administrador | (secreta, mínimo 8 caracteres; ao reinstalar, pergunta se troca) |
| Chave da API da Anthropic | (secreta; Enter vazio deixa para depois) |

## O que vem configurado

| Item | Como |
|---|---|
| Versão | `n8nio/n8n` e `n8nio/runners` fixadas em `docker-compose.yml`, sempre na mesma versão |
| Containers | `astroverso-n8n` (editor, agendamentos e execuções) e `astroverso-n8n-runners` (roda o código do nó Code, em JavaScript ou Python, separado do n8n), na rede `astroverso_default`, sem porta no host |
| Endereço | `https://<endereço>` pelo Caddy (`http://astroverso-n8n:5678`); webhooks com o mesmo endereço, só na rede local |
| Banco | SQLite em `~/.astroverso/n8n/data/n8n` |
| Administrador | criado pela instalação por variáveis de ambiente (`N8N_INSTANCE_OWNER_*`), reaplicado a cada início; e-mail, nome e senha ficam travados na interface e mudam pela reinstalação |
| Chave de criptografia | `N8N_ENCRYPTION_KEY`, gerada uma vez no `.env`: protege as credenciais cadastradas no n8n |
| Isolamento | telemetria, aviso de versão nova e galeria de modelos desligados, ganchos de diagnóstico vazios (página "Isolate n8n" da documentação); o assistente de IA da n8n fica desligado |
| Máquina protegida | o nó Execute Command fica desligado, como no padrão da versão 2: o n8n não roda comandos no servidor |
| Histórico | execuções apagadas depois de 14 dias |
| Fuso | o da máquina |

## Rotinas

As rotinas ficam só no banco do n8n (`database.sqlite`, tabela `workflow_entity`): o repositório não guarda
nenhuma. Os parâmetros de cada rotina (pasta, senhas dos PDFs, destinatários) ficam no próprio fluxo, num nó
**⚙️ Configuração** lido pelos outros nós com `$('⚙️ Configuração').first().json.config`. Cada versão salva vai
para o histórico do n8n (`workflow_history`), e o backup das configurações leva o banco inteiro, com o histórico.
Numa instalação do zero, a instalação avisa quando o n8n está sem rotinas, e Administração → **Restaurar uma
versão** → n8n as traz do backup.

**Credenciais** (`import:credentials` com `id` fixo, a partir de um arquivo temporário dentro do container, apagado
logo depois; atualizadas a cada instalação e pela ação **Trocar a chave da API da Anthropic**; o n8n instala depois do
mailserver, do nextcloud e do discord, e uma senha trocada num deles pede reinstalar o n8n). As
rotinas apontam para esses `id`, que não mudam entre instalações:

| Credencial (`id`) | Origem |
|---|---|
| Astroverso: caixa inbox (IMAP) (`astroversoImapInbox`) | `astroverso-mailserver:31143`, usuário `inbox`, `IMAP_PASSWORD` do mailserver |
| Astroverso: bot do Discord (`astroversoDiscordBot`) | cabeçalho `Authorization: Bot <token>` do projeto discord |
| Astroverso: Nextcloud (`astroversoNextcloud`) | `https://<NEXTCLOUD_HOST>/remote.php/dav/files/<administrador>` e uma senha de app `astroverso-n8n` criada uma vez pelo `occ user:auth-tokens:add` |
| Astroverso: API da Anthropic (`astroversoAnthropic`) | cabeçalho `x-api-key` com `ANTHROPIC_API_KEY` |
| Astroverso: envio de e-mail (`astroversoEnvioEmail`) | cabeçalho `X-Astroverso-Chave` com `SEND_KEY` do mailserver (envio pelo Worker, em `SEND_URL`) |
| Astroverso: chamadas do assistente (`astroversoHook`) | cabeçalho `X-Astroverso-Chave` com `N8N_HOOK_TOKEN` (gerado uma vez), para webhooks chamados pelo Astroverso |

**Pelo Discord:** `contas:email [AAAA-MM]` (`remote-actions` do projeto) chama o webhook `POST
/webhook/astroverso-contas-email` de dentro do container `astroverso-n8n` (`node` com `fetch` em `127.0.0.1:5678`, a chave
das chamadas pela entrada padrão, corpo `{"mes": "AAAA-MM"}`; sem mês, a rotina usa o atual) e devolve o campo `mensagem` da resposta. A rotina
que atende esse webhook precisa da credencial "chamadas do assistente" e de resposta pelo último nó; sem ela
ligada, o comando avisa. O comando `help` do projeto põe `mailserver:fetch` e `contas:email` no grupo Contas.

## Executor de código

O `astroverso-n8n-runners` usa uma imagem própria (`Dockerfile`, construída na instalação a partir de `n8nio/runners` na
mesma versão do n8n): as bibliotecas `qrcode` e `pngjs` (versões fixadas, usadas pelas rotinas de contas para desenhar o QR
Code do Pix e o código de barras), `mupdf` e `zxing-wasm` (leitura de QR Codes) e o módulo `astroverso-qr` (pasta
`astroverso-qr`: abre o PDF, com as senhas se precisar, desenha as páginas e devolve os QR Codes encontrados; também lê
imagens) ficam em `/opt/astroverso/node_modules` (`NODE_PATH`), e o `/etc/n8n-task-runners.json` libera `qrcode`, `pngjs`
e `astroverso-qr` em `NODE_FUNCTION_ALLOW_EXTERNAL` (junto do `moment` de fábrica). A rotina Contas: leitura lê o Pix
dos QR Codes dos anexos antes de chamar o Claude. A versão
do `ARG N8N_VERSION` acompanha a do `n8nio/n8n` no `docker-compose.yml`.

## Backup e restauração

O backup das configurações (rclone, 01:00) chama `project.sh backup`, que roda `n8n export:entities` com o n8n
ligado (rotinas com o histórico de versões, credenciais, usuários e o resto do banco, em `data/n8n/backup/entities.zip`) e deixa o
`database.sqlite` de fora, porque a cópia do arquivo com o n8n rodando pode sair inconsistente.

A restauração para o n8n, troca a configuração e carrega a exportação num banco novo, por um container avulso
(`import:entities --truncateTables=true`), antes de subir o n8n de novo. A chave de criptografia vem junto, no
`.env` do backup.

## Arquivos gerados

| Caminho | Conteúdo |
|---|---|
| `~/.astroverso/n8n/.env` | Endereço, fuso, dados do administrador, chave de criptografia, token do executor de código, `ANTHROPIC_API_KEY`, `NEXTCLOUD_APP_PASSWORD` e `N8N_HOOK_TOKEN` (600) |
| `~/.astroverso/n8n/data/owner_password_hash` | Hash bcrypt da senha do administrador |
| `~/.astroverso/n8n/data/n8n` | Banco, configuração e exportação do backup do n8n |

## Remoção

`remove` apaga os containers, as imagens, a rota do Caddy e `~/.astroverso/n8n` (rotinas, credenciais e histórico). As
rotinas só voltam por um backup das configurações.
