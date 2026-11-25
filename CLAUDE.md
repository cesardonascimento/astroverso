# CLAUDE.md

Regras para desenvolver o Astroverso. O contexto da instalação atual (máquina, IPs, domínio, contas) fica em
`CLAUDE.local.md`, fora do git.

## Situação

O Astroverso está sendo refeito como monorepo. O código antigo (o antigo Astroverso Homelab) fica em `backup/`,
só como referência: nada roda de lá e nada novo depende dele. Cada parte é migrada para `apps/` ou `packages/`,
um pedaço por vez. As regras e armadilhas antigas ficam em `backup/CLAUDE.md` e voltam para este arquivo quando
o app ou pacote delas for migrado.

## Nomes

- O projeto é o **Astroverso**. O codinome técnico é `astroverso` em tudo que identifica o sistema: comando,
  `~/.astroverso`, containers, imagens, rede, unidades systemd, variáveis `ASTROVERSO_*`, marcas em arquivos do
  sistema, sufixo `.astroverso-bak`, recursos da Cloudflare, prefixo `[astroverso]` dos logs e rótulos dos menus.
- **`astro` é só o bot do Discord**: o nome do bot, o comando `/astro`, o `custom_id` `astro|...` e o canal do bot.
  Todo o resto é `astroverso`, inclusive o usuário padrão dos apps.

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
packages/<pacote>/ código compartilhado pelos apps (kit, backup...)
backup/           código antigo, só referência
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
  `kit.backup`: a mudança perguntada `kit.backup.change(APP)` (timer diário próprio) e as ações "Fazer backup agora"
  (`run_backup`) e "Restaurar uma versão" (`restore`). Nenhum app varre os outros. Sem o servidor de backup ligado na
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
- Pasta dos arquivos padrão `~/Nextcloud`, do `www-data` do container (`podman unshare chown 33:33`). Os discos da
  máquina entram depois, pelo `kit.disks`, como armazenamento externo.
- Senhas por arquivo (`*_FILE`) em `~/.astroverso/nextcloud/secrets/` (`644` dentro de pasta `700`: o Postgres lê
  como outro usuário do container). A senha do administrador entra por `occ user:resetpassword --password-from-env`.
- `backup`/`restore` implementados (dump SQL + `config/`), mandados pelo `kit.backup`.

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

### App `backup`

- Servidor (uma máquina): container `rclone serve restic --append-only --private-repos` publicado em
  `backup.<domínio>`, um repositório restic por máquina numa pasta (depois, um disco de backup), manutenção semanal
  (`forget --prune` + `check`) só no servidor, verificação de hora em hora (36 h sem backup).
- Cliente (todas as máquinas, inclusive a do servidor): só grava `~/.astroverso/backup.env`; quem manda os backups
  são os próprios apps (decisão do usuário: "cada app manda a própria config").
- A senha do repositório de cada máquina vai para o gerenciador de senhas do usuário; o backup do próprio app não
  leva as senhas.
- Os outros trabalhos do rclone antigo (espelho dos discos, sincronização com a nuvem, cópia do Windows) ficam para
  outra conversa.

### Mudanças no sistema

- Toda mudança de um app no sistema, por menor que seja, é um `kit.changes.Change`: perguntada na instalação (padrão
  sim), desfeita e refeita na ação "Mudanças no sistema" do app, desfeita no `remove`. As essenciais têm
  `danger=True` (vermelho, ⚠).
- O que só existe por causa de um app (ex.: a porta do Tailscale no firewall) fica nesse app.

### App `system`

- Configurações da própria máquina, um arquivo por módulo: `power.py` (suspensão mascarada, tampa e teclas
  ignoradas no `logind`, tela do console apagada) e `ssh.py` (`sshd`, SSH só da rede local e do Tailscale,
  `AllowUsers` + `PermitRootLogin no`, chaves autorizadas e a chave da máquina para o GitHub).
- O login por senha no SSH fica como na distribuição (decisão do usuário: é o caminho de volta se um PC autorizado
  for perdido). O `remove` não desliga o `sshd` nem apaga o `authorized_keys`.
- `~/.ssh/authorized_keys` é gerado a partir de `~/.astroverso/system/ssh-keys.json` (nome do PC + chave).
- Outras ideias do projeto antigo (atualizações automáticas, resumo da máquina com disco e temperatura, Wake-on-LAN,
  discos) ficam para depois do refactor, para o usuário revisar com calma.

### Pacotes previstos

- `kit`: interface (`kit.ui`: logs, prompts, menus, logo), contrato dos apps (`kit.app`), testes por `pty`
  (`kit.testing`), configuração (`.env`, validadores), camada `distro`, domínio padrão.
- `manager`: o gerenciador (`./astroverso`): menu de instalar e gerenciar, e o uso direto
  `astroverso <app> <comando>`. Contrato do `app.py` em `apps/README.md`.
- `kit.backup`: o backup de cada app no servidor do app `backup` (restic), com avisos no `#backup`.
- `kit.discord`: avisos dos apps no Discord (o bot é o app `discord`).

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
- Não pedir nem aceitar segredos (tokens, senhas) no chat: eles entram pela instalação.
- Teste real de containers por Quadlet: `HOME` temporário, mas `XDG_DATA_HOME`, `XDG_CONFIG_HOME` e
  `XDG_RUNTIME_DIR` reais e o `container.quadlets` apontando para a pasta real (o systemd do usuário só lê de lá);
  nomes `claude-teste-*`, rede própria (`dataclasses.replace(spec, network=...)`: o padrão do `Container` é fixado na
  definição da classe) e, no fim, conferir unidades, containers, redes e imagens que sobraram.

## Armadilhas

- Uma rede do Quadlet vira a unidade `<rede>-network.service` (fica ativa depois de criar a rede): ao apagar a rede
  no Podman, parar a unidade antes, senão o systemd não cria a rede de novo e o container falha com "network not
  found". O `kit.container` já faz isso.
- A imagem do Nextcloud pede `StopSignal=SIGWINCH` (do Apache); o container do cron (`crond`) ignora e é morto em
  10 s, marcando a unidade como falha: o cron usa `stop_signal="SIGTERM"`.
- Duas unidades que usam a mesma imagem: remover todos os containers antes das imagens.
- Segredos nunca em argumentos de comando (aparecem no `ps`): vão pela entrada padrão (`input=` do `kit.run`)
  ou por arquivo temporário.
