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
| Firewall | `firewall_open(itens)`, `firewall_close(itens)` (portas `N/proto` ou serviços), `firewall_masquerade(ligado)` |
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
| `reuse(app)` | "Usar a configuração já salva?" (falso sem perguntar, se não houver `.env`) |
| `domain()` | O domínio dos endereços, em `~/.astroverso/astroverso.env` (`DOMAIN`), perguntado e guardado na primeira vez |
| `purge(app)` | Apaga a pasta do app (com `podman unshare` se houver arquivos de containers). Só aceita um nome de app válido, nunca atalhos nem a pasta inteira |

## validate

Validadores para `ui.ask`: devolvem o valor normalizado ou levantam `ValueError` com o motivo.
`domain` (minúsculo; tira `http://`, `*.` e o ponto ou barra do fim), `ipv4`, `port`, `name` (minúsculo, letras,
números e hífen, até 63) e `email`. Toda resposta que vai para um `.env` ou um arquivo de configuração passa por
um deles.

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
