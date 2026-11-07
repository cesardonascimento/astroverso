# astro

Infraestrutura pessoal em containers (Podman), versionada para subir idêntica em qualquer PC.

## Uso

```bash
gh repo clone cesardonascimento/astro ~/Projects/astro
~/Projects/astro/setup.sh
```

O assistente oferece:

1. **Instalar todos**: instala os projetos que ainda não estão instalados
2. **Escolher quais instalar**: lista com checkboxes (↑/↓, Espaço marca, `a` marca todos, Enter confirma); os já instalados são recriados
3. **Configurar um projeto instalado**: ajustes depois da instalação, oferecidos por cada projeto (ex: rotas do Caddy)
4. **Reinstalar tudo do zero**: apaga os dados de todos os projetos e instala de novo (as respostas salvas no `.env` podem ser reaproveitadas)
5. **Remover todos os containers**: mantendo os dados ou apagando também os volumes

Ao final de cada operação o menu volta, até você escolher **Sair**.

Cada projeto pergunta as informações de que precisa (senhas, portas etc.) durante a instalação
e guarda as respostas em `<projeto>/.env`, que fica fora do git. Rode em um terminal interativo:
o `sudo` pode pedir senha na primeira instalação em cada máquina.

## Projetos

| Projeto | Descrição |
|---|---|
| [adguard](adguard/) | AdGuard Home: DNS da rede com bloqueio de anúncios |
| [caddy](caddy/) | Caddy: proxy reverso com HTTPS para os serviços da rede |

## Adicionando um projeto

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

Bibliotecas compartilhadas:

- `lib/ui.sh`: logs com prefixo `[projeto]` (`ui_step`, `ui_ok`, `ui_info`, `ui_warn`, `ui_error`, `ui_fail`),
  prompts (`ui_input`, `ui_secret`, `ui_confirm`, `ui_list`), `ui_menu` e `ui_checklist`. Defina `ASTRO_PROJECT` antes do `source`.
- `lib/host.sh`: preparação genérica do host (`host_unprivileged_ports`, `host_compose`, `host_autostart`,
  `host_firewall`, `host_tailscale` (instala via dnf/apt se preciso e oferece anunciar a rede local),
  `host_lan_ip`, `host_lan_subnet`, `host_tailscale_ip`).
- `lib/env.sh`: `env_get CHAVE [padrão]` lê valores do `.env` do projeto.
