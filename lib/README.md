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
alcançados pelo nome; serviços do próprio sistema e containers na rede do host, por `host.containers.internal`.

Bibliotecas compartilhadas:

- `lib/ui.sh`: logs com prefixo `[projeto]` (`ui_step`, `ui_ok`, `ui_info`, `ui_warn`, `ui_error`, `ui_fail`),
  prompts (`ui_input`, `ui_secret`, `ui_confirm`, `ui_list`), `ui_menu` e `ui_checklist`. Defina `ASTRO_PROJECT` antes do `source`.
- `lib/host.sh`: preparação genérica do host. `host_base` reúne o que todo projeto precisa (máquina sem
  suspensão, podman-compose, inicialização no boot, SSH e Tailscale). Funções avulsas: `host_no_sleep`,
  `host_unprivileged_ports`, `host_compose`, `host_autostart`, `host_ssh`,
  `host_firewall`, `host_tailscale` (instala via dnf/apt se preciso e oferece anunciar a rede local),
  `host_lan_ip`, `host_lan_subnet`, `host_tailscale_ip`.
- `lib/env.sh`: `env_get CHAVE [padrão]` lê valores do `.env` do projeto.
- `lib/proxy.sh`: `proxy_domain` (domínio do Caddy, se configurado), `proxy_publish`, `proxy_unpublish` e `proxy_reload`.
