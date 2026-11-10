# Criando um projeto

O `setup.sh` reconhece qualquer pasta com um `project.sh` executável que implemente:

| Comando | Responsabilidade |
|---|---|
| `describe` | Imprime uma linha de descrição |
| `status` | Sai com código 0 se o projeto está instalado |
| `install` | Pergunta a configuração, prepara o host e sobe os containers |
| `remove [--purge]` | Remove os containers; com `--purge`, apaga também os dados |
| `actions` | Lista as ações de pós-configuração, uma por linha no formato `id\|Descrição` (vazio se não houver) |
| `action <id>` | Executa uma ação listada em `actions` |
| `global-actions` (opcional) | Como `actions`, mas as ações aparecem no menu principal do `setup.sh` (com o projeto instalado) e rodam com `action <id>` |
| `restore <pasta>` (opcional) | Troca a configuração pela da pasta extraída do backup (`state_restore`), cuidando do que for do projeto (ex.: carregar o dump do banco), e sobe o serviço de novo |
| `remote-actions` (opcional) | Ações para o Discord, uma por linha: `id\|Descrição\|sim` (`sim` pede confirmação por botão; senão `nao`). Aparecem como `/astro <projeto>:<id>`. Nomes em inglês (`sync`, `backup-configs`). Os nomes `start`, `stop` e `restart` são do executor (containers `astro-<projeto>*`) |
| `remote <id> [argumento]` (opcional) | Roda uma ação de `remote-actions` sem perguntas e imprime o resultado em texto (vai para o Discord). O argumento já chega validado (`[A-Za-z0-9._-]`, até 64) |
| `backup` (opcional) | Prepara cópias consistentes (ex.: dump de banco) e imprime, uma por linha, `exclude <caminho>` (fora do backup das configurações), `include <nome> <caminho>` (entra no arquivo do serviço como `<serviço>/<nome>`) ou `add <caminho>` (entra mesmo dentro de um `exclude`). Chamado pelo rclone à 01:00 |

**Estado fora do repositório.** Tudo o que a instalação gera fica em `~/.astro/<projeto>` (`$STATE`): o `.env`
(`$ENV_FILE`), o `.proxy`, dados e certificados. O `cmd_install` começa com `state_setup <função que para o
projeto> <itens>`, que cria a pasta e move para ela o que ainda estiver no lugar antigo (`<projeto>/<item>`),
mantendo donos e permissões (`podman unshare mv`). O compose usa `${ASTRO_STATE}` nos volumes e no `env_file`,
e roda pela função `compose` (`podman compose --env-file "$ENV_FILE"`). Um serviço que roda com outro usuário
guarda a configuração no `~/.astro/<projeto>` desse usuário, legível pelo usuário que instala (ACL) para o
backup.

Todo `docker-compose.yml` de subprojeto deve começar com o grupo `astro` e sem pod, para que os
containers fiquem agrupados mas independentes (remover um não afeta os outros):

```yaml
name: astro

x-podman:
  in_pod: false
```

Para publicar um endereço no Caddy, o projeto chama `proxy_publish <endereço> <destino>` (de `lib/proxy.sh`),
que escreve `~/.astro/<projeto>/.proxy` e recarrega o Caddy se ele estiver instalado. O Caddy junta essas
rotas com as cadastradas manualmente, e as do projeto têm prioridade. Containers do grupo `astro` são
alcançados pelo nome; serviços do próprio sistema e containers na rede do host, por `host.containers.internal`. Um destino
`https+insecure://<host>:<porta>` aceita um certificado autoassinado (ex.: painéis que só abrem em HTTPS).

Bibliotecas compartilhadas:

- `lib/ui.sh`: logs com prefixo `[projeto]` (`ui_step`, `ui_ok`, `ui_info`, `ui_warn`, `ui_error`, `ui_fail`),
  prompts (`ui_input`, `ui_secret`, `ui_confirm`, `ui_list`), `ui_menu` e `ui_checklist` (`--selected "0 2"` antes
  dos itens deixa esses índices já marcados; `--all` põe uma opção "Todos" no topo). Com `ASTRO_PLAIN=1` (serviços do systemd), as mensagens saem sem
  cores, para o journal. Defina `ASTRO_PROJECT` antes do `source`.
  `ui_input VAR rótulo [padrão] [validador]` e `ui_list VAR rótulo [validador]` repetem a pergunta enquanto o
  validador recusar a resposta.
- `lib/host.sh`: preparação genérica do host. `host_base` reúne o que todo projeto precisa (máquina sem
  suspensão, podman-compose, inicialização no boot, SSH e Tailscale). Funções avulsas: `host_upgrade` (dnf ou apt; avisa e marca `HOST_REBOOT` se veio kernel novo; chamada pelo `setup.sh` uma vez
  antes de instalar, não pelos projetos), `host_no_sleep`,
  `host_unprivileged_ports`, `host_compose`, `host_autostart`, `host_ssh`,
  `host_firewall`, `host_firewall_block_lan PORTA` / `host_firewall_unblock_lan PORTA` (porta acessível só
  pela própria máquina, ex.: atrás do Caddy), `host_tailscale` (instala via dnf/apt se preciso, oferece anunciar a rede local e pede o
  redirecionamento da porta UDP do Tailscale no roteador),
  `host_nvidia_driver` (instala o driver proprietário se houver placa NVIDIA, atualizando o kernel no Fedora e
  cadastrando a chave no Secure Boot; marca `HOST_REBOOT=true` quando falta reiniciar), `host_nvidia_version`, `host_rpmfusion`, `host_intel_media` (driver VAAPI completo da Intel no Fedora),
  `host_lan_ip`, `host_lan_subnet`, `host_tailscale_ip`.
- `lib/env.sh`: `ASTRO_HOME`, `STATE`, `ENV_FILE`, `compose`, `state_setup` (acima) e `state_restore <pasta> [itens a manter]`,
  que troca `$STATE` pela pasta do backup, mantendo os itens pedidos da configuração atual. `env_get CHAVE [padrão]
  [arquivo]` lê valores do `.env` do projeto (ou de outro arquivo). Validadores para as perguntas,
  que imprimem o valor normalizado ou falham: `is_port`, `is_ipv4`, `is_hostname`, `is_name`, `is_username`, `is_timezone`, `is_path` (caminho absoluto),
  `is_folder` (nome de uma pasta, sem `/` e sem começar por `.`), `is_email`, `is_time` (`HH:MM`) e `is_number`.
  Toda resposta que vai para `.env`, configuração ou Caddyfile deve passar por um deles.
- `lib/proxy.sh`: `proxy_domain` (domínio do Caddy, se configurado), `proxy_publish`, `proxy_unpublish` e `proxy_reload`.
- `lib/notify.sh`: avisos pelo bot do projeto `discord` (deixa um arquivo na fila `~/.astro/discord/fila/saida`;
  sem o projeto instalado, nada é enviado). `notify_problem <chave> <texto> [botões]` avisa um problema no máximo
  uma vez por dia (marca em `~/.local/state/astro/notify/<projeto>-<chave>`); `notify_resolved <chave> <texto>`
  avisa que ele acabou, só se houve aviso. `notify_send <texto> [botões]` manda direto. Cada botão é
  `"Rótulo|<projeto>:<ação>|<argumento>"` e roda a ação como o `/astro`. Nenhuma delas derruba o chamador.
  Precisa de `lib/ui.sh`.
- `lib/disk.sh`: discos de dados de um projeto, montados pelo sistema no boot.
  - `disk_choose VAR projeto título [uuids atuais]` lista os discos (sem o do sistema e sem os de outro projeto),
    com os atuais já marcados, e devolve os UUIDs marcados, que o projeto grava no `.env`.
  - `disk_setup projeto opções uuid...` cadastra o TPM nos discos LUKS (pede a senha só se o TPM ainda não
    destravar), escreve as linhas do projeto no `/etc/crypttab` e no `/etc/fstab` (cada uma depois de um comentário
    `# astro:<projeto> <uuid>`), desmonta o que a sessão gráfica montou e monta em `/srv/<rótulo>`. Num LUKS2
    sem nome no cabeçalho, copia para lá o rótulo do sistema de arquivos (`cryptsetup config --label`), para o
    disco aparecer com nome na lista mesmo travado. Sem nome nenhum, a lista mostra o dispositivo e o UUID. Deixa os
    caminhos em `DISK_MOUNTS`. As `opções` são acrescentadas às da montagem (ex.: `uid=`, `context=`).
  - Toda montagem leva `nofail` e `x-udisks-auth`. Disco comum: espera de 10s. Disco LUKS: `headless=true` no
    `crypttab` e, no `fstab`, `x-systemd.requires=` do serviço do `cryptsetup` com espera de 5min (o TPM pode
    levar quase um minuto no boot; disco ausente falha em 10s pelo `crypttab`). Nada
    pede senha no boot: um disco ausente ou que o TPM não destrava fica de fora e a máquina sobe.
  - Disco desligado e religado (cabo, troca de case) volta a montar sozinho: um link em
    `/etc/systemd/system/<dispositivo>.device.wants/` liga a montagem (e o `cryptsetup`, no LUKS) ao disco.
  - A pasta vazia em `/srv` fica imutável (`chattr +i`): sem o disco, nada grava nela.
  - `disk_mounts [projeto a ignorar]` lista as montagens do astro (`/srv/<rótulo> projeto`), lidas do `fstab`.
  - Discos tirados da lista são desmontados e saem dos dois arquivos. `disk_release projeto` libera todos.
    Os dados nunca são apagados.
