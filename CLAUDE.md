# CLAUDE.md

Regras para desenvolver o Astroverso. O contexto da instalação atual (máquina, IPs, domínio, contas) fica em
`CLAUDE.local.md`, fora do git.

## Situação

O Astroverso está sendo refeito como monorepo. O código antigo (o antigo Astroverso Homelab) fica em `legacy/`,
só como referência: nada roda de lá e nada novo depende dele. Cada parte é migrada para `apps/` ou `packages/`,
um pedaço por vez. As regras e armadilhas antigas ficam em `legacy/CLAUDE.md` e voltam para este arquivo quando
o app ou pacote delas for migrado.

## Nomes

- O projeto é o **Astroverso**. O codinome técnico é `astroverso` em tudo que identifica o sistema: comando,
  `~/.astroverso`, containers, imagens, rede, unidades systemd, variáveis `ASTROVERSO_*`, marcas em arquivos do
  sistema, sufixo `.astroverso-bak`, recursos da Cloudflare, prefixo `[astroverso]` dos logs e rótulos dos menus.
- **`astro` é só o bot do Discord**: o nome do bot, o comando `/astro`, o `custom_id` `astro|...` e o canal do bot.
  Todo o resto é `astroverso`, inclusive o usuário padrão dos apps.
- **Vocabulário das cópias** (decisão do usuário: uma palavra, um sentido; nada de "backup" para outra coisa):

  | Termo | Sentido |
  |---|---|
  | backup | só o conceito de guardar uma cópia de segurança ("backup da configuração", "Fazer backup agora") |
  | vault | o app que liga a máquina à pasta dos backups no Nextcloud |
  | versão | cada backup datado de um app ("Restaurar uma versão") |
  | fotografia | o resultado: a cópia de um disco inteiro gravada no disco de fotografias (app `disks`: `atual/` + `versoes/`) |
  | fotografar | o ato de tirar a fotografia ("Fotografar agora", toda noite às 03:00) |
  | agendamento | a configuração "fotografar o disco X no disco Y toda noite" ("Agendamentos de fotografia") |
  | espelho | o `atual/` da fotografia, igual ao disco de origem |
  | sincronização | as duas vias do `cloud` |
  | `legacy/` | o código antigo |

## Como trabalhar

- Responder sempre em **português do Brasil**, de forma direta.
- **Micro commits.** Desenvolver um pedaço pequeno por vez: primeiro descrever a arquitetura daquele pedaço e
  esperar a aprovação do usuário, depois implementar. Depois de aprovado, fazer commit e push sem perguntar.
  Mensagens em português, terminando com a linha `Co-Authored-By` da sessão.
- **Sem comentários nem docstrings no código.** Mensagens de log, sim, bem formatadas.
- Toda mensagem na tela usa o prefixo do projeto ou do app (`[astroverso]`, `[adguard]`...), inclusive prompts,
  o prompt do `sudo` e os logs de dentro dos containers. Usar o `kit.ui`, nunca `print` (nem `echo`) solto.
- **Bonito e amigável.** O instalador e o gerenciador cuidam do visual: cores da marca conforme o contexto e o
  logo na abertura, sempre com uma saída sem cor legível (journal, `NO_COLOR`).
- Preferir o caminho simples e remover etapas desnecessárias.
- **Tudo funciona pela rede local**, mesmo com o Tailscale conectado. Não sugerir o IP do Tailscale como
  caminho de acesso.

## Linguagem

- **Python 3.11 ou mais novo, só a biblioteca padrão.** Nada de `pip`, venv ou build: clonar e rodar.
- **sh só onde não há alternativa:** o script de entrada `astroverso` (confere o `python3` e chama o programa) e
  os entrypoints dos containers.
- Exceção: os módulos do n8n (`apps/n8n/modules/<módulo>/`) são APIs em containers próprios e podem instalar
  dependências dentro da imagem (`pip` com versões fixadas no `Containerfile`). O código que roda na máquina continua só
  com a biblioteca padrão.
- Comandos do sistema só pelo `kit.run` (`cmd`, `capture`, `succeeds`), com a lista de argumentos.
- Anotações de tipo em tudo.
- Testes com `unittest`, na pasta `tests/` de cada pacote ou app. Todos os pacotes de uma vez:
  `python3 -m unittest discover -s packages -t packages`.
  Menus e prompts são testados por `pty` dentro dos próprios testes.
- O script de entrada põe `packages/` no `PYTHONPATH`; os apps importam assim: `from kit import ui`.

## Alvo

- **Fedora Server**, sem interface gráfica. Acesso remoto só pelo Cockpit e pelo SSH.
- Outras distribuições virão depois: nenhum app chama o gerenciador de pacotes, o firewall ou o systemd do
  sistema diretamente. Tudo passa pela camada `kit.distro` (`install`, `firewall_open`,
  `service_enable`...), com um módulo por distribuição (`packages/kit/distro/fedora.py`). Distribuição sem
  módulo: a instalação para no início com "distribuição não suportada".
- O Astroverso não depende de uma máquina específica: qualquer máquina instala só os apps que quiser.

## Arquitetura

```
apps/<app>/       serviços autônomos (adguard, nextcloud...)
packages/<pacote>/ código compartilhado pelos apps (kit, manager...)
legacy/           código antigo, só referência
```

### Apps

- **Autônomos.** Um app não conhece nenhum outro app: não cita `apps/<outro>`, não lê `~/.astroverso/<outro>`
  e não depende de ordem de instalação nem de uma etapa prévia da máquina. Depende só de `packages/`.
- Cada app instala as próprias dependências, pela camada `kit.distro`.
- **Endereço.** Todo app com interface na rede tem uma etapa de endereço: `<serviço>.<domínio>`. O domínio é
  perguntado pelo `kit` na primeira instalação e gravado em `~/.astroverso/astroverso.env`; os apps seguintes já
  trazem esse domínio como padrão.
- **Containers por Quadlet** (`kit.container`): cada container é uma unidade do systemd do usuário
  (`~/.config/containers/systemd/<nome>.container`), com início no boot e reinício em falha, sem podman-compose
  nem podman-restart. Nome `astroverso-<app>` (`astroverso-<app>-<parte>` quando houver mais de um), na rede
  `astroverso` (ou na do host, quando precisar), imagem oficial com a versão fixada no código do app.
- **Estado fora do repositório:** tudo o que a instalação gera fica em `~/.astroverso/<app>`; o repositório só
  tem código.
- **README com a tabela de mudanças.** Todo `apps/<app>/README.md` tem uma tabela **Mudança | Por quê** com
  cada mudança que o instalador faz (pacotes, serviços, portas, arquivos do sistema, contas, estado) e outra com
  os passos fora da máquina. Ela é atualizada no mesmo commit de qualquer mudança no instalador.
- **Mudanças no sistema pelo `kit.changes`** (veja a seção "Mudanças no sistema").
- **Passos em terceiros vão para docs.** Configuração em plataforma externa (Tailscale, Cloudflare, Discord,
  roteador, outro computador) tem o passo a passo em `apps/<app>/docs/<plataforma>.md`; o instalador mostra só uma
  frase com os valores desta máquina e o link (`ui.link` + `kit.docs.link`). Explicações do próprio Astroverso
  continuam como `ui.note`.
- **Backup das configurações: cada app manda o seu.** Cada app implementa `backup(pasta)` e `restore(pasta)` e usa o
  `kit.vault`: a mudança perguntada `kit.vault.change(APP)` (timer diário próprio) e as ações "Fazer backup agora"
  (`run_backup`) e "Restaurar uma versão" (`restore`). Nenhum app varre os outros. Sem o vault ligado na
  máquina, o backup só avisa e segue.

### App `network`

Tailscale, AdGuard e Caddy num app só, sempre os três juntos (`apps/network/`, um arquivo por parte). Decisões:

- O servidor anuncia no Tailscale **só o próprio IP** (`<ip>/32`), sem encaminhamento nem masquerade: o Split DNS
  aponta o domínio para o IP local, e o Caddy repassa pela rede local para os outros aparelhos (painéis web de
  roteadores e PCs entram como endereços do Caddy, nunca como rotas do Tailscale).
- O servidor não aceita rotas de outros aparelhos (`--accept-routes=false`): uma rota anunciada por outro aparelho
  desviaria pelo Tailscale o tráfego da própria rede local.
- Pacote dos repositórios da distribuição; o `remove` desinstala o pacote e tira a máquina da conta.
- Perguntas explicadas para quem não conhece o projeto (`ui.note` antes de cada etapa) e a ação "Resumo da rede"
  em tabelas, que ganha as partes do AdGuard e do Caddy quando elas chegarem.
- AdGuard: imagem oficial na rede do host, escutando no IP da rede e no `127.0.0.1`; o servidor pergunta a ele só
  pelo `~<domínio>`; o roteador entrega aos aparelhos o AdGuard **e um DNS secundário** (nunca sem DNS).
- Caddy: imagem local com o módulo da Cloudflare, cadeado curinga `*.<domínio>` por DNS-01; painéis web de
  aparelhos da rede entram como endereços (nome, IP, porta), nunca como rotas do Tailscale.
- Os outros apps publicam endereços pelo `kit.routes` (`~/.astroverso/routes/<app>.json`, pasta de nenhum app); a
  unidade `astroverso-network-routes.path` recarrega o Caddy a cada mudança.
- Verificação de hora em hora (`astroverso-network-watch.timer`): avisa pelo `kit.discord` só quando um problema
  aparece, piora ou se resolve (estado em `watch.json`).

### App `discord`

- Uma máquina roda o bot (container com `discord.py` e a API v1, em `discord.<domínio>` pelo `kit.routes`); as outras
  instalam o mesmo app no modo cliente. Cliente = máquina (ou projeto de fora, como o studio), com chave própria.
- O bot descobre o servidor em que foi convidado, cria a categoria **Astroverso** com `#astro`, `#sistema` e um canal
  por app (no primeiro aviso). O dono do servidor é sempre autorizado.
- Apps avisam pelo `kit.discord.notify(app, nível, título, ...)`: o padrão visual (nível, cor, menção no `erro`) é
  do bot, igual para todas as máquinas. Sem Discord configurado, o aviso é ignorado.
- Ações com `remote=True` viram comandos `/astro <app>:<id>`: o agente (`astroverso-discord-agent.service`, em toda
  máquina com o app) publica o catálogo e roda `astroverso <app> action <id>` sem terminal. Ações remotas nunca
  perguntam nada.
- A API v1 é contrato com projetos de fora: campos novos são opcionais; para quebrar, `/v2`.
- Testar só com outro nome de container e sem o token real: dois processos com o mesmo token recebem os mesmos
  cliques.

### App `nextcloud`

- Quatro containers por Quadlet (Nextcloud apache, Postgres, Valkey sem disco, cron com `/cron.sh`), sem porta na
  máquina, endereço pelo `kit.routes`. Sem tema do Astroverso (decisão do usuário: o logo fica só no projeto por
  enquanto).
- **"Qual é o disco do Nextcloud?"** (decisão do usuário: o Nextcloud assume um disco inteiro, sem escolher pasta): os
  arquivos ficam em `/srv/<disco>/nextcloud` (ou `~/Nextcloud` no disco do sistema), do `www-data` do container
  (`podman unshare chown 33:33`), sem armazenamento externo para eles. A ação "Trazer uma pasta
  para o Nextcloud" move uma pasta para os arquivos de um usuário e roda o `files:scan` só dela. A instalação para
  sem o disco, e a verificação avisa quando ele some.
- **Outros discos** (`drives.py`, decisão do usuário): os outros discos montados aparecem em `/Discos/<disco>` só para o
  administrador, por armazenamento externo Local (`files_external`), montados nos containers em `/srv/<disco>` sem `z`
  (o `context=` do `fstab` já põe o rótulo; reetiquetar o disco inteiro seria lento). O disco de fotografias entra só
  leitura (montagem `ro` + `readonly`). A verificação reinicia o Nextcloud quando um disco voltou depois do container
  (o `st_dev` dentro e fora difere).
- Senhas por arquivo (`*_FILE`) em `~/.astroverso/nextcloud/secrets/` (`644` dentro de pasta `700`: o Postgres lê
  como outro usuário do container). A senha do administrador entra por `occ user:resetpassword --password-from-env`.
- `backup`/`restore` implementados (dump SQL + `config/`), mandados pelo `kit.vault`.

### App `mail`

- Caixa só de entrada para automações (Cloudflare Email Routing → Worker `astroverso-mail` → KV → busca de 5 em 5 min
  com "campainha" → Dovecot `astroverso-mail`) e envio agnóstico pelo mesmo Worker (`kit.mail.send`, de qualquer
  máquina com o endereço e a chave; só para destinatários confirmados na conta da Cloudflare).
- Modos: caixa (uma máquina) e só envio. Token próprio da Cloudflare com sete permissões (`docs/cloudflare.md`).
- A caixa é publicada em `~/.astroverso/mailboxes/` (`kit.mailboxes`); o Nextcloud cria a conta no Mail sozinho
  (decisão do usuário: apps separados, ligados pelo contrato, como o Caddy e os endereços).
- O Remover não apaga os e-mails da caixa sem confirmação (padrão não).
- Recursos antigos da Cloudflare não têm nome no código: a ação "Limpar Workers e KV antigos" lista os da conta e
  apaga os marcados.

### App `vault`

- O backup de cada app é um arquivo por dia (`podman unshare tar --zstd` + `gpg` simétrico com a senha dos backups),
  enviado pelo WebDAV para uma pasta do Nextcloud com uma senha de app (decisão do usuário: os backups vivem dentro do
  Nextcloud, que é o NAS). Nunca gravar direto na pasta dos arquivos do Nextcloud: ele não veria o arquivo e o dono
  ficaria errado.
- Caminho `<pasta>/<máquina>/<AAAA-MM-DD>/<app>.tar.zst.gpg`, 90 dias. O WebDAV é só `urllib` (sem rclone), com as pastas
  criadas nível a nível.
- O app `vault` só guarda a ligação (`~/.astroverso/vault.env`) e a senha dos backups; cada app manda o seu pelo
  `kit.vault` às 01:MM. Nenhuma pergunta de pasta nos apps.
- Os arquivos do Nextcloud e os discos não entram: ficam com a fotografia do disco (app `disks`).
- Os backups não levam a senha de app nem a senha dos backups.

### App `cloud`

- rclone do pacote da distribuição, sem container. Contas por provedor (um módulo cada; por enquanto `proton.py`),
  com a senha ofuscada no `rclone.conf` do app (`600`) e o código das duas etapas só no login, por variável de ambiente.
- Só sincronizações de duas vias (decisão do usuário: sem envios de uma via): `bisync` de 2 em 2 horas, das 08:00 às
  20:00 (fora da madrugada dos backups e da fotografia), o mais novo vence, `--resync --resync-mode newer` na primeira
  rodada ou quando o estado se perde, trava de 5% de exclusões. "Liberar exclusões" mostra a lista e roda com `--force`.
- O destino é escolha do usuário, sem regra nem validação. O `cloud` publica as pastas ligadas pelo `kit.clouds` só
  para a marca ☁ nos seletores.
- A pasta pode ficar "Dentro do Nextcloud": o Nextcloud entra como conta (WebDAV; a mesma conexão do `kit.vault`, com
  confirmação, ou uma senha de app) e a pasta sincroniza pelo Nextcloud, nunca pela pasta dos arquivos dele (o seletor
  recusa uma pasta com `.ncdata`/`.ocdata` acima: o Nextcloud não veria as mudanças e os donos ficariam errados).
- Roda por `podman unshare` (arquivos de containers), com trava entre rodadas e sem rodar com o disco indisponível.
- O backup do app não leva as senhas: na restauração, cada conta pede o login de novo.

### App `disks`

- Monta os discos de dados em `/srv/<nome>` pelo `fstab`/`crypttab` (linhas depois de `# astroverso <uuid>`), sempre
  só do usuário (decisão do usuário: sem o modo compartilhado do antigo, que existia para o usuário dos jogos).
  Formatar disco fica no Cockpit (exceto o Resgatar um disco).
- **Nada pode pedir senha no boot**: LUKS só pelo TPM (PCR 7), com a senha digitada uma vez; sem TPM, o disco fica
  de fora.
- Cada disco cadastrado (`~/.astroverso/disks/disks.json`) é uma Change ⚠: desfazer só desmonta e tira as linhas;
  descadastrar em "Discos da máquina" também descadastra o TPM.
- Os outros apps leem pelo `kit.disks` (o `fstab` é o contrato): `mounts()`, `available(pasta)`.
- Verificação de hora em hora: não montado, preso (não responde), 90% ocupado e fotografia parada ou atrasada.
- **Fotografias** (`photos.py`, decisão do usuário: igual ao sistema antigo, só discos inteiros): toda noite às 03:00, a origem
  vai inteira para `<disco de fotografias>/atual/` (`podman unshare rsync -aH --numeric-ids --delete`) e o que mudou ou saiu
  para `versoes/<data>/` (30 dias). Nada grava no disco de fotografias (`astroverso-fotografia.json` na raiz; o
  `kit.folders` esconde e recusa). Não roda com um disco ausente; para com mais de 10% de exclusões ("Liberar a fotografia").
- **Resgatar um disco** (`rescue.py`): formata o disco novo (LUKS2 + TPM + ext4, com o nome do antigo), monta no mesmo
  lugar e copia de volta o `atual/`. Única exceção à regra "formatar fica no Cockpit" (decisão do usuário).

### App `n8n`

- Uma instância só, com várias rotinas (decisão do usuário: módulos por assunto, não um n8n por rotina). Containers por
  Quadlet: `astroverso-n8n` e `astroverso-n8n-runners` (imagens oficiais, mesma versão), SQLite, `n8n.<domínio>`,
  administrador mantido pela instalação (hash bcrypt), isolado da empresa.
- **Rotinas só no banco do n8n** (fonte de verdade, sem sincronizar código; nada pessoal no repositório). Versões: o
  histórico do n8n, "Restaurar uma rotina" (uma rotina de um backup, como cópia ou substituindo) e "Restaurar uma versão".
  O backup leva o `export:entities` e cada rotina num JSON separado.
- **Módulos** (`apps/n8n/modules/<módulo>/`): APIs em Python, um container cada (`astroverso-n8n-<módulo>:8080`, sem
  porta nem endereço), rotas `/v1/...` versionadas e `/v1/saude`. Não aparecem no instalador: todos sobem sozinhos, e a
  imagem é refeita pelo resumo dos arquivos. Ligar e desligar rotinas é no próprio n8n (decisão do usuário).
- **Conexões do Astroverso:** credenciais com `id` fixo só a partir dos contratos do kit (`kit.mail`, `kit.mailboxes`,
  `kit.discord`) e a chave das chamadas; credenciais de um assunto o usuário cadastra no n8n.
- Módulo `contas` (QR Codes do Pix em PDFs e imagens, QR Code do Pix e código de barras em SVG/PNG) substitui as
  bibliotecas do executor antigo: os nós Code chamam o módulo por `this.helpers.httpRequest` (testado no executor
  externo), e o runners fica na imagem oficial. As rotinas de contas foram migradas fora do repositório (dados
  pessoais) e entram pela ação "Importar rotinas".
- Comandos do Discord para rotinas: cadastrados pelo usuário (`commands.json`: nome, caminho do webhook, descrição),
  um por ação remota (`n8n:<nome>`, como no `wol`). A chamada sai de dentro do container (`node` com `fetch` em
  `127.0.0.1:5678`), com a chave das chamadas pela entrada padrão, e devolve o campo `mensagem`.

### App `cockpit`

- Pacotes do sistema (`cockpit`, `cockpit-podman`, `cockpit-storaged`, `cockpit-files`), não container: ele administra a
  própria máquina. Endereço padrão `<nome-da-máquina>.<domínio>` (um painel por máquina), publicado pelo `kit.routes`
  para `http://host.containers.internal:9090`.
- `cockpit.conf` no modo proxy e o serviço `cockpit` fechado no firewall (só pelo Caddy; o SSH é o caminho de volta).
  Os pacotes ficam no `remove`. Sem verificação de hora em hora (sobe sob demanda).
- Montar disco é pelo app `disks`; o Armazenamento do Cockpit fica para formatar e consultar.

### App `wol`

- Wake-on-LAN: máquinas cadastradas por nome e IP (o MAC lido pelo `ip neigh` com a máquina ligada, ou digitado), em
  `~/.astroverso/wol/machines.json`. Ligar manda o pacote mágico (UDP 9, broadcast geral e da rede local) a cada 4 s
  até a máquina responder ao ping, por até 3 min.
- Discord: uma ação remota por máquina (`wol:ligar-<nome>`, `menu=False`), porque as ações não recebem argumento; o
  agente atualiza o catálogo sozinho.
- Sem mudança no sistema além do backup: o pacote só sai pela rede local.

### Fora do refactor

- **samba** e **sunshine** não voltam (decisão do usuário): nada de pasta na rede nem de acesso remoto por Moonlight.

### Mudanças no sistema

- Toda mudança de um app no sistema, por menor que seja, é um `kit.changes.Change`: perguntada na instalação (padrão
  sim), desfeita e refeita na ação "Mudanças no sistema" do app, desfeita no `remove`. As essenciais têm
  `danger=True` (vermelho, ⚠).
- O que só existe por causa de um app (ex.: a porta do Tailscale no firewall) fica nesse app.

### App `system`

- Configurações da própria máquina, um arquivo por módulo: `hostname.py` (primeira etapa: o nome da máquina pelo
  `hostnamectl`, sem `Change` e sem voltar ao anterior no `remove`, por decisão do usuário), `clock.py` (o acerto do
  relógio pela internet, pela camada `kit.distro`: uma máquina com o relógio de hardware no horário local ficou 3 h
  atrasada sem NTP), `power.py` (suspensão
  mascarada, tampa e teclas ignoradas no `logind`, tela do console apagada) e `ssh.py` (`sshd`, SSH só da rede local e do Tailscale,
  `AllowUsers` + `PermitRootLogin no`, chaves autorizadas e a chave da máquina para o GitHub).
- O login por senha no SSH fica como na distribuição (decisão do usuário: é o caminho de volta se um PC autorizado
  for perdido). O `remove` não desliga o `sshd` nem apaga o `authorized_keys`.
- `~/.ssh/authorized_keys` é gerado a partir de `~/.astroverso/system/ssh-keys.json` (nome do PC + chave).
- Atualizações automáticas (`updates.py`, pela camada `kit.distro`): o `dnf5-automatic` aplica sozinho, todo dia, e
  **nunca reinicia** (decisão: num servidor, reiniciar é escolha do usuário, pelo Cockpit); a verificação de hora em
  hora avisa a atualização que falhou e o reinício pendente. Ficam no Astroverso, não no astroverso-devenv (o devenv
  é o ambiente de desenvolvimento e também roda no WSL).
- O resumo da máquina (disco, temperatura) fica pelo Cockpit (decisão do usuário). O Wake-on-LAN virou o app `wol`.

### Pacotes previstos

- `kit`: interface (`kit.ui`: logs, prompts, menus, logo), contrato dos apps (`kit.app`), testes por `pty`
  (`kit.testing`), configuração (`.env`, validadores), camada `distro`, domínio padrão.
- `manager`: o gerenciador (`./astroverso`): menu de instalar e gerenciar, e o uso direto
  `astroverso <app> <comando>`. Contrato do `app.py` em `apps/README.md`.
- `kit.vault`: o backup de cada app, enviado para a pasta dos backups no Nextcloud (WebDAV), com avisos no `#vault`.
- `kit.discord`: avisos dos apps no Discord (o bot é o app `discord`).
- `kit.disks`: os discos de dados montados pelo app `disks` (só leitura, a partir do `fstab`).
- `kit.folders` (seletor de pastas de todos os apps) e `kit.clouds` (pastas ligadas a uma nuvem, contrato em
  `~/.astroverso/clouds/`).

Cada pacote e cada app tem a própria etapa de arquitetura antes de ser escrito.

## Nada pessoal no código nem na documentação

- O repositório será público. Domínio, IPs, nomes das máquinas da casa, fuso, contas e e-mails **não podem
  aparecer** no código, nos testes, nos READMEs, nas mensagens de commit nem neste arquivo, nem como exemplo.
  Vêm das perguntas da instalação (gravadas em `~/.astroverso/`) ou são detectados.
- Exemplos usam marcadores: `<seu-domínio>`, `<domínio>`, `<ip>`, `<rede>`, `<nome-da-máquina>`.
- Valores padrão neutros quando nada é detectado (ex.: fuso `UTC`).
- Antes de cada commit, conferir com `git grep -nE '<domínio real>|<IP real>|<nomes das máquinas>'` usando os
  valores do `CLAUDE.local.md` (o nome de todas as máquinas citadas lá), e reler a mensagem do commit.

## Regras de segurança ao testar

- **Nunca testar no container real nem no estado real.** Usar outro nome de container (que não comece por
  `astroverso`), outra rede, outra imagem e outras portas, e remover tudo no fim. Um teste antigo recriou um container real e apagou um `.env` real.
- Nunca apagar nada em `~/.astroverso`: contém segredos e não está no git. Para testar, usar outro `HOME`,
  mantendo `XDG_DATA_HOME`, `XDG_CONFIG_HOME` e `XDG_RUNTIME_DIR` reais (senão o Podman usa outro armazenamento).
- A instalação antiga roda a partir de `~/Projects/astroverso-homelab`: não mexer naquela pasta.
- `sudo` não funciona na sessão do Claude (sem TTY). Instalações que pedem `sudo` rodam em um terminal normal.
- Para testar menus e prompts, usar um pseudo-terminal em Python (`pty.fork`) enviando as teclas.
- Nos testes, trocar o `container` e o `run` de **cada** módulo que os importa (ex.: `app.drives.container`): um módulo
  esquecido chama o `systemctl` de verdade e reinicia o container real.
- Não pedir nem aceitar segredos (tokens, senhas) no chat: eles entram pela instalação.
- Teste real de containers por Quadlet: `HOME` temporário, mas `XDG_DATA_HOME`, `XDG_CONFIG_HOME` e
  `XDG_RUNTIME_DIR` reais e o `container.quadlets` apontando para a pasta real (o systemd do usuário só lê de lá);
  nomes `claude-teste-*`, rede própria (`dataclasses.replace(spec, network=...)`: o padrão do `Container` é fixado na
  definição da classe) e, no fim, conferir unidades, containers, redes e imagens que sobraram.

## Armadilhas

- Uma rede do Quadlet vira a unidade `<rede>-network.service` (fica ativa depois de criar a rede): ao apagar a rede
  no Podman, parar a unidade antes, senão o systemd não cria a rede de novo e o container falha com "network not
  found". O `kit.container` já faz isso.
- O Quadlet passa o `HealthCmd=` para o Podman do jeito que está na linha (só tira aspas de fora, sem desfazer `\"`):
  o `kit.container` grava o comando cru (só `%` e `$` dobrados). Com aspas escapadas, a verificação dava "Syntax error"
  e o container ficava `unhealthy` para sempre.
- A imagem do Nextcloud pede `StopSignal=SIGWINCH` (do Apache); o container do cron (`crond`) ignora e é morto em
  10 s, marcando a unidade como falha: o cron usa `stop_signal="SIGTERM"`.
- Duas unidades que usam a mesma imagem: remover todos os containers antes das imagens.
- Discos (trazido do antigo):
  - Com Secure Boot, o IMA registra no TPM cada módulo carregado no boot, e o desbloqueio pelo TPM recebe
    `TPM_RC_PCR_CHANGED` até o boot acalmar (~1 min): a montagem LUKS espera o `systemd-cryptsetup@` (5 min) em vez
    de 10 s pelo dispositivo.
  - Propagação `rslave` não leva para dentro do container uma montagem feita depois que ele subiu: o disco monta
    antes do `user@<uid>.service`.
  - `nofail` tira a ordem do disco antes do `local-fs.target`; `x-systemd.wanted-by=` anula o `nofail`. Para remontar
    ao religar, links em `/etc/systemd/system/<dispositivo>.device.wants/` (no LUKS, a montagem fica no `.wants` do
    `systemd-cryptsetup@`).
  - O rótulo de um LUKS fica dentro da criptografia: o app o copia para o cabeçalho LUKS2.
  - O udisks (Cockpit) regrava as linhas que edita e pode separá-las da marca: as linhas são reconhecidas pela
    assinatura (`x-udisks-auth` + `container_file_t` em `/srv/`; `luks-*` com `headless=true`) e emparelhadas pelo UUID.
  - Um LUKS em uso que desconecta e volta (gaveta USB) fica preso ao aparelho que sumiu: a pasta continua montada,
    mas toda leitura dá `Input/output error` até reiniciar. O `kit.disks.responds` detecta.
  - Sem o disco montado, `/srv/<nome>` é uma pasta vazia e imutável, sem erro: quem grava ou faz backup confere antes.
  - O `ntfs3` usa a permissão gravada no disco; um NTFS desligado sem fechar (inicialização rápida do Windows) não
    monta até `ntfsfix -d`.
  - Com ACL, o `chmod` mexe na máscara: pasta com ACL usa `770`.
- rclone (trazido do antigo):
  - `bisync` com `--resilient` não pede `--resync` quando as listas somem ("cannot find prior Path1 or Path2
    listings"): o app detecta essa mensagem e a de "must run --resync" e junta os dois lados.
  - `bisync --dry-run` também para na trava de exclusões: para mostrar o que seria apagado, `--dry-run --force`.
  - Uma senha ofuscada pelo `rclone obscure` é reversível: vai pela entrada padrão, nunca como argumento (por isso o
    app não usa `rclone config create` com senha).
- n8n:
  - `import:entities --truncateTables=true` só funciona num banco novo (sem `database.sqlite`).
  - `import:workflow` desliga a rotina importada; `--activeState=fromJson` só vale no modo fila. Para religar:
    `publish:workflow --id=<id>`, que o n8n rodando aplica sozinho.
  - `export:workflow` sem nenhuma rotina sai com erro ("No workflows found with specified filters").
  - O `podman exec` no container do n8n roda como `-u 1000` (o nome `node` pode não resolver).
  - A importação de rotinas liga cada nó à credencial pelo `id` e, sem ele, pela credencial de mesmo nome e tipo.
  - No nó Code com o executor externo, `this.helpers.httpRequest` roda no n8n principal (alcança os containers da rede
    pelo nome); o executor oficial libera só o `crypto` e o `moment` no `require`.
- `python3 -I` não põe a pasta do script no caminho de importação.
- Python como processo 1 de um container ignora o SIGTERM sem tratador: cada parada espera 10 s e termina à força.
- Containers sem root (rede `pasta`) chegam na máquina por `host.containers.internal` (`169.254.1.2`), que **não** cai
  no loopback: um serviço ouvindo só em `127.0.0.1` fica fora do alcance do Caddy. Ouvindo no IP da rede (ou em
  todos), o Caddy chega mesmo com a porta fechada no firewall (o tráfego conta como da própria máquina): é assim que
  o Cockpit e o painel do AdGuard ficam só pelo Caddy.
- Segredos nunca em argumentos de comando (aparecem no `ps`): vão pela entrada padrão (`input=` do `kit.run`)
  ou por arquivo temporário.
