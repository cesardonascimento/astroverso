# Criando um projeto

O `setup.sh` reconhece qualquer pasta com um `project.sh` executável. "Instalar Astroverso" instala todos na ordem da
lista `ORDER` do `setup.sh` (`caddy` primeiro, `rclone` por último); um projeto fora da lista entra no fim.
Antes dos projetos, o `setup.sh` prepara a máquina uma vez (`host_base`) e roda "Discos da máquina": o `install`
de um projeto supõe a máquina já preparada. Cada etapa (`maquina`, `discos`, um projeto) só ganha a marca
`~/.astroverso/.concluidas/<etapa>` quando termina sem erro (a marca é apagada no começo); no "Reinstalar Astroverso", um checklist
mostra todas as etapas, com as pendentes já marcadas, e só as escolhidas rodam. Um projeto só conta como concluído se o `status` dele também passar. O
`project.sh` implementa:

| Comando | Responsabilidade |
|---|---|
| `describe` | Imprime uma linha de descrição |
| `status` | Sai com código 0 se o projeto está instalado |
| `install` | Pergunta a configuração, prepara o que é do projeto no host (portas, pacotes) e sobe os containers |
| `remove` | Desfaz tudo o que o projeto criou: containers, imagens (`images_remove`), serviços, regras do firewall, ajustes do sistema feitos só para ele, a rota do Caddy e `~/.astroverso/<projeto>` (`state_purge`). Mantém os pacotes e os dados dos discos. Roda mesmo com o projeto pela metade, sem falhar no que não existe. Chamado pelo "Implodir Astroverso", na ordem inversa da instalação, depois do backup |
| `actions` | Lista as ações de pós-configuração, uma por linha no formato `id\|Descrição` (vazio se não houver) |
| `action <id>` | Executa uma ação listada em `actions` |
| `global-actions` (opcional) | Como `actions`, mas as ações aparecem em Gerenciar Astroverso → Administração (com o projeto instalado) e rodam com `action <id>` |
| `domain <antigo> <novo>` (opcional) | Chamado pelo "Trocar o domínio" depois de os endereços salvos já terem sido trocados no `.env`: reaplica só o que depende do domínio, sem perguntas. Sem ele, o projeto é reinstalado com `ASTROVERSO_REUSE_CONFIG=1` |
| `restore <pasta>` (opcional) | Troca a configuração pela da pasta extraída do backup (`state_restore`), cuidando do que for do projeto (ex.: carregar o dump do banco), e sobe o serviço de novo |
| `remote-actions` (opcional) | Ações para o Discord, uma por linha: `id\|Descrição\|sim` (`sim` pede confirmação por botão; senão `nao`). Um `id` sem `:` aparece como `/astro <projeto>:<id>`; com `:`, aparece como está (ex.: `backup:cloud`) e é atendido pelo projeto que o declarou. Nomes em inglês; a descrição começa pelo nome padrão da operação (ex.: `Backup: local 🔄 nuvem`). Os nomes `start`, `stop` e `restart` são do executor (containers `astroverso-<projeto>*`) |
| `help` (opcional) | Linhas da ajuda do Discord (`/astro command:help`), uma por operação: `grupo\|nome\|o que é\|quando\|comando\|ordem` (comando `-` quando só existe no assistente; ordem numérica dentro do grupo, padrão 50) |
| `remote <id> [argumento]` (opcional) | Roda uma ação de `remote-actions` sem perguntas e imprime o resultado em texto (vai para o Discord). O argumento já chega validado (`[A-Za-z0-9._-]`, até 64) |
| `backup` (opcional) | Prepara cópias consistentes (ex.: dump de banco) e imprime, uma por linha, `exclude <caminho>` (fora do backup das configurações) ou `add <caminho>` (entra mesmo dentro de um `exclude`). Chamado pelo rclone à 01:00, no "Fazer backup agora" e no "Implodir Astroverso". Logs vão para a saída de erro |

**Estado fora do repositório.** Tudo o que a instalação gera fica em `~/.astroverso/<projeto>` (`$STATE`): o `.env`
(`$ENV_FILE`), o `.proxy`, dados e certificados. O `cmd_install` começa com `state_setup`, que cria a pasta
(`700`), e o `remove` termina com `state_purge`, que a apaga (`podman unshare rm -rf`). O compose usa `${ASTROVERSO_STATE}` nos volumes e no `env_file`,
e roda pela função `compose` (`podman compose --env-file "$ENV_FILE"`). Um serviço que roda com outro usuário
guarda a configuração no `~/.astroverso/<projeto>` desse usuário, legível pelo usuário que instala (ACL) para o
backup.

Todo `docker-compose.yml` de subprojeto deve começar com o grupo `astroverso` e sem pod, para que os
containers fiquem agrupados mas independentes (remover um não afeta os outros):

```yaml
name: astroverso

x-podman:
  in_pod: false
```

Para publicar um endereço no Caddy, o projeto chama `proxy_publish <endereço> <destino>` (de `lib/proxy.sh`),
que escreve `~/.astroverso/<projeto>/.proxy` e recarrega o Caddy se ele estiver instalado. O Caddy junta essas
rotas com as cadastradas manualmente, e as do projeto têm prioridade. Containers do grupo `astroverso` são
alcançados pelo nome; serviços do próprio sistema e containers na rede do host, por `host.containers.internal`. Um destino
`https+insecure://<host>:<porta>` aceita um certificado autoassinado (ex.: painéis que só abrem em HTTPS).

Bibliotecas compartilhadas:

- `lib/ui.sh`: logs com prefixo `[projeto]` (`ui_step`, `ui_ok`, `ui_info`, `ui_warn`, `ui_error`, `ui_fail`),
  prompts (`ui_input`, `ui_secret`, `ui_confirm`, `ui_list`), `ui_menu` e `ui_checklist` (sem eco do terminal enquanto abertos; setas `ESC [`/`ESC O`, com 0,5s de espera pelo resto da sequência) (`--selected "0 2"` antes
  dos itens deixa esses índices já marcados; `--all` põe uma opção "Todos" no topo; `--esc` faz o Esc cancelar,
  com a lista vazia e `UI_CANCELLED=1`; sem ele, o Esc é ignorado). No `ui_menu`, o Esc escolhe o último item
  quando ele se chama "Voltar" ou "Sair" (e a dica na tela avisa); nos outros menus, ele é ignorado. `ui_browse VAR título
  raiz...` navega pelas pastas a partir das raízes (setas, rolagem de 12 em 12, "usar esta pasta", "voltar" e
  "digitar um caminho"; esconde pastas ocultas, `$RECYCLE.BIN`, `System Volume Information` e `lost+found`). Com `ASTROVERSO_PLAIN=1` (serviços do systemd), as mensagens saem sem
  cores, para o journal. Defina `ASTROVERSO_PROJECT` antes do `source`.
  `ui_input VAR rótulo [padrão] [validador]` e `ui_list VAR rótulo [validador]` repetem a pergunta enquanto o
  validador recusar a resposta.
- `lib/host.sh`: preparação genérica do host. `host_base` reúne o que todo projeto precisa (o comando `astroverso` em `~/.local/bin`, apontando para o
  `setup.sh`; máquina sem suspensão, podman-compose, inicialização no boot, SSH e Tailscale; chamado uma vez pelo `setup.sh`, na etapa Máquina), e `host_undo` desfaz o que é só do Astroverso
  (comando `astroverso`, suspensão, também a da tela de login, portas baixas, rede anunciada no Tailscale, login só por chave no SSH, linger e `podman-restart`;
  o SSH continua ativo), chamado pelo "Implodir Astroverso". Funções avulsas: `host_upgrade` (dnf ou apt; avisa e marca `HOST_REBOOT` se veio kernel novo; chamada pelo `setup.sh` uma vez
  antes de instalar, não pelos projetos), `host_no_sleep`,
  `host_unprivileged_ports`, `host_compose`, `host_autostart`, `host_ssh`,
  `host_firewall` / `host_firewall_remove` (portas `N/proto` ou serviços), `host_firewall_block_lan PORTA` / `host_firewall_unblock_lan PORTA` (porta acessível só
  pela própria máquina, ex.: atrás do Caddy), `host_tailscale` (instala via dnf/apt se preciso, oferece anunciar a rede local e pede o
  redirecionamento da porta UDP do Tailscale no roteador),
  `host_nvidia_driver` (instala o driver proprietário se houver placa NVIDIA, atualizando o kernel no Fedora e
  cadastrando a chave no Secure Boot; marca `HOST_REBOOT=true` quando falta reiniciar), `host_nvidia_version`, `host_rpmfusion`, `host_intel_media` (driver VAAPI completo da Intel no Fedora),
  `host_lan_ip`, `host_lan_subnet`, `host_tailscale_ip`, `host_state_set CHAVE [valor]` (grava ou apaga, sem valor, uma
  linha do `~/.astroverso/host.env`). Máquinas da rede (Wake-on-LAN): `host_machines_manage` (menu da Administração),
  `host_machines` (`nome ip mac` de cada `WAKE_<nome>=<ip>,<mac>` do `host.env`), `host_wake <nome>` (pacote mágico
  por broadcast, de 4 em 4 segundos, até a máquina responder ou passar de 2 minutos; usado pelo `machine:wake` do
  Discord) e `host_online <ip>` (ping ou, com ICMP bloqueado como no Windows, o ARP em `REACHABLE`).
- `lib/env.sh`: `ASTROVERSO_HOME`, `STATE`, `ENV_FILE`, `compose`, `state_setup` e `state_purge` (acima), `images_remove`
  (apaga as imagens do `docker-compose.yml` e os `FROM` do `Dockerfile` do projeto) e `state_restore <pasta> [itens a manter]`,
  que troca `$STATE` pela pasta do backup, mantendo os itens pedidos da configuração atual. `env_get CHAVE [padrão]
  [arquivo]` lê valores do `.env` do projeto (ou de outro arquivo). Validadores para as perguntas,
  que imprimem o valor normalizado ou falham: `is_port`, `is_ipv4`, `is_mac` (aceita `-`, devolve minúsculo com `:`), `is_machine` (nome de máquina, minúsculo), `is_hostname`, `is_name`, `is_label` (nome com espaços, até 40), `is_username`, `is_timezone`, `is_path` (caminho absoluto),
  `is_folder` (nome de uma pasta, sem `/` e sem começar por `.`), `is_relpath` (caminho relativo, com espaços; `/` ou vazio
  vira vazio), `is_host` (IP, nome com domínio ou nome simples da rede local), `is_drive` (letra de disco do Windows, com ou sem
  `:`, em maiúscula), `is_email`, `is_time` (`HH:MM`) e `is_number`.
  Toda resposta que vai para `.env`, configuração ou Caddyfile deve passar por um deles. `config_reuse` faz a
  pergunta "usar a configuração já salva?" (falso sem `.env`); com `ASTROVERSO_REUSE_CONFIG=1` (troca de domínio),
  responde sim sem perguntar, e o projeto não deve fazer outras perguntas opcionais nesse caminho.
- `lib/proxy.sh`: `proxy_domain` (domínio do Caddy, se configurado), `proxy_publish`, `proxy_unpublish` e `proxy_reload`.
- `lib/notify.sh`: avisos pelo bot do projeto `discord` (deixa um arquivo na fila `~/.astroverso/discord/fila/saida`;
  sem o projeto instalado, nada é enviado). `notify_problem <chave> <texto> [botões]` avisa um problema no máximo
  uma vez por dia (marca em `~/.local/state/astroverso/notify/<projeto>-<chave>`); `notify_resolved <chave> <texto>`
  avisa que ele acabou, só se houve aviso, em mensagem silenciosa. `notify_send <texto> [botões]` manda direto;
  `notify_info <texto> [botões]` também, mas silenciosa (fica no canal, sem notificar o celular). Cada botão é
  `"Rótulo|<projeto>:<ação>|<argumento>"` e roda a ação como o `/astro`. Nenhuma delas derruba o chamador.
  O canal do Discord vem de `NOTIFY_CHANNEL` (definido pelo projeto ao lado do `ASTROVERSO_PROJECT`: `dados`,
  `sistema`, `financeiro`); sem ele, o canal principal.
  Precisa de `lib/ui.sh`.
- `lib/brand.sh`: a paleta (`BRAND_BACKGROUND`, `BRAND_LIGHT`, `BRAND_PURPLE`, `BRAND_VIOLET`, `BRAND_ACCENT`), o nome
  (`BRAND_NAME`) e a pasta das imagens (`BRAND_DIR`, a `logo/` do repositório). Ver `logo/README.md`.
- `lib/disk.sh`: discos de dados **da máquina**, montados pelo sistema no boot. Nenhum disco pertence a um
  projeto: o dono é sempre quem instala, e os projetos só escolhem quais usar (pelo caminho em `/srv`).
  - `disk_manage` é a etapa "Discos da máquina" do `setup.sh` (na instalação e na Administração): lista os discos (menos o do sistema), com os
    configurados já marcados, pergunta quais são compartilhados e chama o `disk_setup`. Tirar um disco da lista
    pede confirmação.
  - `disk_setup uuid:tipo...` (tipo `privado` ou `compartilhado`) cadastra o TPM nos discos LUKS (pede a senha só
    se o TPM ainda não destravar), escreve as linhas no `/etc/crypttab` e no `/etc/fstab` (cada uma depois de um
    comentário `# astroverso <uuid> [tipo]`;
    as linhas também são reconhecidas pela assinatura, mesmo separadas da marca: no `fstab`, destino em `/srv/` com
    `x-udisks-auth` e `container_file_t`; no `crypttab`, `luks-*` com `headless=true`), desmonta o que a sessão gráfica montou e monta em `/srv/<rótulo>`. Num LUKS2
    sem nome no cabeçalho, copia para lá o rótulo do sistema de arquivos (`cryptsetup config --label`), para o
    disco aparecer com nome na lista mesmo travado. Sem nome nenhum, a lista mostra o dispositivo e o UUID. Deixa os
    caminhos em `DISK_MOUNTS`. Um disco já montado só é remontado se mudarem as opções que não são `x-*`
    (`uid`, `gid`, `umask`, `context`); em uso, as opções novas valem no próximo boot.
  - `disk_release_all` (do "Implodir Astroverso") desmonta todos os discos do Astroverso, tira as linhas do `fstab` e do
    `crypttab`, os links de religar e as pastas de `/srv`, e descadastra o TPM dos discos LUKS (a senha continua).
  - **Privado:** pasta principal `770` (dono e grupo de quem instala), `umask=077` em NTFS/exFAT/FAT,
    `x-gvfs-hide` e `x-systemd.before=user@<uid>.service` (monta antes dos containers de quem instala).
  - **Compartilhado:** pasta principal `777`, `umask=000` em NTFS/exFAT/FAT, `x-gvfs-show` (aparece no Arquivos
    de todos) e `x-systemd.before=systemd-user-sessions.service` (monta antes de qualquer login). Arquivos
    criados pelo Linux guardam a permissão de quem os criou.
  - Todos levam `context=system_u:object_r:container_file_t:s0`: o SELinux libera os containers sem reetiquetar.
  - Toda montagem leva `nofail` e `x-udisks-auth`. Disco comum: espera de 10s. Disco LUKS: `headless=true` no
    `crypttab` e, no `fstab`, `x-systemd.requires=` do serviço do `cryptsetup` com espera de 5min (o TPM pode
    levar quase um minuto no boot; disco ausente falha em 10s pelo `crypttab`). Nada
    pede senha no boot: um disco ausente ou que o TPM não destrava fica de fora e a máquina sobe.
  - Disco desligado e religado (cabo, troca de case) volta a montar sozinho: um link em
    `/etc/systemd/system/<dispositivo>.device.wants/` liga a montagem ao disco. No LUKS, o disco liga o
    `cryptsetup`, e a montagem fica em `systemd-cryptsetup@<mapeamento>.service.wants/`.
  - "Discos da máquina" lista também os discos configurados que estão desligados (`desligado`), já marcados:
    desmarcar um deles o tira do `fstab`/`crypttab` sem precisar ligá-lo.
  - A pasta vazia em `/srv` fica imutável (`chattr +i`): sem o disco, nada grava nela.
  - `disk_responds <caminho>` confere se um disco montado ainda responde: no LUKS, se o dispositivo por baixo
    existe; em todos, se a pasta principal e a lista dela são lidas em até 20s. O `disk_manage` liga o timer de
    usuário `astroverso-disk-check` (5 min depois do boot e a cada 15 min, `lib/disk-check.sh`), que avisa no Discord
    (`notify_problem`, uma vez por dia) um disco da máquina desmontado ou que parou de responder, e avisa quando
    ele volta. O `disk_release_all` o desliga.
  - `disk_mounts` lista os discos da máquina (`/srv/<rótulo> tipo`), lidos do `fstab`; `disk_type <caminho>` dá
    o tipo.
  - Discos tirados da lista são desmontados e saem dos dois arquivos. Os dados nunca são apagados.
