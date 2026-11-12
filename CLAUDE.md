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
  "Implodir Astro" na máquina real: eles apagam `~/.astro`, o usuário de jogos e as montagens dos discos. Para
  testar, usar outro `HOME` (o `ASTRO_HOME` vem de `$HOME/.astro`).
- `sudo` não funciona na sessão do Claude (sem TTY). `systemctl` e `pkexec` disparam uma janela gráfica do
  polkit para o usuário digitar a senha. Instalações que pedem `sudo` rodam em um terminal normal.
- Para testar menus e prompts, usar um pseudo-terminal em Python (`pty.fork`) enviando as teclas.
- Não pedir nem aceitar segredos (token da Cloudflare, senhas) no chat: eles entram pelo assistente.

## Arquitetura

```
setup.sh             assistente: Instalar/Reinstalar Astro (host_upgrade na primeira vez, discos, projetos na ordem ORDER),
                     Gerenciar Astro (ações dos projetos) → Administração (discos, ações globais, Implodir Astro),
                     Modo desenvolvimento (só com o comando claude: exec claude --continue na pasta do repositório)
lib/ui.sh            logs com prefixo, prompts, ui_menu, ui_checklist (setas e Espaço)
lib/host.sh          host_base (comando astro, sem suspensão, compose, boot, ssh, tailscale) / host_undo, firewall, portas, IP e sub-rede
lib/env.sh           env_get CHAVE [padrão], state_setup / state_purge, images_remove, validadores
lib/proxy.sh         proxy_publish / proxy_unpublish (rotas do projeto no Caddy via .proxy)
lib/disk.sh          disk_manage / disk_setup / disk_mounts / disk_release_all (discos da máquina no fstab e crypttab, TPM; privado ou compartilhado)
lib/notify.sh        avisos pelo bot do discord (fila): notify_send / notify_info (silenciosa), notify_problem / notify_resolved (1 por dia), com botões
<projeto>/project.sh describe | status | actions | action <id> | install | remove
                     opcionais: global-actions | remote-actions | remote <id> [arg] | help | backup | restore <pasta>
```

- Contrato e bibliotecas documentados em `lib/README.md`.
- Compose de todo projeto: `name: astro` + `x-podman: in_pod: false` (agrupados, mas independentes).
- **Estado fora do repositório:** tudo o que a instalação gera fica em `~/.astro/<projeto>` (`$STATE`, `$ENV_FILE`),
  o repositório só tem código. `state_setup` (início do `cmd_install`) cria a pasta; `state_purge` (fim do `remove`) a apaga.
  Compose com `${ASTRO_STATE}` nos volumes e `env_file`, rodado pela função `compose` (`--env-file`). Serviço que
  roda com outro usuário guarda a configuração no `~/.astro` dele (arcade), legível por ACL a quem instala.
  Estado da máquina em `~/.astro/host.env` (`600`).
- Backup das configurações (rclone, 01:00, e "Fazer backup agora"): cada `~/.astro/<serviço>` em
  `<destino>/<AAAA-MM-DD_HHMMSS>/<serviço>/<serviço>.tar.zst.gpg`, versões apagadas depois de `CONFIG_KEEP_DAYS` (90).
  "Restaurar uma versão" (rclone, ação global, em Administração): para o rclone e segura as travas, salva a situação atual
  (`_antes-da-restauracao`) e chama `<projeto>/project.sh restore <pasta>`. Formato
  (gpg simétrico, senha em `~/.astro/rclone/data/config-backup.key`), com caminhos relativos ao serviço (`tar
  --transform`), sem home nem usuário. Cada projeto pode ter o comando `backup` (dumps e `exclude <caminho>`,
  `include <nome> <caminho>`, `add <caminho>`).
- **Instalar Astro** sempre instala tudo, na ordem `ORDER` do `setup.sh` (`caddy` primeiro, pelo domínio; `rclone` e
  `discord` por último, por verem os outros), depois da atualização do sistema (primeira vez), da Máquina
  (`host_base`, uma vez só; os projetos não o chamam) e de "Discos da máquina". Um projeto que falha não para os
  outros; o resumo mostra quais falharam. Cada etapa roda em subshell com `set -e` (`run_step`) e só ganha a
  marca `~/.astro/.concluidas/<etapa>` ao terminar sem erro; no "Reinstalar Astro", um checklist escolhe quais
  concluídas refazer (Enter pula todas). A implosão apaga as marcas depois do backup.
- **Nomes das operações** (iguais em menus, avisos, logs, unidades e ajuda do Discord): `Backup: local ⬅️ nuvem`
  (download inicial), `Backup: local ↔️ nuvem` (mesclagem), `Backup: local 🔄 nuvem` (sincronização),
  `Backup: local ➡️ backup diário`, `Backup: configurações ➡️ local`, `Backup: configurações ⬅️ local` (restauração),
  `Backup: Arcade ➡️ local`, `Máquina: estado`, `Serviço: iniciar/parar/reiniciar`. Comandos do Discord em inglês:
  `backup:cloud`, `backup:cloud-check`, `backup:cloud-force`, `backup:daily`, `backup:configs`, `backup:arcade`,
  `machine:status`, `<projeto>:start|stop|restart`, `help`. A tabela completa fica no `README.md` da raiz.
- **Implodir Astro** (Administração): confirmação digitando `IMPLODIR`; backup `antes-de-implodir` pelo
  `rclone/run.sh config` (pasta e senha do rclone ou, sem elas, perguntadas: `ASTRO_BACKUP_DEST`/`ASTRO_BACKUP_KEY`),
  e nada é desfeito se ele falhar; `remove` de cada projeto na ordem inversa; `disk_release_all`; `host_undo`; rede
  `astro_default`; `~/.astro` (mantido se algum `remove` falhou). Ficam pacotes, dados dos discos e o SSH ativo.
  `remove` desfaz tudo o que é do projeto (não existe mais `--purge`) e não falha no que já não existe.
- Configuração por prompts, gravada em `~/.astro/<projeto>/.env` (permissão 600). "Usar a configuração já salva?" reaproveita.
  Toda resposta passa por um validador de `lib/env.sh` (`is_port`, `is_ipv4`, `is_hostname`...), porque vai parar
  em `.env`, YAML, `sed` ou Caddyfile.
- Segredos nunca em argumentos de comando (aparecem no `ps`): senha para o `htpasswd` e token para o `curl`
  vão pela entrada padrão.
- Um projeto publica um endereço no Caddy com `proxy_publish` (escreve `~/.astro/<projeto>/.proxy` e recarrega o
  Caddy). Rotas manuais ficam em `~/.astro/caddy/.routes`; as de projeto têm prioridade sobre uma manual com o mesmo endereço.
- Discos de dados são **da máquina**, nunca de um projeto: "Discos da máquina" no `setup.sh` (`disk_manage`) os monta
  em `/srv/<rótulo>`, com quem instala como dono, `privado` (só ele) ou `compartilhado` (todos os usuários, ex.:
  jogos). As linhas no `fstab`/`crypttab` vêm depois de `# astro <uuid> <tipo>`. Projetos só escolhem caminhos de
  `disk_mounts` (Nextcloud com ACL para o `www-data` nos privados; rclone). Disco plugado de passagem fica com o
  padrão do Fedora (montado para quem está na tela) e é acessado de longe pelo Cockpit. **Nada pode pedir senha no boot** (a máquina é reiniciada de longe): LUKS só pelo TPM
  (PCR 7) com `headless=true`, e tudo com `nofail`.
- Versões fixadas: AdGuard na 1ª linha de `adguard/Dockerfile`; Caddy e `caddy-dns/cloudflare` em `caddy/Dockerfile`;
  Python e `discord.py` em `discord/Dockerfile`; Nextcloud, PostgreSQL e Valkey nas imagens de `nextcloud/docker-compose.yml`.

### Projetos

| Projeto | Resumo |
|---|---|
| adguard | Imagem customizada em **`network_mode: host`**. O entrypoint gera `AdGuardHome.yaml` do template se ele não existir. `.env` guarda só o **hash bcrypt** da senha. Reescritas `*.<domínio> → IP`. Configura o DNS da máquina, confere o Split DNS do Tailscale e publica o painel no Caddy (`PANEL_HOST`). |
| arcade | ES-DE + RetroArch + Sunshine no usuário de jogos (padrão `ristar`), a única exceção ao usuário que instala (dados sensíveis, nunca logado). **ES-DE:** AppImage `ES-DE_x64.AppImage` mais recente pela API de pacotes do GitLab (`file_sha256` conferido) em `/usr/local/bin/es-de`, com `.desktop`, ícone e o `es_systems.xml` da versão em `/usr/local/share/astro-arcade` (extraídos com `--appimage-extract <caminho>` para `squashfs-root/`); runtime estático com `fusermount3`. **RetroArch:** Flatpak `org.libretro.RetroArch` do Flathub (sistema), com `org.freedesktop.Platform.GL.nvidia-<versão>//1.4` igual a `/sys/module/nvidia/version` (na instalação e na ação de atualizar, não no boot). Central de Programas do usuário de jogos sem `download-updates`. Configuração em `~<jogos>/.astro/arcade/{sunshine,es-de,retroarch}`, com atalhos `~/.config/sunshine`, `~/ES-DE` e `~/.var/app/org.libretro.RetroArch/config/retroarch`. Pastas escolhidas por `ui_browse` (`MEDIA_DIR`, `ROM_DIRS` separadas por `|`); `scripts/emulation.py` roda como o usuário de jogos (`python3 -I -` pela entrada padrão) e grava `ROMDirectory`/`MediaDirectory`, limpa caminhos e drivers do Windows do `retroarch.cfg`, gera `custom_systems/es_systems.xml` (sistemas das outras pastas de ROMs, `<path>` absoluto, lista em `.astro-sistemas`) e baixa o núcleo padrão de cada sistema do buildbot. Carregar configuração/gamelists: `sudo tar` + `chown` (só com a pasta local vazia na instalação; depois por ações). No backup das configurações, só `sunshine/`, `retroarch.cfg` e `es_settings.xml`; o resto (RetroArch: cfg, saves, states, system, config, playlists, screenshots, records; ES-DE: settings, collections, gamelists, themes) vai por `rclone sync` incremental, sem criptografia, para `ARCADE_BACKUP` (padrão `Arcade` ao lado do `CONFIG_BACKUP`), dentro do `cmd_backup` (01:00, "Fazer backup agora", "Implodir Astro"); falha nele derruba o backup e a implosão. Instalação com a pasta local vazia oferece restaurar do backup. **Sunshine:** pacote do sistema baixado da última release no GitHub (SHA-256 conferido), não container. Usuário de jogos sem `sudo`, com senha (`chpasswd` pela entrada padrão); login automático no GDM e sem bloqueio automático de tela opcionais (`AUTOLOGIN`), bloqueio manual e troca de usuário sempre permitidos; o serviço de usuário sobe com a `graphical-session.target` dele. `setcap cap_sys_admin,cap_sys_nice+p` (captura KMS e prioridade alta na GPU). Instala o driver NVIDIA (RPM Fusion + chave MOK no Secure Boot), torna a NVIDIA a placa principal do GNOME (udev `mutter-device-preferred-primary`). O codificador não é fixado: o Sunshine testa (NVENC primeiro) a cada stream; a instalação só avisa se não houver tela na saída da NVIDIA. Padrão: tampa fechada e tela externa (TV ou plugue HDMI fantasma) no HDMI, que sai pela NVIDIA. Apps do Sunshine (`emulation.py sunshine-apps`): Desktop + ES-DE (`auto-detach`), sem os de fábrica "Low Res Desktop"/"Steam Big Picture"; capa em `sunshine/covers/es-de.png` se existir. `astro-sunshine-display` (Python + DBus do Mutter) no `global_prep_cmd` troca a tela, temporariamente, para a resolução exata do aparelho e volta no `undo`; nunca sai com erro. Alto-falantes internos mudos a cada sessão do usuário de jogos: `scripts/speakers.py` em `/usr/local/bin/astro-arcade-speakers`, serviço de usuário `astro-arcade-speakers` na `graphical-session.target` dele (`pw-dump` + `wpctl`; o Fedora não traz `pactl`). Flathub ativado com `remote-modify --enable` (vem desligado sem os repositórios de terceiros). Painel `47990` bloqueado na rede, rota `https+insecure://host.containers.internal:47990`. ACL `u:<quem instala>:rX` no `~/.astro` do usuário de jogos para o backup. Discos de jogos: compartilhados em "Discos da máquina" (o arcade não cuida de discos). `.env` com usuário inexistente refaz as perguntas em vez de criá-lo. O `remove` apaga o usuário de jogos com a home (`userdel -r`), depois do backup do RetroArch e do ES-DE. |
| caddy | Let's Encrypt **curinga `*.<domínio>`** por DNS-01 na Cloudflare. O token precisa de **Zone:Read + DNS:Edit** na zona, sem expiração, e é validado na API ao instalar. Ações: listar, adicionar, remover e recarregar rotas. |
| cockpit | Pacotes do sistema (`cockpit`, `cockpit-podman`, `cockpit-storaged`, `cockpit-files`), não container. Arquivos e discos pelo navegador (com "Acesso administrativo", qualquer arquivo). `cockpit.conf` em modo proxy; porta 9090 bloqueada para a rede no firewalld (rich rule). Rota `<nome-da-máquina>.<domínio> → http://host.containers.internal:9090`. |
| discord | Bot em Python (`discord.py`, imagem customizada) sem acesso ao host: só monta `~/.astro/discord/fila` (`pedidos/`, `respostas/`, `saida/`, `tmp/`, `catalogo.json`; arquivos gravados em `tmp/` e movidos). Comando `/astro command:<projeto>:<ação> argument:<opcional>` (nomes sempre em inglês) com autocompletar do catálogo, registrado só no servidor do canal; botões com `custom_id` `astro\|run\|<ação>\|<arg>` tratados no `on_interaction` (sobrevivem a reinícios); ações com `sim` pedem confirmação. Só os IDs de `DISCORD_USERS`; menções desligadas. O catálogo guarda projeto, ação e tipo (`host`/`container`/`remote`) de cada comando; `remote-actions` com `:` no id dá um nome próprio (`backup:cloud`, `backup:arcade`). `help` mostra `fila/ajuda.json`, montado das linhas do comando `help` dos projetos (`grupo|nome|o que é|quando|comando|ordem`) mais máquina e serviços, dividido em mensagens de até 1900 caracteres. O executor no host (`runner.sh`, `astro-discord-runner.path` com `DirectoryNotEmpty`) refaz o catálogo a cada rodada, recusa o que não está nele, roda `machine:status`, `<projeto>:start\|stop\|restart` (`podman start/stop/restart` em `astro-<projeto>*`, nunca o próprio bot) ou `<projeto>/project.sh remote`, com 10 min de limite. `notify_send` deixa o aviso em `saida/`. |
| nextcloud | Imagem oficial `nextcloud:<versão>-apache` + PostgreSQL + Valkey + container de cron (mesma imagem, `/cron.sh`). Sem porta no host: o Caddy chega em `astro-nextcloud:80` pela `astro_default`. Senha do banco em `~/.astro/nextcloud/data/secrets` (lida pelos `*_FILE`; arquivo `644` em pasta `700`, porque o Postgres lê como o usuário `postgres`). A imagem instala com uma senha aleatória, trocada pela digitada com `occ user:resetpassword --password-from-env`. `trusted_proxies`, `overwriteprotocol`, fuso, região e cron aplicados pelo `occ` a cada instalação. Discos: escolhidos em `disk_mounts` (caminhos em `DISKS`); nos privados, ACL (também padrão) para o UID do `www-data` no host (o `group::---` da ACL fecha o grupo); disco sem `container_file_t` na montagem fica de fora; volumes em `docker-compose.override.yml` gerado e pasta no Nextcloud pelo `files_external` (`filesystem_check_changes 1`). `apache.conf` substitui o `000-default.conf` da imagem: `ServerName https://${NEXTCLOUD_HOST}:443` + `UseCanonicalName On` (redirecionamentos do `.well-known` em `https`) e HSTS. |
| rclone | Sem container: timers do systemd do usuário rodando `rclone/run.sh` (`tick` de 2 em 2 horas das 08:00 às 20:00, pulado durante streams do Sunshine (marcador `/tmp/astro-sunshine-stream` do `astro-sunshine-display`, ignorado com mais de 6h; `stream_watch` interrompe a rodada com SIGINT se um stream começar, aviso ⏸️; `.agora` do "agora" manual ignora a pausa), `config` 01:00, `local` 03:00: sincroniza e depois espelha no disco) com `ASTRO_PLAIN=1` e prioridade mínima (`Nice=19`, `CPUSchedulingPolicy=idle`, `IOSchedulingClass=idle`). Disco de backup escolhido em `disk_mounts` (`BACKUP_MOUNT`; `atual/` + `versoes/<data>`, `podman unshare rclone sync --metadata --backup-dir`). Nuvem pelo rclone, um destino por `data/targets/<nome>.env` e seção no `data/rclone.conf`; serviços em `providers/*.sh` (`provider_describe`, `provider_default_name`, `provider_options`, `provider_configure`). Nuvem ↔ disco por `rclone bisync` (conflito: o mais novo vence, o outro vira `.conflict1`; `--max-delete 5` em %; `--resync --resync-mode newer` na primeira rodada ou quando o estado se perde; `--force` pelo "Backup: local 🔄 nuvem (agora)" ou `backup:cloud-force`). Primeira cópia nuvem → disco agendável, retomada pelo `tick` até `IMPORT_DONE=yes`; antes disso nada vai para a nuvem. Nada roda sem o disco montado; `flock` entre rodadas. Avisos no Discord (`routine` no `run.sh`, só com `INVOCATION_ID`, ou seja, pelo systemd): início/sucesso silenciosos e falha para o `tick` (inclusive "Sincronizar agora" e a primeira cópia), o `config` e o `local`; rodada pulada pelo `flock` não avisa. |

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
- O usuário de jogos tem o `home` fechado (700): comandos nele passam por `sudo -u <usuário> -H` (`as_user`),
  e o `status` do arcade não lê nada dentro dele.
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
  Para remontar ao religar, o `disk_setup` cria links em `/etc/systemd/system/<dispositivo>.device.wants/`.
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
- O ES-DE procura o RetroArch do Flatpak (`/var/lib/flatpak/exports/bin/org.libretro.RetroArch`) e os núcleos em
  `~/.var/app/org.libretro.RetroArch/config/retroarch/cores`; a pasta pode ser um atalho para fora (o Flatpak
  tem `filesystems=host`).
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
- O Flatpak só usa a NVIDIA com a extensão `org.freedesktop.Platform.GL.nvidia-<versão>` igual à do driver
  carregado. Depois de uma atualização do driver, a antiga não serve, e o app cai para a Intel/CPU (stutter no
  stream). A Central de Programas de um usuário sem `sudo` tenta instalar a nova e falha ("Deploy not allowed").
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

## Pendências e ideias combinadas

- Segurança:
  - revisar as ACLs do Tailscale (hoje "todos acessam tudo" e a rede inteira está anunciada);
  - conferir no roteador se não há DMZ, UPnP ou redirecionamento de portas.
- Discord: avisos e comandos de outros projetos (ex.: DNS do AdGuard fora, renovação do certificado do Caddy,
  consultas bloqueadas). Outros canais (e-mail por SMTP, Telegram), se precisar.
- Sunshine independente de usuário (ideia combinada, para depois): Sunshine como serviço do sistema com um
  usuário de serviço próprio (`sunshine`, configuração em `/var/lib/sunshine`), subindo no boot; imagem (KMS) e
  controles (`/dev/uinput`, grupo `input`) já valem para qualquer sessão. Som e resolução por um agente em toda
  sessão gráfica (`systemctl --global enable`), que só age na sessão que está na tela: aplica o modo pedido
  (`astro-sunshine-display`) e cria uma ponte do PipeWire da sessão para a saída virtual do Sunshine (túnel),
  desfeita no fim do stream ou na troca de usuário. O Sunshine avisa início/fim do stream por arquivo em
  `/run/astro-sunshine/` (`global_prep_cmd`). Fazer em duas etapas: imagem, controles e resolução primeiro; som
  depois, testado pelo Moonlight. Hoje o Sunshine é serviço da sessão do usuário de jogos: sair da sessão
  derruba o stream (usar "Trocar de usuário").
- Ação "verificar atualizações" para as versões fixadas.
- Ações de pós-configuração no adguard (ex.: gerenciar reescritas).
