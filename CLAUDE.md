# CLAUDE.md

Regras para continuar o desenvolvimento do astro. O contexto da instalação atual (máquina, IPs,
domínio, contas) fica em `CLAUDE.local.md`, fora do git.

## Como trabalhar

- Responder sempre em **português do Brasil**, de forma direta.
- **Antes de alterar código ou documentação, descrever as mudanças e esperar a validação do usuário.** Depois de
  aprovado, fazer commit e push sem perguntar. Mensagens em português, terminando com a linha `Co-Authored-By` da
  sessão.
- **Sem comentários no código.** Mensagens de log, sim, bem formatadas.
- Toda mensagem na tela usa o prefixo do projeto (`[astro]`, `[adguard]`, `[caddy]`...), inclusive prompts,
  o prompt do `sudo` e os logs de dentro dos containers. Usar as funções de `lib/ui.sh`, nunca `echo` solto.
- Preferir o caminho simples e remover etapas desnecessárias.
- **Tudo funciona pela rede local**, mesmo com o Tailscale conectado. Não sugerir o IP do Tailscale como
  caminho de acesso.
- Quando algo pertence ao script (ex.: uma verificação manual que não se pode esquecer), colocar no
  assistente como etapa, com aviso e instruções.

## Nada pessoal no código nem na documentação

- Domínio, IPs, nomes de máquina, fuso, contas e e-mails **não podem aparecer** no código, nos READMEs
  nem neste arquivo. Eles vêm das perguntas da instalação (gravadas em `~/.astro/<projeto>/.env`) ou são detectados
  (`host_lan_ip`, `host_lan_subnet`, `hostname`, `timedatectl`).
- Exemplos usam marcadores: `<seu-domínio>`, `<domínio>`, `<ip>`, `<rede>`, `<nome-da-máquina>`.
- Valores padrão neutros quando nada é detectado (ex.: fuso `UTC`).
- Antes de cada commit, conferir com
  `git grep -nE '<domínio real>|<IP real>|<nome da máquina>'` usando os valores do `CLAUDE.local.md`.
- Valores reais desta instalação vão só no `CLAUDE.local.md`.

## Diretrizes dos READMEs

- **`README.md` da raiz** é para quem vai instalar e usar, não para quem vai programar:
  - Tabela **Projeto | Para que serve**: explica o que aquele tipo de serviço faz **em geral** e por que
    ele existe no homelab (ex.: o que é um proxy reverso e qual problema resolve), não como foi
    configurado.
  - **Como usar**: clonar e rodar o `setup.sh`, mais a tabela das opções do assistente.
  - **Respondendo a instalação**: uma subseção por projeto (e uma para as perguntas comuns a todos). Cada
    pergunta em negrito com o nome que aparece na tela, seguida do **que ela define**, **para que serve** e,
    quando houver, o padrão recomendado.
  - **Depois de instalar**: passos manuais fora da máquina (ex.: roteador).
- **`<projeto>/README.md`**: detalhes técnicos daquele projeto (o que vem customizado, tabela de perguntas
  com padrões, o que a instalação faz no host, arquivos gerados).
- **`lib/README.md`**: o contrato do `project.sh`, as convenções (compose, `.proxy`) e as bibliotecas.
- Ao adicionar ou mudar um projeto, uma pergunta da instalação ou uma opção do assistente, atualizar
  **na mesma mudança** a linha da tabela da raiz, a subseção "Respondendo a instalação", o README do
  projeto e, se mudar o contrato ou as bibliotecas, o `lib/README.md`.
- Texto em português do Brasil, frases curtas, sem valores pessoais (ver seção anterior).

## Regras de segurança ao testar

- **Nunca testar na pasta real nem no container real.** Copiar para o scratchpad e trocar `name:` do compose,
  `container_name`, imagem, portas (`15353`, `18080`, `18081`, `18443`) e a constante `CONTAINER` do `project.sh`.
  Um teste antigo recriou o container real e apagou um `.env` real.
- Nunca apagar nada em `~/.astro`: contém segredos e não está no git. Nunca rodar `remove` de um projeto nem o
  "Implodir Astro" na máquina real: eles apagam `~/.astro`, o login automático e as montagens dos discos. Para
  testar, usar outro `HOME` (o `ASTRO_HOME` vem de `$HOME/.astro`).
- `sudo` não funciona na sessão do Claude (sem TTY). `systemctl` e `pkexec` disparam uma janela gráfica do
  polkit para o usuário digitar a senha. Instalações que pedem `sudo` rodam em um terminal normal.
- Para testar menus e prompts, usar um pseudo-terminal em Python (`pty.fork`) enviando as teclas.
- Não pedir nem aceitar segredos (token da Cloudflare, senhas) no chat: eles entram pelo assistente.

## Arquitetura

```
setup.sh             assistente: Instalar/Reinstalar Astro (host_upgrade na primeira vez, discos, projetos na ordem ORDER),
                     Gerenciar Astro (ações dos projetos) → Administração (discos, Trocar o domínio, ações globais, Implodir Astro),
                     Modo desenvolvimento (só com o comando claude: exec claude --continue na pasta do repositório)
lib/ui.sh            logs com prefixo, prompts, ui_menu, ui_checklist (setas e Espaço)
lib/host.sh          host_base (comando astro, sem suspensão, compose, boot, ssh, tailscale) / host_undo, firewall, portas, IP e sub-rede
lib/env.sh           env_get CHAVE [padrão], state_setup / state_purge, images_remove, validadores
lib/proxy.sh         proxy_publish / proxy_unpublish (rotas do projeto no Caddy via .proxy)
lib/disk.sh          disk_manage / disk_setup / disk_mounts / disk_responds / disk_release_all (discos da máquina no fstab e crypttab, TPM; privado ou compartilhado; timer astro-disk-check → lib/disk-check.sh)
lib/notify.sh        avisos pelo bot do discord (fila; canal por NOTIFY_CHANNEL do projeto): notify_send / notify_info (silenciosa), notify_problem / notify_resolved (1 por dia), com botões
lib/brand.sh         paleta e nome (BRAND_*) e BRAND_DIR (a pasta logo/)
logo/                identidade visual: variantes em PNG transparente (símbolo, horizontal, texto, vertical; -alt para fundo claro) e a paleta no logo/README.md
<projeto>/project.sh describe | status | actions | action <id> | install | remove
                     opcionais: global-actions | remote-actions | remote <id> [arg] | help | backup | restore <pasta> | domain <antigo> <novo>
```

- Contrato e bibliotecas documentados em `lib/README.md`.
- Compose de todo projeto: `name: astro` + `x-podman: in_pod: false` (agrupados, mas independentes).
- **Estado fora do repositório:** tudo o que a instalação gera fica em `~/.astro/<projeto>` (`$STATE`, `$ENV_FILE`),
  o repositório só tem código. `state_setup` (início do `cmd_install`) cria a pasta; `state_purge` (fim do `remove`) a apaga.
  Compose com `${ASTRO_STATE}` nos volumes e `env_file`, rodado pela função `compose` (`--env-file`). Configuração que
  um programa espera noutro lugar fica no `$STATE` com um atalho (sunshine: `~/.config/sunshine`). Estado da máquina em `~/.astro/host.env` (`600`).
- Backup das configurações (rclone, 01:00, e "Fazer backup agora"): cada `~/.astro/<serviço>` em
  `<destino>/<AAAA-MM-DD_HHMMSS>/<serviço>/<serviço>.tar.zst.gpg`, versões apagadas depois de `CONFIG_KEEP_DAYS` (90).
  "Restaurar uma versão" (rclone, ação global, em Administração): para o rclone e segura as travas, salva a situação atual
  (`_antes-da-restauracao`) e chama `<projeto>/project.sh restore <pasta>`. Formato
  (gpg simétrico, senha em `~/.astro/rclone/data/config-backup.key`), com caminhos relativos ao serviço (`tar
  --transform`), sem home nem usuário. Cada projeto pode ter o comando `backup` (dumps e `exclude <caminho>`,
  `add <caminho>`).
- **Instalar Astro** sempre instala tudo, na ordem `ORDER` do `setup.sh` (`caddy` primeiro, pelo domínio; `discord` antes do
  `n8n`, que monta as credenciais das rotinas com o token do bot; `rclone` por último, por ver os outros), depois da atualização do sistema (primeira vez), da Máquina
  (`host_base`, uma vez só; os projetos não o chamam) e de "Discos da máquina". Um projeto que falha não para os
  outros; o resumo mostra quais falharam. Cada etapa roda em subshell com `set -e` (`run_step`) e só ganha a
  marca `~/.astro/.concluidas/<etapa>` ao terminar sem erro; no "Reinstalar Astro", um checklist com todas as
  etapas (concluídas com a data, as outras "pendente" e já marcadas) escolhe quais rodar; Esc volta sem rodar nada.
  Nos menus, Esc escolhe o último item quando ele é "Voltar" ou "Sair" (no inicial, fecha o assistente). A implosão apaga as marcas depois do backup.
- **Nomes das operações** (iguais em menus, avisos, logs, unidades e ajuda do Discord): `Backup: local ⬅️ nuvem`
  (download inicial), `Backup: local ↔️ nuvem` (mesclagem), `Backup: local 🔄 nuvem` (sincronização),
  `Backup: local ➡️ backup diário`, `Backup: configurações ➡️ local`, `Backup: configurações ⬅️ local` (restauração),
  `Máquina: estado`, `Serviço: iniciar/parar/reiniciar`. Comandos do Discord em inglês:
  `backup:cloud`, `backup:cloud-check`, `backup:cloud-force`, `backup:daily`, `backup:configs`,
  `machine:status`, `<projeto>:start|stop|restart`, `help`. A tabela completa fica no `README.md` da raiz.
- **Implodir Astro** (Administração): confirmação digitando `IMPLODIR`; backup `antes-de-implodir` pelo
  `rclone/run.sh config` (pasta e senha do rclone ou, sem elas, perguntadas: `ASTRO_BACKUP_DEST`/`ASTRO_BACKUP_KEY`),
  e nada é desfeito se ele falhar; `remove` de cada projeto na ordem inversa; `disk_release_all`; `host_undo`; rede
  `astro_default`; `~/.astro` (mantido se algum `remove` falhou). Ficam pacotes, dados dos discos e o SSH ativo.
  `remove` desfaz tudo o que é do projeto (não existe mais `--purge`) e não falha no que já não existe.
- Configuração por prompts, gravada em `~/.astro/<projeto>/.env` (permissão 600). "Usar a configuração já salva?" (`config_reuse`) reaproveita.
  Toda resposta passa por um validador de `lib/env.sh` (`is_port`, `is_ipv4`, `is_hostname`...), porque vai parar
  em `.env`, YAML, `sed` ou Caddyfile.
- **Trocar o domínio** (Administração): guarda os `.env` e `caddy/.routes` em `~/.astro/.troca-de-dominio/<data>/`,
  troca o sufixo `.<antigo>` só nas chaves de endereço (`CADDY_DOMAIN`, `PANEL_HOST`, `ADGUARD_REWRITES`,
  `COCKPIT_HOST`, `NEXTCLOUD_HOST`, `SUNSHINE_HOST`, `N8N_HOST`; `MAIL_ADDRESS` vira `<local>@<novo>`), nas rotas
  manuais e nos `.proxy` (e-mails pessoais e `ALLOWED_DOMAINS` ficam), e reaplica os projetos instalados afetados na
  ordem `ORDER` pelo `run_step`: `domain <antigo> <novo>` (adguard: reescrita no YAML e Split DNS exigido; sunshine:
  `csrf_allowed_origins` e rota) ou `install` com `ASTRO_REUSE_CONFIG=1`. Mostra antes os passos na Cloudflare
  e depois os de fora da máquina (Tailscale, apps do Nextcloud, favoritos, mailserver).
- Segredos nunca em argumentos de comando (aparecem no `ps`): senha para o `htpasswd` e token para o `curl`
  vão pela entrada padrão.
- Um projeto publica um endereço no Caddy com `proxy_publish` (escreve `~/.astro/<projeto>/.proxy` e recarrega o
  Caddy). Rotas manuais ficam em `~/.astro/caddy/.routes`; as de projeto têm prioridade sobre uma manual com o mesmo endereço.
- Discos de dados são **da máquina**, nunca de um projeto: "Discos da máquina" no `setup.sh` (`disk_manage`) os monta
  em `/srv/<rótulo>`, com quem instala como dono, `privado` (só ele) ou `compartilhado` (todos os usuários). As linhas no `fstab`/`crypttab` vêm depois de `# astro <uuid> <tipo>`. Projetos só escolhem caminhos de
  `disk_mounts` (Nextcloud com ACL para o `www-data` nos privados; rclone). Disco plugado de passagem fica com o
  padrão do Fedora (montado para quem está na tela) e é acessado de longe pelo Cockpit. **Nada pode pedir senha no boot** (a máquina é reiniciada de longe): LUKS só pelo TPM
  (PCR 7) com `headless=true`, e tudo com `nofail`.
- Versões fixadas: AdGuard na 1ª linha de `adguard/Dockerfile`; Caddy e `caddy-dns/cloudflare` em `caddy/Dockerfile`;
  Python e `discord.py` em `discord/Dockerfile`; Nextcloud, PostgreSQL e Valkey nas imagens de `nextcloud/docker-compose.yml`; Dovecot em `mailserver/docker-compose.yml`; n8n em `n8n/docker-compose.yml` e runners (mesma versão), `qrcode`, `pngjs`, `mupdf` e `zxing-wasm` em `n8n/Dockerfile`.

### Projetos

| Projeto | Resumo |
|---|---|
| adguard | Imagem customizada em **`network_mode: host`**. O entrypoint gera `AdGuardHome.yaml` do template se ele não existir. `.env` guarda só o **hash bcrypt** da senha. Reescritas `*.<domínio> → IP`. Configura o DNS da máquina, confere o Split DNS do Tailscale e publica o painel no Caddy (`PANEL_HOST`). |
| caddy | Let's Encrypt **curinga `*.<domínio>`** por DNS-01 na Cloudflare. O token precisa de **Zone:Read + DNS:Edit** na zona, sem expiração, e é validado na API ao instalar. Ações: listar, adicionar, remover e recarregar rotas. |
| cockpit | Pacotes do sistema (`cockpit`, `cockpit-podman`, `cockpit-storaged`, `cockpit-files`), não container. Arquivos e discos pelo navegador (com "Acesso administrativo", qualquer arquivo). `cockpit.conf` em modo proxy; porta 9090 bloqueada para a rede no firewalld (rich rule). Rota `<nome-da-máquina>.<domínio> → http://host.containers.internal:9090`. |
| discord | Bot em Python (`discord.py`, imagem customizada) sem acesso ao host: só monta `~/.astro/discord/fila` (`pedidos/`, `respostas/`, `saida/`, `tmp/`, `catalogo.json`; arquivos gravados em `tmp/` e movidos). Comando `/astro command:<projeto>:<ação> argument:<opcional>` (nomes sempre em inglês) com autocompletar do catálogo, registrado só no servidor do canal; botões com `custom_id` `astro\|run\|<ação>\|<arg>` tratados no `on_interaction` (sobrevivem a reinícios); ações com `sim` pedem confirmação. Só os IDs de `DISCORD_USERS`; menções desligadas. O catálogo guarda projeto, ação e tipo (`host`/`container`/`remote`) de cada comando; `remote-actions` com `:` no id dá um nome próprio (`backup:cloud`). `help` mostra `fila/ajuda.json`, montado das linhas do comando `help` dos projetos (`grupo|nome|o que é|quando|comando|ordem`) mais máquina e serviços, dividido em mensagens de até 1900 caracteres. O executor no host (`runner.sh`, `astro-discord-runner.path` com `DirectoryNotEmpty`) refaz o catálogo a cada rodada, recusa o que não está nele, roda `machine:status`, `<projeto>:start\|stop\|restart` (`podman start/stop/restart` em `astro-<projeto>*`, nunca o próprio bot) ou `<projeto>/project.sh remote`, com 10 min de limite. `notify_send` deixa o aviso em `saida/`. Canais: o principal (`DISCORD_CHANNEL`, comandos) e os só de leitura `#financeiro` (rotinas de contas no n8n, `canal_discord` no `⚙️ Configuração`), `#dados` (`rclone`) e `#sistema` (`astro-disk-check`, `mailserver`), criados ou ajustados pelo `channels.py` na instalação (mesma categoria do principal; `@everyone` sem enviar nem criar/escrever em tópicos, bot com ver/enviar/incorporar/histórico; IDs em `DISCORD_CHANNELS`); convite com `378225642512` (inclui gerenciar canais e permissões e as de tópicos, que o bot precisa ter para negar). Cada aviso leva `canal` (`NOTIFY_CHANNEL`, padrão `astro`); canal desconhecido ou fora do ar vai para o principal. Foto do bot = `logo/icone.png` (`PATCH users/@me`, só quando o hash em `.avatar` muda; 429 tenta na próxima instalação). |
| mailserver | Caixa só de entrada para automações, sem porta aberta: Cloudflare Email Routing num domínio sem outro e-mail (padrão `inbox@<domínio do Caddy>`; a instalação confere os MX do domínio do endereço pelo DNS: com `*.mx.cloudflare.net` segue, sem MX ativa pela API `POST zones/<zona>/email/routing/dns` (corpo `{}` no domínio da zona; `name` só para subdomínio, senão "must be a subdomains of") e espera os MX, com MX de outro serviço para; o `remove` desliga com `DELETE` no mesmo endereço) → Worker `astro-mailserver` (`worker.js`, publicado pela API) → KV `astro-mailserver` → `project.sh fetch` (timer do usuário de 5 em 5 min das 08:00 às 20:00, `flock`; só lista o KV se a chave `campainha`, gravada pelo Worker a cada e-mail, existir, e a apaga antes de listar; `fetch force` na ação manual, no Discord e na instalação) → `doveadm save` no container `astro-mailserver` (imagem oficial `dovecot/dovecot` 2.4). Worker: INBOX só com o primeiro `Authentication-Results` de `mx.cloudflare.net` com `spf=pass` ou `dmarc=pass` e o domínio do remetente do envelope em `ALLOWED_DOMAINS` (ação "Domínios autorizados": edita, republica o Worker e move da Quarentena o que for do domínio novo; `ALLOWED_SENDERS` antigo vira a lista dos domínios); o resto vai para a pasta `Quarentena`; a pasta vem do prefixo da chave no KV (`inbox.`/`quarentena.`), e o cabeçalho `X-Astro-Mailserver` só informa. Apaga do KV só depois de o Dovecot aceitar. Envio pelo mesmo Worker: `fetch` em `POST /enviar` (`workers.dev`, URL em `SEND_URL`; subdomínio da conta criado se faltar) com `X-Astro-Chave` = `SEND_KEY` (ligação `secret_text` `CHAVE_ENVIO`), corpo `{para[], assunto, texto, html, anexos[{nome,tipo,base64,cid}]}`, um `env.ENVIO.send` (ligação `send_email`) por destinatário, de `REMETENTE` (`MAIL_ADDRESS`), resposta `{enviados, erros}`; o base64 dos anexos vira bytes (`Uint8Array`) antes do `send` (com o texto base64 direto, as imagens chegavam quebradas); metadados do upload num arquivo temporário (segredo fora dos argumentos). Ação "Destinatários de e-mail": endereços de destino da conta (`accounts/<conta>/email/routing/addresses`: listar, `POST` cadastra e a Cloudflare manda a confirmação, `DELETE`); só os verificados recebem. Token próprio da Cloudflare (Workers Scripts, Workers KV Storage, Email Routing Addresses, Email Routing Rules, Zone Settings: Edit; Zone e DNS: Read). IMAP `31143` sem TLS só na `astro_default`; um usuário (`inbox`) num `passwd-file` (`data/users`, hash SHA512-CRYPT; senha gerada em `IMAP_PASSWORD`). Conta "Astro Inbox" no Nextcloud Mail do `NEXTCLOUD_USER` (`occ mail:account:create[-imap]` por PHP na entrada padrão, senha por variável de ambiente). Ação "Reprocessar e-mails" (escolhidos num checklist) e remota `mailserver:reprocess` (últimos 30 dias, com confirmação): cada e-mail da INBOX é copiado de novo como novo (`doveadm fetch text`, sem a linha `text:` do começo, → `doveadm save`) e a cópia antiga é apagada só depois, para o gatilho IMAP do n8n disparar outra vez. Ação remota `mailserver:fetch`. |
| n8n | Imagens oficiais `n8nio/n8n` e `n8nio/runners` (mesma versão), containers `astro-n8n` e `astro-n8n-runners` (executor externo do código dos fluxos, JavaScript e Python nativo; `N8N_RUNNERS_MODE=external`, token em `RUNNERS_TOKEN`). Sem porta no host: rota `n8n.<domínio> → http://astro-n8n:5678`, `N8N_PROXY_HOPS=1`. SQLite em `~/.astro/n8n/data/n8n`. Isolado da empresa ("Isolate n8n"): `N8N_DIAGNOSTICS_ENABLED`, `N8N_VERSION_NOTIFICATIONS_ENABLED` e `N8N_TEMPLATES_ENABLED` em `false`, `EXTERNAL_FRONTEND_HOOKS_URLS` e `N8N_DIAGNOSTICS_CONFIG_*` vazios; o assistente de IA vem desligado (sem `N8N_AI_ASSISTANT_BASE_URL`); o nó Execute Command fica no padrão da versão 2 (desligado). Administrador criado pela instalação (`N8N_INSTANCE_OWNER_MANAGED_BY_ENV`, reaplicado a cada início e travado na interface), senha só como hash bcrypt em `data/owner_password_hash` (gerado com o `bcryptjs` da própria imagem, senha pela entrada padrão). `N8N_ENCRYPTION_KEY` gerada uma vez no `.env` (sem ela, as credenciais do backup não abrem). Backup: `n8n export:entities` em `data/n8n/backup` com o n8n rodando, e o `database.sqlite*` fica de fora; restauração com o n8n parado, num banco novo, por um container avulso com `import:entities --truncateTables=true`. **Rotinas** só no banco do n8n (fonte de verdade; nenhuma no repositório), parâmetros num nó `⚙️ Configuração` de cada fluxo, histórico de versões nativo (`workflow_history`) e backup diário pelo `export:entities`; instalação do zero: a instalação avisa quando não há rotinas e "Restaurar uma versão" traz o n8n do backup. Credenciais com `id` fixo, montadas na instalação por `import:credentials` de um arquivo temporário no container (`astroImapInbox01` IMAP do mailserver, `astroDiscordBot01` bot do Discord, `astroNextcloud001` Nextcloud por senha de app `astro-n8n` do `occ user:auth-tokens:add -n`, `astroAnthropic001` `ANTHROPIC_API_KEY`, `astroEnvioEmail01` `SEND_KEY` do mailserver, `astroHookAstro001` `N8N_HOOK_TOKEN` dos webhooks chamados pelo astro); ação "Trocar a chave da API da Anthropic" (regrava todas); senha trocada noutro projeto pede reinstalar o n8n. Executor com imagem própria `localhost/astro-n8n-runners` que instala `qrcode`, `pngjs`, `mupdf` e `zxing-wasm` e copia o módulo `n8n/astro-qr` (`lerQrCodes(buffer, {tipo, senhas})`: desenha as páginas do PDF a 150/300 dpi pelo `mupdf`, abre com as senhas, e lê QR Codes pelo `zxing-wasm` com o `.wasm` local) para `/opt/astro/node_modules`; só `qrcode`, `pngjs` e `astro-qr` ficam liberados em `/etc/n8n-task-runners.json` (o `mupdf` tem `await` no topo e só carrega por `import()`, que o nó Code não faz). Ação remota `contas:email [AAAA-MM]`: `node` com `fetch` dentro do `astro-n8n` em `127.0.0.1:5678/webhook/astro-contas-email`, chave pela entrada padrão, devolve `mensagem`. Rotinas de contas em uso (no banco, editadas por export/patch/import com teste num n8n isolado): Contas: leitura (IMAP → sem PDF anexo, `🔗 Links do boleto` escolhe até 3 links pelo texto (boleto, fatura, 2ª via, visualizar...; descadastro e redes sociais fora; só `https` com nome de site, sem IP, porta, usuário ou nome interno, checado por expressão regular porque o executor não tem `URL`) e `⬇️ Baixar boleto` (HTTP, arquivo, só PDF) → `📎 Anexos` (todos os anexos: PDF com as senhas, imagens JPG/PNG/GIF/WEBP a partir de `imagem_minima` bytes (ícones ficam de fora), o resto vira aviso) → texto do PDF → `🧩 Juntar` por posição (devolve os binários ao `🧾 Montar pedido`, que lê com `this.helpers.getBinaryDataBuffer`) → Pix dos QR Codes de cada PDF e imagem pelo `astro-qr` antes da IA (só `000201...br.gov.bcb.pix`; vão prontos no texto, em `qr` por arquivo, e o `✅ Conferir` troca o Pix da IA pelo do QR do mesmo `anexo`; o Pix de muitos boletos e faturas, como Light e BTG, só existe na imagem do QR Code) → Claude `claude-haiku-5-5` com JSON schema (16.000 tokens de resposta, até 150 mil caracteres de texto dos anexos; PDF sem texto vai como `document` e imagem como `image`, em base64, mesmo com o QR lido, porque valor e vencimento só estão na imagem), inclusive `remetente_original` do encaminhamento; instruções: todo e-mail da caixa é do dono e confiável, cada código de pagamento é uma conta (vários por e-mail ou por PDF), documento com código é conta mesmo chamado de nota fiscal (DANF3E da Light) → DV/CRC sem IA (Pix com CRC errado é procurado no texto original por TLV + CRC, ignorando só os espaços: a IA tende a tirar os espaços do nome do recebedor) → `AAAA-MM.md` do mês de vencimento (sem ele, o do recebimento; agrupar pela emissão foi testado e desfeito a pedido), sem título, um bloco por conta: `**Conta**` (o tipo da despesa, nunca o nome de quem cobra: Claro → Internet, Light → Energia; a empresa vai nas observações), `**Titular**` (uma pessoa só, quem paga: campo Pagador/Sacado/Cliente/Titular/Consumidor, senão a saudação do e-mail; nunca o beneficiário nem o nome do condomínio ou edifício, que costuma ser nome de pessoa; sem aspas duplas nas instruções, que ficam num texto JS entre aspas duplas), `**Valor**`, `**Vencimento**` dd/mm/aaaa, `**Fonte**` (data - assunto - remetente original), `**Observações**`, linha em branco, imagem ` ![[pix-<hash>.svg|220]]` ou ` ![[boleto-<hash>.svg|420]]` e o código entre crases, linha em branco e `---`; dedupe pelo código; e-mail sem nenhuma conta vira um bloco `⚠️ revisar` no mês do recebimento; `⬆️ Salvar` com novas tentativas e `continueRegularOutput` (o n8n só repete quando o primeiro item falha), porque o Nextcloud trava o arquivo aberto em outro lugar (`Sabre\DAV\Exception\Locked`; o editor de texto do Nextcloud deixa a trava do app `files_lock` enquanto a aba fica aberta): um mês que falha não impede os outros e vira aviso no Discord com as contas que ficaram de fora; todo anexo não lido (senha, formato, tamanho) vai para o aviso) e Contas: notificação mensal (dia 5 às 08:00 e o webhook; sem mês, o atual; mesmo formato do arquivo em HTML, QR/barras em PNG por `cid` → Worker `/enviar`; Discord só no agendado). |
| nextcloud | Imagem oficial `nextcloud:<versão>-apache` + PostgreSQL + Valkey + container de cron (mesma imagem, `/cron.sh`). Sem porta no host: o Caddy chega em `astro-nextcloud:80` pela `astro_default`. Senha do banco em `~/.astro/nextcloud/data/secrets` (lida pelos `*_FILE`; arquivo `644` em pasta `700`, porque o Postgres lê como o usuário `postgres`). A imagem instala com uma senha aleatória, trocada pela digitada com `occ user:resetpassword --password-from-env`. `trusted_proxies`, `overwriteprotocol`, fuso, região e cron aplicados pelo `occ` a cada instalação. Discos: escolhidos em `disk_mounts` (caminhos em `DISKS`); nos privados, ACL (também padrão) para o UID do `www-data` no host (o `group::---` da ACL fecha o grupo); disco sem `container_file_t` na montagem fica de fora; volumes em `docker-compose.override.yml` gerado e pasta no Nextcloud pelo `files_external` (`filesystem_check_changes 1`). Visual do Astroverso pelo `occ theming:config` (nome, `primary_color` laranja solar, `background_color` + `background backgroundColor` azul espacial, `logo`/`logoheader` = `logo/simbolo.png`, `favicon` = `logo/icone.png`, por `podman cp` num temporário). `apache.conf` substitui o `000-default.conf` da imagem: `ServerName https://${NEXTCLOUD_HOST}:443` + `UseCanonicalName On` (redirecionamentos do `.well-known` em `https`) e HSTS. |
| rclone | Sem container: timers do systemd do usuário rodando `rclone/run.sh` (`tick` de 2 em 2 horas das 08:00 às 20:00, `config` 01:00, `local` 03:00: sincroniza e depois espelha no disco) com `ASTRO_PLAIN=1` e prioridade mínima (`Nice=19`, `CPUSchedulingPolicy=idle`, `IOSchedulingClass=idle`). Disco de backup escolhido em `disk_mounts` (`BACKUP_MOUNT`; `atual/` + `versoes/<data>`, `podman unshare rclone sync --metadata --backup-dir`). Nuvem pelo rclone, um destino por `data/targets/<nome>.env` e seção no `data/rclone.conf`; serviços em `providers/*.sh` (`provider_describe`, `provider_default_name`, `provider_options`, `provider_configure`). Nuvem ↔ disco por `rclone bisync` (conflito: o mais novo vence, o outro vira `.conflict1`; `--max-delete 5` em %; `--resync --resync-mode newer` na primeira rodada ou quando o estado se perde; `--force` pelo "Backup: local 🔄 nuvem (agora)" ou `backup:cloud-force`). Primeira cópia nuvem → disco agendável, retomada pelo `tick` até `IMPORT_DONE=yes`; antes disso nada vai para a nuvem. Nada roda sem o disco montado; `flock` entre rodadas (com ele na mão, as travas `*.lck` do bisync que um reinício deixou são apagadas). Avisos no Discord (`routine` no `run.sh`, só com `INVOCATION_ID`, ou seja, pelo systemd): início/sucesso silenciosos e falha para o `tick` (inclusive "Sincronizar agora" e a primeira cópia), o `config` e o `local`; rodada pulada pelo `flock` não avisa. |
| samba | Pacote do sistema (`samba`), não container. Bloco `[Public]` no fim do `/etc/samba/smb.conf` entre `# astro samba: inicio` e `# astro samba: fim` (`path = ~/Public`, `valid users = <quem instala>`, gravação; conferido pelo `testparm`, volta ao `.astro-bak` se falhar). SELinux: `semanage fcontext` `samba_share_t` em `~/Public(/.*)?` + `restorecon` (o `[homes]` do Fedora fica bloqueado pelo `samba_enable_home_dirs` desligado). Senha própria por `smbpasswd -s -a` (entrada padrão), perguntada (ou mantida) a cada instalação. `smb.service` (`smbd` no Debian) habilitado; serviço `samba` no firewalld. No mesmo bloco, um `[global]` com `multicast dns register = no`, `load printers = no` e `disable spoolss = yes`, e `[homes]`, `[printers]` e `[print$]` do Fedora com `available = no` (o Samba aceita repetir seções; vale o valor do fim do arquivo): sem anúncio por mDNS, que só valia em casa; o acesso é por `smb://<nome-da-máquina>.<domínio>/Public`, pelo AdGuard, em casa e pelo Tailscale. |
| sunshine | Acesso remoto à área de trabalho de quem instala pelo Moonlight. **Sunshine:** pacote do sistema baixado da última release no GitHub (SHA-256 conferido), não container; `setcap cap_sys_admin,cap_sys_nice+p` (captura KMS e prioridade alta na GPU); serviço de usuário habilitado (`systemctl --user enable`), sobe com a `graphical-session.target`. Login automático no GDM com quem instala e bloqueio logo depois (serviço de usuário `astro-sunshine-lock`, `WantedBy=graphical-session.target`: `loginctl lock-session` na sessão de `loginctl show-user -p Display`, a cada 2s até o `LockedHint`; o autostart do GNOME 50 rodava cedo demais e não bloqueava); bloqueio depois de 5 min parada (`idle-delay 300`, `lock-delay 0`, sem `idle-dim`); `astro-sunshine-awake` (`astro-sunshine-display awake`) reacende a tela pelo `PowerSaveMode` do Mutter sempre que o GNOME a apaga, e um drop-in sobe o Sunshine depois dele e do bloqueio; o Moonlight mostra a tela de bloqueio e destrava com a senha. Configuração em `~/.astro/sunshine/config`, atalho `~/.config/sunshine` (pasta real movida); backup sem `sunshine.log*`. Instala o driver NVIDIA (RPM Fusion + chave MOK no Secure Boot) e torna a NVIDIA a placa principal do GNOME (udev `mutter-device-preferred-primary`, GDM esperando a placa), com a extensão `org.freedesktop.Platform.GL.nvidia-<versão>//1.4` do driver carregado no Flatpak (as antigas saem). O codificador não é fixado: o Sunshine testa (NVENC primeiro) a cada stream; a instalação só avisa se não houver tela na saída da NVIDIA. Padrão: tampa fechada e plugue HDMI fantasma (ou monitor) no HDMI, que sai pela NVIDIA. Apps (`scripts/apps.py`): só Desktop, com a capa `logo/capa-moonlight.png` (copiada para `config/covers/desktop.png`), sem os de fábrica "Low Res Desktop"/"Steam Big Picture". `astro-sunshine-display` (Python + DBus do Mutter) no `global_prep_cmd` troca a tela, temporariamente, para a resolução exata do aparelho e volta no `undo`; nunca sai com erro. Painel `47990` bloqueado na rede, rota `https+insecure://host.containers.internal:47990`. O `remove` mantém o pacote e o driver. |

## Armadilhas conhecidas

- O podman-compose interpola `${...}` em valores do `.env`, **mesmo entre aspas simples**. Por isso a senha vira hash antes de ir para o `.env`.
- Chamar uma função em contexto `cmd || funcao` desliga o `set -e` dentro dela. Usar `if ! cmd; then funcao; fi`.
- Portas publicadas no Podman rootless passam pelo `rootlessport`, um repassador em espaço de usuário: o serviço
  vê todos os clientes como `10.89.0.x`, e respostas **UDP** a quem chega pelo Tailscale saem com o endereço de
  origem errado (o cliente descarta). Serviços UDP que atendem a rede, como DNS, usam `network_mode: host`.
- Container → serviço do sistema: `host.containers.internal`, com o serviço escutando em `0.0.0.0`. O IP da
  máquina só funciona para portas publicadas por outros containers. Do lado do serviço, a conexão chega como local.
- Rootless + porta < 1024: `net.ipv4.ip_unprivileged_port_start` (`host_unprivileged_ports`, arquivo `99-astro.conf`).
- O `systemd-resolved` com o DNS secundário do roteador fica preso no roteador depois de o AdGuard reiniciar
  ou subir atrasado no boot. A verificação `astro-dns-check` (adguard) reinicia o resolved quando isso acontece.
- Compose com `restart: always`, nunca `unless-stopped`: no desligamento, o Podman tenta reiniciar o container,
  falha, marca como "parado pelo usuário" e o `podman-restart` não o sobe no boot seguinte.
- O `tailscale0` não pertence a nenhuma zona do firewalld; interfaces sem zona caem na zona padrão, então as
  regras dela (inclusive os `reject` das portas 8080 e 9090) **provavelmente** valem também para quem chega pelo
  Tailscale. Não confirmado: testar de um aparelho remoto. Rotas `~dominio` do Split DNS mandam as consultas
  para o servidor do Split DNS.
- O `akmod-nvidia` puxa o `kernel-devel` (e o kernel) mais recente do repositório: numa máquina desatualizada, o
  módulo é compilado para o kernel novo, que só entra no boot seguinte. `host_nvidia_version` procura o módulo
  em todos os kernels. A pasta `/etc/pki/akmods/certs` só é legível pelo root (`sudo` no `test` e no `mokutil`).
- `firewall-cmd --state` pede autorização do polkit a usuários comuns (as consultas `--query-*` não): para saber
  se o firewalld está ativo, usar `systemctl is-active -q firewalld`.
- O `libva-intel-media-driver` do Fedora não codifica H.264/HEVC; o `intel-media-driver` do RPM Fusion, sim.
- Sem `capture = kms`, o Sunshine consulta o portal do GNOME (RemoteDesktop) ao iniciar: abre uma janela de
  permissão na tela e fica parado sem abrir o painel (porta 47990), ou trava.
- O painel do Sunshine só aceita alterações de `https://localhost`: atrás do Caddy, a origem precisa estar em
  `csrf_allowed_origins` (lista separada por vírgula, cada item com `https://`).
- O GNOME escolhe a placa principal ao iniciar; o `nvidia-drm` aparece ~2s depois do GDM no boot, e o GNOME fica
  com a Intel (log "selected primary from builtin panel presence"). Sem tela na NVIDIA, o NVENC falha e o
  Sunshine cai no Vulkan, que codifica na NVIDIA a tela capturada da Intel: imagem corrompida. O GDM espera o
  `/dev/dri/by-path/pci-<placa>-card` (`udevadm wait`, drop-in `astro-nvidia.conf`).
- O pacote do Sunshine não aplica o `setcap`, e uma atualização do pacote apaga a permissão.
- Com a NVIDIA como placa principal do GNOME, todo app Flatpak que desenha pela placa (ex.: Bazaar) precisa da
  extensão `org.freedesktop.Platform.GL.nvidia-<versão>` igual à do driver carregado; sem ela, fecha com "Lost
  connection to Wayland compositor". Depois de uma atualização do driver, a antiga não serve.
- O Sunshine (KMS) não captura uma tela apagada (`PowerSaveMode` do Mutter diferente de 0): ao iniciar, dá
  "Mismatch ... 0x0" e "Unable to initialize capture method", perde o `CAP_SYS_ADMIN` e não se recupera até
  reiniciar; numa conexão, testa os codificadores antes do `global_prep_cmd`. Com a sessão bloqueada, o GNOME
  apaga a tela depois de segundos parada. `Set` no `PowerSaveMode` pelo DBus acende a tela de novo, e ela só volta
  a apagar depois de alguma atividade.
- Com Secure Boot, o IMA do kernel registra no TPM cada módulo carregado no boot, e o desbloqueio pelo TPM recebe
  `TPM_RC_PCR_CHANGED` (0x128) e tenta de novo até o boot acalmar (~1 min). Por isso a montagem de disco LUKS
  espera o serviço do `cryptsetup` (`x-systemd.requires=`, 5min) em vez de 10s pelo dispositivo.
- Propagação `rslave` não traz para dentro do container uma montagem feita depois que ele subiu (Podman rootless).
  Por isso o disco monta antes do gerenciador do usuário (`x-systemd.before=user@<uid>.service`).
- Armazenamento externo criado pelo `occ` não vê arquivos gravados por fora até
  `files_external:option <id> filesystem_check_changes 1`.
- Com ACL padrão, o `umask` é ignorado e a máscara vem do modo de criação: quem cria arquivos `0644` corta a
  escrita do outro lado. A maioria dos programas cria `0666` (ok).
- Com ACL, o `chmod` mexe na máscara (os bits do grupo): um `chmod 700` depois do `setfacl` zera a máscara e corta
  as permissões extras. Pasta com ACL usa `chmod 770` (o `group::---` continua sem acesso).
- O `ntfs3` usa a permissão gravada no disco (atributos `$LXMOD` do WSL) no lugar do `umask`/`dmask`: a pasta
  principal pode aparecer `777`. Um `chmod` fica gravado no disco e vale nas próximas montagens. Com `acl` (padrão
  no kernel atual), ele também guarda dono e ACL POSIX de verdade nos arquivos criados pelo Linux (testado com o
  `www-data` de um container); os vindos do Windows seguem `uid`/`gid`/`umask` da montagem.
- `nofail` tira a ordem do disco antes do `local-fs.target`: quem precisa do disco montado antes declara
  (`x-systemd.before=user@<uid>.service` para containers, `systemd-user-sessions.service` para qualquer login).
  Pôr todos antes dos logins faria o SSH e o login automático esperarem o TPM (~1 min) nos discos LUKS.
- O rótulo de um disco LUKS fica dentro da criptografia: travado, o `lsblk` só mostra o rótulo do cabeçalho LUKS2
  (vazio por padrão). O `disk_setup` copia o rótulo de dentro para o cabeçalho ao destravar.
- `x-systemd.wanted-by=` no `fstab` tira a montagem do `local-fs.target` (anula o `nofail` e a ordem do boot).
  Para remontar ao religar, o `disk_setup` cria links em `/etc/systemd/system/<dispositivo>.device.wants/`. No LUKS,
  a montagem fica no `.wants` do serviço do `cryptsetup` (que o disco dispara): o link no dispositivo de dentro
  (`/dev/mapper`) não montava ao religar a gaveta.
- `find -name` usa glob: nomes de unidade com `\x2d` precisam da barra escapada (`${nome//\\/\\\\}`).
- `tar` aplica os `--exclude` também aos caminhos da linha de comando: para incluir algo dentro de uma pasta
  excluída (ex.: `data/html/config` do Nextcloud), anexar numa segunda passada (`tar -rf`).
- Num comando do Bash, um texto com "rm -rf" (mesmo dentro de um heredoc de edição) é barrado pela proteção do
  Claude Code: editar esses trechos com a ferramenta de edição.
- O Nextcloud cria na instalação um usuário próprio no Postgres (`oc_<admin>`, senha no `config.php`). O
  `pg_dump` de um banco não leva usuários: a restauração recria o usuário antes do `pg_restore` (sem
  `--no-owner`). O superusuário da imagem é o `POSTGRES_USER` (`nextcloud`); o papel `postgres` não existe.
- Um `flock` segura enquanto houver um processo com o descritor aberto: comandos que sobem containers não podem
  herdar a trava (`7>&- 8>&-`), senão o container a segura para sempre.
- Em teste com outro `HOME`, o Podman rootless passa a usar outro armazenamento de imagens: manter
  `XDG_DATA_HOME`, `XDG_CONFIG_HOME` e `XDG_RUNTIME_DIR` reais e apontar só o `~/.astro` (e as travas) para o
  scratchpad. E desativar o Caddy da cópia: o `proxy_reload` acha o container real pelo nome.
- `local -n ref=$1` com uma variável local do mesmo nome que a do chamador (ex.: `path`) faz a referência apontar
  para a local: funções com nameref usam só variáveis internas com prefixo (`__ui_`).
- Editar vários `project.sh` por substituição de texto: `case "${1:-}" in` aparece também dentro de funções (ex.:
  `cmd_action`). Ancorar na linha seguinte (`    describe) cmd_describe ;;`), senão a função entra no lugar errado.
- `lsblk -J` só devolve a árvore (`children`) com `--tree` ou a coluna `NAME`.
- `$(...)` cujo último comando é `((n)) && ...` com `n=0` sai com 1 e, numa atribuição, derruba o `set -e`.
- `journalctl --user -u <padrão>` sai com 1 quando nenhuma unidade tem mensagens: em pipeline com `pipefail`, `|| true`.
- `find -cmin`/`-newerct` usa a data de mudança no disco: pega também arquivos copiados com data antiga (o
  `--max-age` do rclone, que olha a data do arquivo, não pegaria).
- `tailscale status --json` usa indentação de 2 espaços (a extração do bloco "Self" depende disso).
- O firewall do Fedora Workstation libera as portas TCP/UDP de 1025 a 65535 para a rede local. O `--query-port` diz que
  uma porta dentro dessa faixa está aberta, e o `--remove-port` dela parte a faixa (fecha a porta): para desfazer, só
  tirar o que aparece exatamente em `--list-ports` (`host_firewall_remove`).
- O udisks (app Discos, Armazenamento do Cockpit) regrava as linhas do `fstab`/`crypttab` que ele edita (ex.:
  `auto noauto`) e pode separá-las da marca `# astro`. O `lib/disk.sh` reconhece as linhas do Astro também pela
  assinatura (`fstab`: destino em `/srv/` com `x-udisks-auth` e `container_file_t`; `crypttab`: `luks-*` com
  `headless=true`) e só emparelha marca e linha quando a linha tem o UUID da marca (`\x2d` no LUKS).
- A tela de login (GDM) tem a própria configuração de energia e, no padrão do Fedora, suspende depois de ~15 min
  sem ninguém logado, mesmo na tomada. O `host_no_sleep` grava `/etc/dconf/db/gdm.d/95-astro-power` (`dconf
  update`); com os alvos mascarados, ela só mostra "The system will suspend now!" e o logind recusa.
- Arquivos gravados pelo Nextcloud num disco (ex.: envio de fotos do celular) ficam com o `www-data` do container
  como dono (`524320` no host). A ACL deixa quem instala gravar, mas só o dono muda a data (`chtimes: operation
  not permitted`): o rclone da nuvem roda por `podman unshare` (`rclone_owner`), como o espelho do disco.
- O Brave e o Chrome no Linux ignoram as CAs do sistema (usam o repositório NSS próprio).
- `rclone bisync` com `--resilient` não pede `--resync` quando as listas somem ("cannot find prior Path1 or Path2
  listings"): tenta para sempre. O `run.sh` detecta essa mensagem e a de "must run --resync" e faz a junção.
- `IFS=$'\t' read` junta campos vazios seguidos (tab é espaço em branco para o `IFS`) e desloca os valores.
  Para campos que podem vir vazios, separar com `\x1f`.
- `${texto: -N}` devolve vazio quando o texto tem menos de N caracteres: testar o tamanho antes.
- Discord: desligar "Public Bot" exige "Install Link: None" na aba Installation do aplicativo. O link de convite
  com `client_id` continua funcionando para o dono.
- `rclone bisync --dry-run` também para no `--max-delete`: para mostrar o que seria apagado, usar `--force`.
- O repositório do Tailscale para RHEL e derivados é `rhel/<versão>`; para Fedora é `fedora`. No apt, derivados usam o `UBUNTU_CODENAME`.
- A imagem `dovecot/dovecot` 2.4 traz um `passdb static` que aceita qualquer usuário com a senha de `USER_PASSWORD`
  (padrão `{CRYPT}*`, que nunca confere): basta não definir a variável e somar um `passwd-file`. Sem
  `auth_allow_cleartext = yes`, o login sem TLS vindo de outro container é recusado. A imagem não tem shell útil
  (`ls`, `cat`, `id` não existem).
- Um disco LUKS montado e em uso (ex.: pelo Nextcloud) que desconecta e volta (gaveta USB) deixa o mapeamento
  `/dev/mapper/luks-*` preso ao aparelho que sumiu: o `systemd-cryptsetup` não consegue fechá-lo ("Device or resource
  busy") e, na volta, acha o volume "already active". A montagem continua em `/srv`, mas toda leitura dá
  `Input/output error` (o `ls -ld`, o `getfacl`), até a máquina reiniciar. `disk_responds` detecta isso (dispositivo
  por baixo do `dm` sumiu ou a raiz não é lida), o `astro-disk-check` avisa no Discord e o Nextcloud deixa o disco
  de fora em vez de falhar. Sem o disco montado, `ls /srv/<rótulo>` lista a pasta vazia e imutável, sem erro:
  conferir com `mountpoint -q`.
- `n8n import:entities --truncateTables=true` falha com "Deployment keys must not be deleted" num banco já
  usado (com o n8n rodando ou não): só funciona num banco novo, sem `database.sqlite`. Uma importação que falha
  deixa os `.jsonl` extraídos na pasta. O `n8n execute` pela linha de comando briga pela porta 5679 do executor de
  código com o n8n rodando.
- A API WebDAV do Nextcloud não cria pastas encadeadas (`MKCOL` de `a/b` com `a` ausente dá 404): criar nível a
  nível. A credencial `nextCloudApi` do n8n monta `<webDavUrl>/<caminho>`, sem barra no fim do `webDavUrl`.
- Webhook do n8n com `responseMode: lastNode` responde 500 ("No item to return was found") se o último nó não
  devolver item: o fluxo termina num nó que sempre devolve um item. O Gmail não mostra imagens SVG: e-mail usa PNG.
- `occ user:auth-tokens:add -n <usuário>` cria uma senha de app sem a senha de login (capacidades limitadas, mas o
  WebDAV funciona) e imprime o token sozinho na última linha.
- No n8n, `import:credentials` aceita `data` em texto aberto e criptografa com a chave da instalação; com o mesmo `id`,
  atualiza. Nós com `onError: continueRegularOutput` mantêm a contagem de itens, e o `Code` pode casar itens de nós
  anteriores pelo índice (`$('Nó').all()[i]`). Um `Set` com `includeOtherFields` e `includeBinary` passa os anexos
  adiante.
- O executor de JavaScript do n8n (`n8nio/runners`) só deixa o `Code` fazer `require` dos módulos listados em
  `NODE_FUNCTION_ALLOW_EXTERNAL`, e esse valor vem do `env-overrides` de `/etc/n8n-task-runners.json` (variável de
  ambiente não basta): a imagem própria edita o arquivo. A imagem não tem `npm`, só `pnpm`
  (`--config.node-linker=hoisted`); o `NODE_PATH` é repassado ao executor.
- O `occ` só aceita senhas como argumento (ex.: `mail:account:create-imap`). Para não expô-las no `ps`, rodar o
  `console.php` por um script PHP na entrada padrão (`podman exec -i -e VAR ... php`), com `$_SERVER["argv"]`
  montado lá dentro e a senha lida por `getenv`.

## Pendências e ideias combinadas

- Segurança:
  - revisar as ACLs do Tailscale (hoje "todos acessam tudo" e a rede inteira está anunciada);
  - conferir no roteador se não há DMZ, UPnP ou redirecionamento de portas.
- Discord: avisos e comandos de outros projetos (ex.: DNS do AdGuard fora, renovação do certificado do Caddy,
  consultas bloqueadas). Outros canais (e-mail por SMTP, Telegram), se precisar.
- Contas a pagar: as rotinas `Contas: leitura` e `Contas: notificação mensal` existem no banco do n8n
  (`Contas: lembretes`, avisos diários de vencimento, foi desligada: só o resumo do dia 5). Ideias: marcar como paga pelo Discord (botão), histórico/relatório mensal.
- Migrar para o n8n o que for "cola" entre serviços (conversa pendente com o usuário: mais controle das rotinas
  sem programar). Os comandos `/astro`, os botões e o executor no host ficam no bot do Discord.
- Projeto `tunnel` (combinado, para quando houver um uso concreto de webhook): `cloudflared` em container, túnel
  da Cloudflare publicando só `/webhook/` do n8n num nome próprio (ex.: `hooks.<domínio>`), editor e API só na rede
  local, webhooks com autenticação e regras da Cloudflare na frente. Exige manter o n8n atualizado.
  Combinado: quando o `tunnel` existir, trocar também a busca do `mailserver` por entrega direta (Worker → `POST`
  em `hooks.<domínio>/mailserver` com credencial de serviço do Cloudflare Access → túnel → receptor
  `astro-mailserver-hook` que grava na caixa pelo IMAP), mantendo o KV com a campainha e a busca das 08:00 às 20:00
  como reserva para quando a máquina estiver fora do ar.
- Bloqueio opcional no AdGuard dos domínios da n8n usados para telemetria, como segunda camada do isolamento
  (levantar os domínios no código da imagem antes; não bloquear o site e a documentação).
- Ação "verificar atualizações" para as versões fixadas.
- Ações de pós-configuração no adguard (ex.: gerenciar reescritas).
