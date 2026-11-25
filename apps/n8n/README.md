# n8n

Rotinas automáticas montadas pelo navegador ([n8n](https://n8n.io)), com blocos prontos para centenas de serviços, em
`https://n8n.<domínio>` (só na rede de casa e no Tailscale). As rotinas ficam no banco do n8n: você cria, edita, liga e
desliga por lá, e o que está no n8n é a fonte de verdade. Os **módulos do Astroverso** ([modules/](modules/README.md))
sobem junto, como APIs pequenas que as rotinas chamam. Hoje: [contas](modules/contas/README.md) (QR Codes do Pix e
códigos de barras das contas a pagar).

## Containers

| Container | Imagem | Para quê |
|---|---|---|
| `astroverso-n8n` | `n8nio/n8n:<versão>` | Editor, agendamentos e execuções, na porta 5678 só da rede dos containers |
| `astroverso-n8n-runners` | `n8nio/runners:<versão>` (a mesma) | Roda o código dos nós Code (JavaScript e Python) separado do n8n |
| `astroverso-n8n-<módulo>` | `localhost/astroverso-n8n-<módulo>:<resumo>` | Um por módulo de `modules/`, em `http://astroverso-n8n-<módulo>:8080` |

Versão fixada em `n8n.py`. Banco SQLite em `~/.astroverso/n8n/data`.

## O que a instalação faz

| Pergunta | Padrão |
|---|---|
| Endereço do n8n | `n8n.<domínio>` |
| E-mail, nome e sobrenome do administrador | `n8n@<domínio>` (só o login: não precisa existir), `Astroverso`, `n8n` |
| Senha do administrador | sem padrão, mínimo 8 caracteres (na reinstalação, pergunta se troca) |

1. Gera, uma vez, a chave de criptografia do n8n (protege as credenciais), o token do executor de código e a chave das
   chamadas do Astroverso. A senha do administrador fica só como hash bcrypt (gerado com o `bcryptjs` da própria imagem,
   senha pela entrada padrão).
2. Sobe o n8n, o executor e os módulos (cada módulo vira uma imagem montada na hora; a imagem é refeita quando os
   arquivos do módulo mudam, e o módulo que sai de `modules/` tem o container removido).
3. Grava as **conexões do Astroverso** (abaixo) como credenciais do n8n.
4. Publica `n8n.<domínio>` pelo `kit.routes` e pergunta as mudanças no sistema.

O administrador é mantido pela instalação (`N8N_INSTANCE_OWNER_MANAGED_BY_ENV`): e-mail, nome e senha ficam travados na
tela do n8n e mudam pela reinstalação ou pela ação **Trocar a senha do administrador**.

## Isolado da empresa

Telemetria, aviso de versão nova, galeria de modelos e personalização desligados, ganchos de diagnóstico vazios (página
"Isolate n8n" da documentação), o assistente de IA da n8n desligado, o nó Execute Command desligado (padrão da versão 2:
o n8n não roda comandos na máquina) e as variáveis de ambiente fora do alcance dos nós.

## Conexões do Astroverso

Credenciais com `id` fixo, montadas a partir dos contratos do kit (nunca da pasta de outro app) e regravadas a cada
instalação e pela ação **Atualizar as conexões do Astroverso** (ex.: depois de instalar o app `mail`). As rotinas apontam
para esses `id`, que não mudam entre instalações:

| Credencial (`id`) | Tipo | De onde vem |
|---|---|---|
| Astroverso: envio de e-mail (`astroversoEnvioEmail`) | Header Auth (`X-Astroverso-Chave`) | `kit.mail`: `POST <endereço do envio>/enviar` (o endereço aparece no Resumo) |
| Astroverso: caixa `<nome>` (IMAP) (`astroversoImap<Nome>`) | IMAP | `kit.mailboxes`: cada caixa publicada (ex.: a do app `mail`) |
| Astroverso: Discord (`astroversoDiscord`) | Header Auth (`Authorization: Bearer`) | `kit.discord`: `POST <endereço do bot>/v1/mensagens` |
| Astroverso: chamadas do Astroverso (`astroversoChamadas`) | Header Auth (`X-Astroverso-Chave`) | Chave gerada pela instalação, para os webhooks que o Astroverso chamar |

O que não estiver configurado na máquina fica de fora, com aviso. Credenciais de um assunto (ex.: a chave de uma API
externa) você cadastra no próprio n8n: o backup leva junto, criptografadas.

## Mudanças na máquina

| Mudança | Por quê |
|---|---|
| Podman e *linger*; os containers acima por Quadlet, na rede `astroverso`, sem porta na máquina | O n8n, o executor e os módulos; o Caddy chega no n8n pelo nome |
| `~/.astroverso/n8n/` (`.env` com as respostas e a chave das chamadas, `n8n.env` e `runners.env` `600` com a chave de criptografia e o token, `owner_password_hash`, `data/` com o banco) | A configuração e as rotinas |
| `~/.astroverso/routes/n8n.json` | O endereço publicado para o Caddy |
| Unidades do usuário `astroverso-n8n-watch.timer` e `.service` (perguntada) | A verificação de hora em hora |
| Unidades do usuário `astroverso-n8n-backup.timer` e `.service` (perguntada, com as pastas de destino) | O backup diário (abaixo) |

## Versões das rotinas

O banco do n8n é a fonte de verdade: nenhuma rotina fica no repositório (elas guardam dados pessoais) e nada sincroniza
código. Três camadas de versão:

| Camada | Para quê |
|---|---|
| Histórico de versões do próprio n8n | Desfazer uma edição recente, pela tela do n8n |
| **Restaurar uma rotina** (ação) | Trazer **uma** rotina de um backup (dias ou meses atrás) sem mexer nas outras: como cópia desligada ao lado da atual (`<nome> (restaurada de dd/mm)`), para comparar, ou substituindo a atual (volta ligada se estava ligada, por `publish:workflow`) |
| **Restaurar uma versão** (ação) | O n8n inteiro de uma data (máquina nova, desastre) |

## Backup

Pelo `kit.backup`, com o n8n no ar: `export:entities` (rotinas com o histórico, credenciais criptografadas, usuários e o
resto do banco), **cada rotina num arquivo JSON separado** (`export:workflow --backup`, sem segredos: as credenciais vão
só pelo `id`), o `.env`, o `n8n.env` (a chave de criptografia: sem ela, as credenciais do backup não abrem) e o hash da
senha. O `database.sqlite` não vai: copiado com o n8n rodando, pode sair inconsistente.

A restauração para os containers, apaga o banco e carrega a exportação **num banco novo** (`import:entities
--truncateTables=true`, por um container avulso), e reinstala com as respostas salvas.

## Ações

| Ação | O que faz |
|---|---|
| Resumo do n8n | Situação, versão, endereço, containers e módulos (com o endereço de cada um para as rotinas) e as conexões. Também no Discord |
| Atualizar as conexões do Astroverso | Regrava as credenciais das conexões (também no Discord) |
| Trocar a senha do administrador | Novo hash e reinício do n8n |
| Restaurar uma rotina / Restaurar uma versão | Veja "Versões das rotinas" |
| Importar rotinas (arquivos JSON) | Traz rotinas de uma pasta (exportadas de outro n8n ou do backup), desligadas; a de mesmo `id` é substituída. Antes, avisa as credenciais que ainda não existem (a importação liga cada nó pelo `id` ou pelo nome e tipo) |
| Mudanças no sistema / Verificar agora / Fazer backup agora | Como nos outros apps |

## Verificação de hora em hora

Avisa no canal `#n8n` do Discord só quando algo muda, com os botões **Resumo do n8n** e **Verificar de novo**:

| O que confere | Nível |
|---|---|
| Container do n8n ou do executor parado | erro |
| n8n de pé, mas sem responder (`/healthz`) | erro |
| Módulo parado ou sem responder (`/v1/saude`) | erro |

## Remover

Desfaz as mudanças, retira o endereço e remove os containers e as imagens. As rotinas, as credenciais e o histórico só
são apagados se você confirmar (padrão não); senão ficam em `~/.astroverso/n8n` e uma instalação nova as encontra.

Testes: `python3 -m unittest discover -s apps/n8n/tests`.
