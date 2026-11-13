# n8n

Plataforma de automações montadas pelo navegador, com blocos prontos para centenas de serviços. Roda isolada:
só na rede local, pelo Caddy, e sem comunicação com os servidores da empresa que a desenvolve.

```bash
./project.sh install           # perguntas, containers e rota no Caddy
./project.sh remove            # desfaz tudo o que o projeto criou (usado pelo Implodir Astro)
./project.sh remote contas:email [AAAA-MM]   # envia agora o e-mail das contas do mês (o mesmo do Discord)
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
Ao instalar sobre um fluxo que já existe, os valores do nó **⚙️ Configuração** do fluxo atual (exportado antes)
passam para a versão nova, pelo nome do campo; campos novos ficam com o padrão e os endereços de API
(`config.api_*`) sempre vêm do repositório. Marcadores trocados na importação: `__ASTRO_PASTA_CONTAS__`
(`CONTAS_PASTA`), `__ASTRO_CANAL_DISCORD__` (canal do projeto discord) e `__ASTRO_URL_ENVIO__` (`SEND_URL` do
mailserver). Para levar ao repositório uma mudança feita na interface: `n8n export:workflow --id=<id>`.

**Credenciais** (`import:credentials` com `id` fixo, a partir de um arquivo temporário dentro do container, apagado
logo depois; atualizadas a cada instalação e pela ação):

| Credencial | Origem |
|---|---|
| Astro: caixa inbox (IMAP) | `astro-mailserver:31143`, usuário `inbox`, `IMAP_PASSWORD` do mailserver |
| Astro: bot do Discord | cabeçalho `Authorization: Bot <token>` do projeto discord |
| Astro: Nextcloud | `https://<NEXTCLOUD_HOST>/remote.php/dav/files/<administrador>` e uma senha de app `astro-n8n` criada uma vez pelo `occ user:auth-tokens:add` |
| Astro: API da Anthropic | cabeçalho `x-api-key` com `ANTHROPIC_API_KEY` |
| Astro: envio de e-mail | cabeçalho `X-Astro-Chave` com `SEND_KEY` do mailserver (envio pelo Worker) |
| Astro: chamadas do assistente | cabeçalho `X-Astro-Chave` com `N8N_HOOK_TOKEN` (gerado uma vez), exigido pelos webhooks dos módulos |

**Contas: leitura** (`astroContasLeitu`): gatilho IMAP na `INBOX` (marca como lido, anexos baixados) → ⚙️
Configuração (pasta, modelo `claude-haiku-5-5`, esforço `low`, senhas de PDF, aviso, endereços das APIs) → cada
PDF tentado sem senha e com cada senha (Extract from File) → um pedido por e-mail à API, com os anexos que parecem
boleto primeiro (linha digitável, Pix, "pagável", "vencimento"; nota fiscal, demonstrativo e extrato por último),
até 20 mil caracteres por anexo e 60 mil no total; a instrução diz que um e-mail traz uma conta só, tirada do
documento com o código de pagamento (`anthropic-version: 2026-10-21`, `output_config.format` com JSON schema:
`e_cobranca` e `contas[]` com conta, titular, valor, vencimento, códigos, observações e anexo) → conferência sem IA
(DV dos campos e geral da linha digitável de 47 dígitos, blocos da conta de consumo de 48, valor e vencimento pelo
fator, CRC16 do Pix) → um arquivo `AAAA-MM.md` por mês de vencimento, criando a pasta nível a nível, sem repetir
uma conta cujo código (o Pix ou, sem ele, a linha digitável) já está no arquivo → aviso no Discord. Para cada
código conferido, gera a imagem para pagar com a câmera: QR Code do Pix (biblioteca `qrcode`) ou, sem Pix válido,
código de barras "2 de 5 intercalado" do boleto (os 44 dígitos do código de barras, montado da linha digitável, em
JavaScript puro), em SVG, gravados em `<pasta>/imagens/` com nome pelo hash do código (`pix-<hash>.svg`,
`boleto-<hash>.svg`) e embutidos no formato do Obsidian (`![[pix-<hash>.svg|220]]`). Divergências viram
`⚠️ revisar (motivo)` em **Observações**; um e-mail que a IA não leu vira uma conta "⚠️ revisar".

Formato do arquivo do mês (um bloco por conta, cada um terminado por `---`; a caixa `- [ ] **Pago**` é um item de
lista, clicável no Obsidian, e a linha em branco depois dela separa o resto):

```markdown
# 2026-12

**Conta**: Energia
**Valor**: R$ 187,32
- [ ] **Pago**

**Titular**: <nome do titular>
**Vencimento**: 10/12/2026
**Pix copia e cola**: `00020126...6304ABCD`
**QR code**: ![[pix-4a2e5eb7d7.svg|220]]
**Fonte**: 12/11/2026 - Sua fatura de dezembro - Companhia <fatura@empresa.com.br>

---
```

Sem Pix, no lugar das duas linhas dele vêm `**Boleto**` (a linha digitável) e `**Código de barras**`
(`![[boleto-<hash>.svg|420]]`). `**Titular**` só aparece quando o documento traz o nome, e `**Observações**` só
quando há algo a dizer (observação da IA, como "parcela 3 de 10", ou `⚠️ revisar (...)`).

**Contas: lembretes** (`astroContasLembr`): todo dia às 08:00, lê os arquivos do mês atual e do seguinte e avisa
no Discord as contas com `- [ ] **Pago**` (não marcadas) cujo `**Vencimento**` está até `dias_antecedencia`
(padrão 3) à frente, inclusive as vencidas. Linhas no formato antigo (`- [ ] … 📅 AAAA-MM-DD`) continuam valendo.

**Contas: e-mail mensal** (`astroContasEmail`): dois gatilhos, dia 5 de cada mês às 08:00 e o webhook `POST
/webhook/astro-contas-email` (credencial "chamadas do assistente", resposta do último nó) → ⚙️ Configuração
(`destinatarios` separados por vírgula, pasta, aviso, `api_envio`) → mês do corpo (`{"mes": "AAAA-MM"}`) ou o
atual → lê `AAAA-MM.md` no Nextcloud → monta o e-mail: um quadro por conta (valor, titular, vencimento e, nas não
pagas, o Pix copia e cola com o QR Code ou a linha digitável com o código de barras; as pagas aparecem como "✅
paga"), imagens em PNG embutidas por `cid` (QR pela `qrcode`, barras pela `pngjs`; o Gmail não mostra SVG), com
versão em texto → `POST <api_envio>/enviar` (credencial "envio de e-mail") → mensagem com quem recebeu e quem não
(destinatário não confirmado na Cloudflare) → aviso no Discord, só no envio agendado (pelo Discord, a resposta do
comando já mostra o resultado). Sem destinatários ou sem contas no mês, não envia e avisa.

**Pelo Discord:** `contas:email [AAAA-MM]` (`remote-actions` do projeto) chama o webhook de dentro do container
`astro-n8n` (`node` com `fetch` em `127.0.0.1:5678`, a chave pela entrada padrão) e devolve a mensagem do fluxo; com
o módulo desligado, avisa. O comando `help` do projeto põe `mailserver:fetch` e `contas:email` no grupo Contas.

## Executor de código

O `astro-n8n-runners` usa uma imagem própria (`Dockerfile`, construída na instalação a partir de `n8nio/runners` na
mesma versão do n8n): as bibliotecas `qrcode` e `pngjs` (versões fixadas) ficam em `/opt/astro/node_modules`
(`NODE_PATH`), e o `/etc/n8n-task-runners.json` as libera em `NODE_FUNCTION_ALLOW_EXTERNAL` (junto do `moment` de
fábrica). A
versão do `ARG N8N_VERSION` acompanha a do `n8nio/n8n` no `docker-compose.yml`.

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
| `~/.astro/n8n/.env` | Endereço, fuso, dados do administrador, chave de criptografia, token do executor de código, `CONTAS_PASTA`, `ANTHROPIC_API_KEY`, `NEXTCLOUD_APP_PASSWORD` e `N8N_HOOK_TOKEN` (600) |
| `~/.astro/n8n/data/owner_password_hash` | Hash bcrypt da senha do administrador |
| `~/.astro/n8n/data/n8n` | Banco, configuração e exportação do backup do n8n |

## Remoção

`remove` apaga os containers, as imagens, a rota do Caddy e `~/.astro/n8n` (fluxos, credenciais e histórico).
