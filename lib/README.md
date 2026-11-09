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

Todo `docker-compose.yml` de subprojeto deve começar com o grupo `astro` e sem pod, para que os
containers fiquem agrupados mas independentes (remover um não afeta os outros):

```yaml
name: astro

x-podman:
  in_pod: false
```

Para publicar um endereço no Caddy, o projeto chama `proxy_publish <endereço> <destino>` (de `lib/proxy.sh`),
que escreve `<projeto>/.proxy` (fora do git) e recarrega o Caddy se ele estiver instalado. O Caddy junta essas
rotas com as cadastradas manualmente, e as do projeto têm prioridade. Containers do grupo `astro` são
alcançados pelo nome; serviços do próprio sistema e containers na rede do host, por `host.containers.internal`. Um destino
`https+insecure://<host>:<porta>` aceita um certificado autoassinado (ex.: painéis que só abrem em HTTPS).

Bibliotecas compartilhadas:

- `lib/ui.sh`: logs com prefixo `[projeto]` (`ui_step`, `ui_ok`, `ui_info`, `ui_warn`, `ui_error`, `ui_fail`),
  prompts (`ui_input`, `ui_secret`, `ui_confirm`, `ui_list`), `ui_menu` e `ui_checklist`. Defina `ASTRO_PROJECT` antes do `source`.
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
- `lib/env.sh`: `env_get CHAVE [padrão]` lê valores do `.env` do projeto. Validadores para as perguntas,
  que imprimem o valor normalizado ou falham: `is_port`, `is_ipv4`, `is_hostname`, `is_name`, `is_username`, `is_timezone`, `is_path` (caminho absoluto).
  Toda resposta que vai para `.env`, configuração ou Caddyfile deve passar por um deles.
- `lib/proxy.sh`: `proxy_domain` (domínio do Caddy, se configurado), `proxy_publish`, `proxy_unpublish` e `proxy_reload`.
- `lib/disk.sh`: discos de dados de um projeto, montados pelo sistema no boot.
  - `disk_choose VAR projeto título` lista os discos (sem o do sistema e sem os de outro projeto) e devolve os UUIDs
    marcados, que o projeto grava no `.env`.
  - `disk_setup projeto opções uuid...` cadastra o TPM nos discos LUKS (pede a senha só se o TPM ainda não
    destravar), escreve as linhas do projeto no `/etc/crypttab` e no `/etc/fstab` (cada uma depois de um comentário
    `# astro:<projeto> <uuid>`), desmonta o que a sessão gráfica montou e monta em `/srv/<rótulo>`. Deixa os
    caminhos em `DISK_MOUNTS`. As `opções` são acrescentadas às da montagem (ex.: `uid=`, `context=`).
  - Toda montagem leva `nofail`, espera de 10s pelo disco e `x-udisks-auth`; o LUKS leva `headless=true`. Nada
    pede senha no boot: um disco ausente ou que o TPM não destrava fica de fora e a máquina sobe.
  - A pasta vazia em `/srv` fica imutável (`chattr +i`): sem o disco, nada grava nela.
  - Discos tirados da lista são desmontados e saem dos dois arquivos. `disk_release projeto` libera todos.
    Os dados nunca são apagados.
