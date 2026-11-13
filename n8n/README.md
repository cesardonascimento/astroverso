# n8n

Plataforma de automações montadas pelo navegador, com blocos prontos para centenas de serviços. Roda isolada:
só na rede local, pelo Caddy, e sem comunicação com os servidores da empresa que a desenvolve.

```bash
./project.sh install           # perguntas, containers e rota no Caddy
./project.sh remove            # desfaz tudo o que o projeto criou (usado pelo Implodir Astro)
```

## Perguntas da instalação

| Pergunta | Padrão |
|---|---|
| Endereço do n8n no Caddy | `n8n.<domínio>` |
| E-mail do administrador | `n8n@<domínio>` (só o login: não precisa existir, o n8n não manda e-mails) |
| Nome e sobrenome do administrador | — |
| Senha do administrador | (secreta, mínimo 8 caracteres; ao reinstalar, pergunta se troca) |
| Chave da API da Anthropic | (secreta; Enter vazio deixa para depois) |
| Pasta no Nextcloud para as contas | `Contas a pagar` (só na primeira importação dos módulos de contas) |

## O que vem configurado

| Item | Como |
|---|---|
| Versão | `n8nio/n8n` e `n8nio/runners` fixadas em `docker-compose.yml`, sempre na mesma versão |
| Containers | `astro-n8n` (editor, agendamentos e execuções) e `astro-n8n-runners` (roda o código do nó Code, em JavaScript ou Python, separado do n8n), na rede `astro_default`, sem porta no host |
| Endereço | `https://<endereço>` pelo Caddy (`http://astro-n8n:5678`); webhooks com o mesmo endereço, só na rede local |
| Banco | SQLite em `~/.astro/n8n/data/n8n` |
| Administrador | criado pela instalação por variáveis de ambiente (`N8N_INSTANCE_OWNER_*`), reaplicado a cada início; e-mail, nome e senha ficam travados na interface e mudam pela reinstalação |
| Chave de criptografia | `N8N_ENCRYPTION_KEY`, gerada uma vez no `.env`: protege as credenciais cadastradas no n8n |
| Isolamento | telemetria, aviso de versão nova e galeria de modelos desligados, ganchos de diagnóstico vazios (página "Isolate n8n" da documentação); o assistente de IA da n8n fica desligado |
| Máquina protegida | o nó Execute Command fica desligado, como no padrão da versão 2: o n8n não roda comandos no servidor |
| Histórico | execuções apagadas depois de 14 dias |
| Fuso | o da máquina |

## Módulos

Rotinas prontas em `modulos/*.json`, fluxos do n8n com `id` fixo e `meta.astro` (`modulo`, `versao`). A instalação
importa, desligados, os que ainda não existem no n8n (`import:workflow`); um módulo já instalado nunca é
sobrescrito, para não perder as mudanças feitas na interface. A ação **Módulos** (Gerenciar Astro → n8n) mostra
cada um (ligado, desligado ou não instalado, por `list:workflow`, e quando o repositório tem uma `meta.astro.versao`
maior que a instalada, lida por `export:workflow`), instala os que faltam, restaura um à versão do
repositório (substitui as mudanças e o deixa desligado), atualiza as credenciais e troca a chave da Anthropic.
Marcadores trocados na importação: `__ASTRO_PASTA_CONTAS__` (`CONTAS_PASTA`) e `__ASTRO_CANAL_DISCORD__` (canal do
projeto discord). Para levar ao repositório uma mudança feita na interface: `n8n export:workflow --id=<id>`.

**Credenciais** (`import:credentials` com `id` fixo, a partir de um arquivo temporário dentro do container, apagado
logo depois; atualizadas a cada instalação e pela ação):

| Credencial | Origem |
|---|---|
| Astro: caixa inbox (IMAP) | `astro-mailserver:31143`, usuário `inbox`, `IMAP_PASSWORD` do mailserver |
| Astro: bot do Discord | cabeçalho `Authorization: Bot <token>` do projeto discord |
| Astro: Nextcloud | `https://<NEXTCLOUD_HOST>/remote.php/dav/files/<administrador>` e uma senha de app `astro-n8n` criada uma vez pelo `occ user:auth-tokens:add` |
| Astro: API da Anthropic | cabeçalho `x-api-key` com `ANTHROPIC_API_KEY` |

**Contas: leitura** (`astroContasLeitu`): gatilho IMAP na `INBOX` (marca como lido, anexos baixados) → ⚙️
Configuração (pasta, modelo `claude-haiku-5-5`, esforço `low`, senhas de PDF, aviso, endereços das APIs) → cada
PDF tentado sem senha e com cada senha (Extract from File) → um pedido por e-mail à API, com os anexos que parecem
boleto primeiro (linha digitável, Pix, "pagável", "vencimento"; nota fiscal, demonstrativo e extrato por último),
até 20 mil caracteres por anexo e 60 mil no total; a instrução diz que um e-mail traz uma conta só, tirada do
documento com o código de pagamento, e o JSON diz de qual `anexo` ela saiu (`anthropic-version:
2026-10-21`, `output_config.format` com JSON schema: `e_cobranca` e `contas[]`) → conferência sem IA (DV dos campos
e geral da linha digitável de 47 dígitos, blocos da conta de consumo de 48, valor e vencimento pelo fator, CRC16
do Pix) → um arquivo `AAAA-MM.md` por mês de vencimento, criando a pasta nível a nível, sem repetir um código já
presente → aviso no Discord. Divergências viram `⚠️ revisar (motivo)` na tarefa; um e-mail que a IA não leu vira
uma tarefa de revisão.

Formato de cada conta (tarefa do Markdown, data no formato do plugin Tasks do Obsidian):

```markdown
- [ ] Energia · R$ 187,32 · vence 📅 2026-11-20
  - Boleto: `34191750090001234567489012345008416360000018732`
  - Beneficiário: Companhia de Energia · recebido em 12/11/2026 · e-mail "Sua fatura chegou"
```

**Contas: lembretes** (`astroContasLembr`): todo dia às 08:00, lê os arquivos do mês atual e do seguinte e avisa
as tarefas `- [ ]` com `📅` até `dias_antecedencia` (padrão 3) à frente, inclusive as vencidas.

## Backup e restauração

O backup das configurações (rclone, 01:00) chama `project.sh backup`, que roda `n8n export:entities` com o n8n
ligado (fluxos, credenciais, usuários e o resto do banco, em `data/n8n/backup/entities.zip`) e deixa o
`database.sqlite` de fora, porque a cópia do arquivo com o n8n rodando pode sair inconsistente.

A restauração para o n8n, troca a configuração e carrega a exportação num banco novo, por um container avulso
(`import:entities --truncateTables=true`), antes de subir o n8n de novo. A chave de criptografia vem junto, no
`.env` do backup.

## Arquivos gerados

| Caminho | Conteúdo |
|---|---|
| `~/.astro/n8n/.env` | Endereço, fuso, dados do administrador, chave de criptografia, token do executor de código, `CONTAS_PASTA`, `ANTHROPIC_API_KEY` e `NEXTCLOUD_APP_PASSWORD` (600) |
| `~/.astro/n8n/data/owner_password_hash` | Hash bcrypt da senha do administrador |
| `~/.astro/n8n/data/n8n` | Banco, configuração e exportação do backup do n8n |

## Remoção

`remove` apaga os containers, as imagens, a rota do Caddy e `~/.astro/n8n` (fluxos, credenciais e histórico).
