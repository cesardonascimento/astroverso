# kit

Pacote base dos apps do Astroverso. Só a biblioteca padrão do Python.

```python
from kit import ui
```

Testes: `python3 -m unittest discover -s packages -t packages` (todos os pacotes).

## ui

Logs, perguntas e menus, sempre com o prefixo do app (`[astroverso]` se `ui.set_app` não for chamado). As cores
seguem a paleta da marca e mudam conforme o contexto. Saem sem cor quando a saída não é um terminal (systemd,
journal, redirecionamento) ou com `NO_COLOR`. Elas usam 24 bits com `COLORTERM=truecolor`, 256 cores com
`TERM=*256*` e as 16 básicas no resto.

| Função | O que faz |
|---|---|
| `set_app(nome)` | Troca o prefixo, também no `SUDO_PROMPT` herdado pelo `sudo` |
| `banner()` | Mostra o logo do Astroverso: ao lado do nome, em cima dele ou só o nome, conforme a largura do terminal. Sem terminal, não mostra nada |
| `step`, `info`, `ok`, `warn` | Etapa e mensagens (saída padrão) |
| `error(texto)` / `fail(texto)` | Erro na saída de erro; `fail` também encerra com código 1 |
| `prefixed(texto)` | Saída de um comando, linha a linha, com o prefixo e em cinza |
| `note(texto)` | Explicação em itálico, recuada e quebrada na largura do terminal (antes de uma pergunta ou etapa) |
| `link(rótulo, url)` | `→ rótulo: url`, com o endereço sublinhado e sem quebra (para o terminal reconhecer o link) |
| `section(título)` | Título de um bloco, como as tabelas de um resumo |
| `table(linhas, columns=)` | Tabela com bordas arredondadas (sem `columns`, vira uma tabela de rótulo e valor). Células com situação: `good` (✔ verde), `pending` (! âmbar), `off` (○ cinza), `bad` (✘ vermelho). As colunas encolhem com `…` se o terminal for estreito; sem cor, sai em colunas alinhadas, sem bordas |
| `ask(rótulo, default=, validate=)` | Pergunta e devolve o texto, repetindo enquanto o validador recusar |
| `secret(rótulo, confirm=True)` | Pergunta sem eco, com confirmação (ou sem, com `confirm=False`) |
| `ask_list(rótulo, validate=)` | Lista de valores, um por pergunta, até um Enter vazio |
| `confirm(pergunta, default=False)` | Sim ou não (`s`, `sim`, `n`, `não`...) |
| `menu(título, itens, details=)` | Devolve o índice escolhido. `details`: um texto em cinza ao lado de cada item, alinhado |
| `checklist(título, itens, selected=, all_option=, cancel=, details=)` | Devolve os índices marcados, ou `None` se cancelado com Esc |

- **Validadores** recebem o texto e devolvem o valor normalizado, ou levantam `ValueError("motivo")`. O motivo
  aparece na tela.
- **Perguntas e menus** usam `/dev/tty`. Sem terminal, terminam com "sem terminal para perguntar". Depois da
  resposta, a pergunta vira uma linha com o valor escolhido (segredos aparecem como `••••••••`).
- **Teclas:** ↑/↓ (ou `k`/`j`), Home, End, PgUp, PgDn, 1 a 9 no menu, Espaço e `a` (todos) no checklist. Esc
  escolhe o último item do menu quando ele é "Voltar" ou "Sair". No checklist, Esc só cancela com `cancel=True`.
  Nos outros casos, é ignorado.
- Listas maiores que o terminal rolam, com o contador "N de M".
- O terminal é restaurado (eco, cursor, quebra de linha) mesmo com Ctrl+C, que chega ao chamador como
  `KeyboardInterrupt`.

## run

A única porta para comandos do sistema: os apps não chamam o `subprocess` direto. Só listas de argumentos.

| Função | Na tela | Se falhar |
|---|---|---|
| `cmd(args, sudo=, input=, quiet=, timeout=)` | Saída e erros, linha a linha, ao vivo, com o prefixo e em cinza | `ui.fail` com o comando e o código. Com `quiet=True`, a saída só aparece se der erro |
| `capture(args, sudo=, input=, timeout=)` | Nada: devolve a saída padrão (sem o `\n` do fim) | `ui.fail`, mostrando a saída de erro |
| `succeeds(args, sudo=, timeout=)` | Nada | Devolve `False` (também para comando inexistente ou tempo esgotado) |
| `sudo_prepare(motivo)` | Explica o motivo e pede a senha uma vez (`sudo -v`), se ainda não houver permissão | Sem terminal: "rode num terminal" |

- **Segredos** só por `input=` (entrada padrão), nunca nos argumentos.
- `sudo=True` põe `sudo` na frente; sem terminal (systemd), `sudo -n`, que falha na hora em vez de esperar senha.
- Sem `input=`, o comando herda o terminal: o que pede uma ação do usuário (ex.: o endereço de login do
  `tailscale up`) aparece ao vivo e espera.

## distro

Pacotes, serviços, firewall e ajustes do sistema, sem que o app saiba qual é a distribuição. `kit/distro/__init__.py`
lê o `/etc/os-release` e repassa para o módulo dela (`fedora.py`). Distribuição sem módulo: `distro.check()` (chamado
pelo gerenciador antes de tudo, menos no `status`) termina com "distribuição não suportada: <nome>".

| Grupo | Funções |
|---|---|
| Pacotes | `installed(pacote)`, `install(pacotes)`, `uninstall(pacotes)`, `add_repo(nome, url)`, `remove_repo(nome)` |
| Serviços do sistema | `service_active(nome)`, `service_enable(nome)` (agora e no boot), `service_disable(nome)` |
| Firewall | `firewall_open(itens)`, `firewall_close(itens)` (portas `N/proto` ou serviços), `firewall_allowed(item)` (liberado, inclusive dentro de uma faixa; verdadeiro sem firewall), `firewall_masquerade(ligado)` |
| sysctl | `sysctl_set(nome, valores)` (`/etc/sysctl.d/99-astroverso-<nome>.conf`, aplicado na hora), `sysctl_remove(nome)` |

- Tudo é idempotente: só age, e só mostra um ✔, quando algo muda.
- Fedora: `dnf -q`; o arquivo do repositório é baixado pelo Python e gravado em `/etc/yum.repos.d/<nome>.repo`.
- Firewall só com o `firewalld` ativo (conferido pelo `systemctl`: o `firewall-cmd --state` pede o polkit). As
  consultas usam a configuração em uso (sem `sudo`); as mudanças vão para a permanente, com `--reload`. Abrir e
  fechar comparam o item exato da lista: uma porta dentro de uma faixa liberada é aberta à parte, e fechar nunca
  parte uma faixa.
- `sysctl_remove` apaga o arquivo e reaplica os outros; o valor em uso só volta ao padrão por completo depois de
  reiniciar.

## config

O estado de cada app em `~/.astroverso/<app>` (fora do repositório).

| Função | O que faz |
|---|---|
| `state(app)` | Cria a pasta do app (`700`) e devolve o caminho |
| `load(app)` / `save(app, valores)` | Lê e grava o `.env` do app (`CHAVE=valor`, `600`). O `save` junta com o que já existe; `None` apaga a chave. Gravação atômica; chaves em maiúsculas e valores sem quebra de linha |
| `read_env(arquivo)` / `write_env(arquivo, valores)` | Leem e gravam qualquer arquivo `CHAVE=valor` (gravação atômica, `600`), como os compartilhados entre apps |
| `reuse(app)` | "Usar a configuração já salva?" (falso sem perguntar, se não houver `.env`) |
| `domain()` | O domínio dos endereços, em `~/.astroverso/astroverso.env` (`DOMAIN`), perguntado e guardado na primeira vez |
| `purge(app)` | Apaga a pasta do app (com `podman unshare` se houver arquivos de containers). Só aceita um nome de app válido, nunca atalhos nem a pasta inteira |

## validate

Validadores para `ui.ask`: devolvem o valor normalizado ou levantam `ValueError` com o motivo.
`domain` (minúsculo; tira `http://`, `*.` e o ponto ou barra do fim), `ipv4`, `port`, `name` (minúsculo, letras,
números e hífen, até 63) e `email`. Toda resposta que vai para um `.env` ou um arquivo de configuração passa por
um deles.

## net

- `lan_ip()`: o IP da máquina na rede de casa, pelo endereço de saída de um socket UDP (nenhum pacote é enviado).
  Um IP do Tailscale (`100.64.0.0/10`, com exit node) ou a falta de rede terminam com "IP da rede local não
  encontrado": tudo funciona pela rede local.
- `hostname()`: o nome curto da máquina, em minúsculas.

## container

Containers como unidades do systemd do usuário, por Quadlet (sem podman-compose).

```python
from kit import container

spec = container.Container(
    name="astroverso-network-adguard",
    image="docker.io/adguard/adguardhome:v0.107.80",
    description="Astroverso network: AdGuard",
    network="host",
    volumes=[container.Volume(pasta / "conf", "/opt/adguardhome/conf")],
    health="wget -q --spider http://127.0.0.1:8080/login.html",
)
container.prepare()
container.start(spec)
container.remove(spec.name, spec.image)
```

| Função | O que faz |
|---|---|
| `prepare()` | Instala o Podman e liga o *linger* (os containers sobem no boot sem ninguém logado) |
| `restart(spec)` | Reinicia o container e espera ficar pronto (ex.: quando o `env_file` mudou) |
| `start(spec, timeout=180)` | Baixa a imagem, grava `~/.config/containers/systemd/<nome>.container` (e o `.network` da rede), recarrega o systemd, reinicia a unidade se algo mudou ou se ela estava parada e espera o container ficar `healthy` (com `health`) ou `running`. Se não ficar, mostra o fim do log e para |
| `active(nome)` | A unidade está rodando |
| `remove(nome, imagem=)` | Para a unidade, apaga o arquivo e, se pedida, a imagem; apaga a rede quando nenhum outro container a usa |
| `once(imagem, args, input=)` | Roda um comando num container descartável e devolve a saída (segredos pela entrada padrão) |
| `build(imagem, Containerfile, args=)` | Monta uma imagem local (se ainda não existir), sem guardar camadas intermediárias |
| `exec(nome, args)` | Roda um comando num container em execução e devolve a saída (ex.: recarregar a configuração) |
| `remove_image(imagem)` | Apaga uma imagem, se existir |

O `Container` aceita `env_file`: um arquivo de variáveis (ex.: com um token, `600`), para segredos não ficarem no
arquivo da unidade.

- Unidade `<nome>.service`, com `Restart=always` e `WantedBy=default.target`. Logs: `journalctl --user -u <nome>`.
- Valores com espaço ou aspas vão entre aspas, e `%` e `$` são escapados, como o systemd espera. Quebra de linha é
  recusada.

## discord

Avisos dos apps no Discord do Astroverso (o bot é o app `discord`, nesta ou em outra máquina). A máquina fica ligada
ao bot por `~/.astroverso/discord.env` (`DISCORD_URL`, `DISCORD_KEY`, `600`), gravado pela instalação do app
`discord`.

| Nome | O que faz |
|---|---|
| `notify(app, nível, título, texto="", campos=None)` | Manda um aviso para o canal `#<app>`, no padrão do Astroverso. `nível`: `info`, `sucesso`, `aviso` ou `erro` (veja o README do app `discord`). Sem configuração, não faz nada; se o bot não responder, mostra um aviso e segue. Devolve se o aviso foi entregue |
| `configured()` | Se esta máquina está ligada ao bot |
| `settings()` / `save(url, chave)` / `forget()` | Lê, grava e apaga o `discord.env` |
| `whoami(url=, key=)` | O nome do cliente da chave (`GET /v1/eu`); levanta `DiscordError` se o bot recusar ou não responder |
| `request(método, caminho, dados=None)` | Chamada qualquer à API v1, com a chave desta máquina |

```python
from kit import discord

discord.notify("network", "erro", "AdGuard parado", "O DNS da casa está usando o secundário.")
```

## docs

Links para a documentação dos apps (os passos em plataformas de terceiros, em `apps/<app>/docs/`).

| Função | O que faz |
|---|---|
| `link(arquivo, âncora="")` | Endereço do arquivo no GitHub, montado na hora a partir do `origin` do clone e do branch atual (`https://github.com/<dono>/<repo>/blob/<branch>/<caminho>#<âncora>`). Sem `git`, sem `origin` no GitHub ou fora de um clone, devolve o caminho local. Fora de um branch, usa `main` |
| `slug(título)` | A âncora que o GitHub dá a um título (`Split DNS` → `split-dns`) |
| `anchors(arquivo)` | As âncoras de todos os títulos do arquivo, fora dos blocos de código (para os testes conferirem os links) |

O endereço do repositório nunca fica escrito no código: vem do clone.

## routes

Endereços que os apps publicam para o Caddy do `network` (o app não precisa saber se ele está instalado).

| Nome | O que faz |
|---|---|
| `Route(host, target)` | Um endereço: `host` (ex.: `nuvem.<domínio>`) e `target` (ex.: `http://astroverso-nuvem:80`, `http://host.containers.internal:9090`) |
| `publish(app, rotas)` | Grava `~/.astroverso/routes/<app>.json` de uma vez (rename atômico, com o temporário fora da pasta); não regrava se nada mudou |
| `withdraw(app)` | Apaga o arquivo do app (no `remove` dele) |
| `load()` | Todos os endereços publicados, com o app de origem; ignora arquivos inválidos com um aviso |

Com o `network` instalado, a unidade `astroverso-network-routes.path` vê a mudança e recarrega o Caddy.

## units

Unidades do systemd do usuário (`~/.config/systemd/user/`) que não são containers: timers, `.path`, serviços
oneshot.

| Função | O que faz |
|---|---|
| `install({nome: conteúdo}, start=[...])` | Grava as que mudaram, `daemon-reload`, liga (`enable --now`) as de `start` que estão paradas e reinicia as que mudaram |
| `remove(nomes)` | Desliga, apaga e faz `daemon-reload`; ignora as que não existem |
| `active(nome)` | Se a unidade está ativa |

## logo

Os pixels do símbolo (`SYMBOL`, convertido de `simbolo.png`: `#` lavanda, `o` arco em degradê do violeta ao
magenta) e a fonte do nome (`FONT`), desenhados pelo `ui.banner()` com meio-blocos (`▀▄█`).

## app

`Action(id, rótulo, função)`, o `Protocol` `App` e `REQUIRED`, os nomes obrigatórios do `app.py` (contrato em
`apps/README.md`).

## testing

`run_in_pty(função, teclas, lines=24, columns=100)` roda a função num pseudo-terminal (processo filho), envia as
teclas uma a uma e devolve `PtyRun(result, screen, code)`: o retorno da função (em JSON), a tela sem as cores e o
código de saída. É assim que menus e prompts de qualquer pacote ou app são testados.
