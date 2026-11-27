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
| `checklist(título, itens, selected=, all_option=, cancel=, details=, danger=)` | Devolve os índices marcados, ou `None` se cancelado com Esc. Os itens de `danger` aparecem com `⚠` e em vermelho |

- **Validadores** recebem o texto e devolvem o valor normalizado, ou levantam `ValueError("motivo")`. O motivo
  aparece na tela.
- **Perguntas e menus** usam `/dev/tty`. Sem terminal, terminam com "sem terminal para perguntar". Depois da
  resposta, a pergunta vira uma linha com o valor escolhido (segredos aparecem como `••••••••`).
- **Teclas:** ↑/↓ (ou `k`/`j`), Home, End, PgUp, PgDn, 1 a 9 no menu, Espaço e `a` (todos) no checklist. Esc
  escolhe o último item do menu quando ele é "Voltar" ou "Sair", e o checklist com `cancel=True` devolve `None`. Nos
  outros casos (perguntas de texto, confirmações, menus e checklists sem volta), Esc levanta `ui.Cancelled` (filha
  de `KeyboardInterrupt`), e a pergunta vira "cancelado".
- **Texto** é lido tecla por tecla: acentos, Backspace, Ctrl+U (apaga a linha) e Enter; as setas são ignoradas.
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
| `output_raw(args, timeout=, env=, input=)` | Como o `output`, mas devolve os bytes (para conteúdo binário, como um e-mail) | Não falha |
| `output(args, timeout=, env=, input=)` | Nada: devolve `(código, saída)`, com a saída padrão e a de erro juntas | Não falha: código `127` (comando inexistente) ou `124` (tempo esgotado) |
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
| Firewall | `firewall_open(itens)`, `firewall_close(itens)` (portas `N/proto` ou serviços), `firewall_allowed(item)` (liberado, inclusive dentro de uma faixa; verdadeiro sem firewall), `firewall_masquerade(ligado)`. Ler também pede `sudo`: a política de servidor do firewalld exige administrador até para consultar |
| sysctl | `sysctl_set(nome, valores)` (`/etc/sysctl.d/99-astroverso-<nome>.conf`, aplicado na hora), `sysctl_remove(nome)` |
| Arquivos do sistema | `file_put(caminho, conteúdo, mode=)` (com `sudo`, só se mudou; devolve se mudou; `mode` acerta a permissão), `file_drop(caminho)` |
| systemd | `units_mask(nomes)`, `units_unmask(nomes)`, `units_masked(nomes)`; `unit_install(nome, conteúdo)` (em `/etc/systemd/system`, liga e reinicia), `unit_remove(nome)`, `unit_enabled(nome)`; `daemon_reload()`; `reload_service(nome)` (`reload`, ou `HUP`) |
| Atualizações automáticas | `auto_updates_on()` / `auto_updates_off()` / `auto_updates_active()` (Fedora: `dnf5-plugin-automatic`, `/etc/dnf/automatic.conf` com `apply_updates = yes` e `reboot = never`, `dnf5-automatic.timer`), `auto_updates_last()` (resultado e início da última rodada), `reboot_pending()` (`dnf needs-restarting`, sem rede) |
| Nome da máquina | `hostname_set(nome)` (Fedora: `hostnamectl set-hostname`); para ler, `kit.net.hostname()` |
| Firewall por origem | `firewall_limit(serviço, origens)` (regras ricas só das origens, e tira o serviço aberto para todos; as regras entram antes), `firewall_unlimit(serviço, origens)`, `firewall_limited(serviço, origens)` |

- Tudo é idempotente: só age, e só mostra um ✔, quando algo muda.
- Fedora: `dnf -q`; o arquivo do repositório é baixado pelo Python e gravado em `/etc/yum.repos.d/<nome>.repo`.
- Firewall só com o `firewalld` ativo (conferido pelo `systemctl`: o `firewall-cmd --state` pede o polkit). As
  consultas usam a configuração em uso (sem `sudo`); as mudanças vão para a permanente, com `--reload`. Abrir e
  fechar comparam o item exato da lista: uma porta dentro de uma faixa liberada é aberta à parte, e fechar nunca
  parte uma faixa.
- `sysctl_remove` apaga o arquivo e reaplica os outros; o valor em uso só volta ao padrão por completo depois de
  reiniciar.

## disks

Os discos de dados da máquina, montados pelo app `disks` em `/srv/<nome>`. Só leitura: a fonte é o próprio
`/etc/fstab` (as linhas depois de `# astroverso <uuid>`, reconhecidas também quando o udisks as separa da marca), não
a pasta de um app.

| Função | O que faz |
|---|---|
| `mounts()` | Os discos cadastrados: `Disk(uuid, path, fstype, line)`, com `name` (o nome da pasta) |
| `mounted(caminho)` | Se há algo montado nesse caminho (`findmnt`) |
| `responds(caminho)` | Montado, com o aparelho por baixo presente e a pasta lida em até 20 s (pega o disco preso depois de uma queda da conexão) |
| `containing(caminho)` / `available(caminho)` | O disco onde fica uma pasta; se ela está num disco que responde (verdadeiro fora dos discos) |
| `usage(caminho)` | `(usado, total)` em bytes |

## clouds

As pastas ligadas a uma nuvem, publicadas pelo app que sincroniza (`~/.astroverso/clouds/<app>.json`, pasta de nenhum
app, como os endereços do `kit.routes`). Só servem para mostrar a marca ☁ nos seletores: nenhum app decide nada por
elas.

| Função | O que faz |
|---|---|
| `publish(app, [Linked(caminho, rótulo)])` / `withdraw(app)` | Publica (ou retira) as pastas ligadas do app |
| `load()` | Todas as pastas publicadas |
| `mark(caminho)` | O rótulo da pasta ligada que contém esse caminho, ou `""` |

## folders

`pick(pergunta, atual=, validate=)` é o seletor de pastas de todos os apps: um menu com a pasta atual, os discos do
`kit.disks`, as pastas do `kit.clouds` e o home, cada uma com o disco, o espaço livre e a marca ☁ (`describe`), mais
"Digitar outra pasta…". Depois, Enter confirma a pasta, um nome vira uma subpasta dela e um caminho completo a troca.

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
- `config.timezone()` e `config.region()`: o fuso da máquina (de `/etc/localtime`, `UTC` sem ele) e o país dele
  (`zone.tab`), para os apps que precisam.
- `lan_network()`: a rede do `lan_ip()` (ex.: `<rede>/24`), pelo `ip -j addr`.

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

Outros campos do `Container`: `ports`, `environment`, `command`, `env_file`, `requires` (outros containers que
sobem antes: `Requires` e `After` do systemd), `entrypoint`, `health_start` (tempo de partida do teste de saúde,
padrão `30s`), `stop_signal` (ex.: `SIGTERM` quando a imagem pede um sinal que o processo não atende) e `read_only`
(`ReadOnly=true`: só os volumes aceitam escrita, e o `/tmp` fica em memória). O volume
leva `Z` por padrão (só daquele container); use `z` para uma pasta montada em mais de um container.

| Função | O que faz |
|---|---|
| `prepare()` | Instala o Podman e liga o *linger* (os containers sobem no boot sem ninguém logado) |
| `restart(spec)` | Reinicia o container e espera ficar pronto (ex.: quando o `env_file` mudou) |
| `exec_raw(nome, args, user=)` | Comando no container devolvendo `(código, bytes)` |
| `exec(nome, args, user=, input=)` / `exec_output(nome, args, user=, env=, input=)` | Comando dentro do container; o `exec_output` não falha (devolve código e saída) e repassa variáveis pelo ambiente (`-eNOME`), sem o valor nos argumentos |
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
| `notify(app, nível, título, texto="", campos=None, actions=())` | Manda um aviso para o canal `#<app>`, no padrão do Astroverso. `nível`: `info`, `sucesso`, `aviso` ou `erro` (veja o README do app `discord`). Sem configuração, não faz nada; se o bot não responder, mostra um aviso e segue. `actions`: botões `(rótulo, "<app>:<ação>")` que rodam ações remotas. Devolve se o aviso foi entregue |
| `configured()` | Se esta máquina está ligada ao bot |
| `settings()` / `save(url, chave)` / `forget()` | Lê, grava e apaga o `discord.env` |
| `whoami(url=, key=)` | O nome do cliente da chave (`GET /v1/eu`); levanta `DiscordError` se o bot recusar ou não responder |
| `request(método, caminho, dados=None)` | Chamada qualquer à API v1, com a chave desta máquina |

```python
from kit import discord

discord.notify("network", "erro", "AdGuard parado", "O DNS da casa está usando o secundário.")
```

## changes

As mudanças que um app faz no sistema, uma a uma (regra de todo app: veja `apps/README.md`).

| Nome | O que faz |
|---|---|
| `Change(id, rótulo, por_quê, applied, apply, undo, danger=False)` | Uma mudança. O rótulo é uma ação ("Ignorar a tampa fechada"), o porquê aparece antes da pergunta, `applied()` confere no sistema, `apply()`/`undo()` fazem e desfazem. `danger`: importante para o funcionamento do app |
| `install(app, mudanças, reuse)` | Pergunta cada uma (padrão sim, ou a resposta salva), grava `CHANGE_<ID>=yes/no` no `.env` do app e aplica ou desfaz. Com `reuse`, usa as respostas salvas sem perguntar |
| `manage(app, mudanças)` | O painel: checklist com as aplicadas marcadas e as `danger` em vermelho; desfazer uma `danger` pede confirmação |
| `undo_all(mudanças)` | Desfaz todas, na ordem inversa (no `remove`) |
| `rows(mudanças)` | Linhas de tabela (mudança, aplicada ou desfeita) para o resumo |

## backup

O backup de cada app no servidor do app `backup` (restic por HTTPS). A máquina fica ligada ao servidor por
`~/.astroverso/backup.env` (`BACKUP_URL`, `BACKUP_USER`, `BACKUP_PASSWORD`, `BACKUP_REPO_PASSWORD`, `600`) e
`~/.astroverso/backup-destinations.json` (as pastas de destino do servidor: `Destination(id, path, cloud)`). Cada
pasta de destino é um repositório: `rest:<url>/<máquina>/<id>/`. **Quem escolhe as pastas é o app**, guardadas no
`.env` dele (`BACKUP_TO` para a configuração; outra chave para cada parte dos dados).

| Nome | O que faz |
|---|---|
| `change(app)` | A mudança perguntada do backup diário: ao ligar, pergunta as pastas de destino (`choose`) e instala o timer `astroverso-<app>-backup` às 01:MM (o minuto vem do nome do app), `Persistent`, que roda `astroverso <app> action backup-now`. Desfazer tira o timer e esquece as pastas |
| `data_change(app, parte, rótulo, porquê, ação, chave, o_quê)` | Igual, para dados: timer `astroverso-<app>-backup-<parte>` às 02:MM, que roda a ação dada; com `chave=None`, o app guarda as pastas de cada item do jeito dele |
| `run_backup(app, backup, label="", notify=True)` | Chama `backup(pasta)` do app numa pasta temporária, manda pelo `restic backup` para cada pasta escolhida (marcas `astroverso`, `app:<app>` e o rótulo), apaga a pasta e avisa no `#backup` (falha com o botão "Tentar de novo"). Sem servidor, só avisa; sem pasta escolhida ou com pasta que saiu do servidor, avisa o erro |
| `run_data(app, nome, caminho, pastas, ação, unshare=, missing=, exclude=)` | Manda uma pasta de dados direto (marca `dados:<nome>`), com `podman unshare` para os arquivos de containers; `missing` são as pastas escolhidas que saíram do servidor (avisadas como erro). Pasta num disco desligado ou travado (`kit.disks.available`): não guarda nada e avisa |
| `restore(app, backup, restore)` | Escolhe a pasta de destino e a versão, guarda antes uma versão "antes-da-restauracao", traz a pasta daquela versão e chama `restore(pasta)` do app |
| `opened(app)` | Contexto: escolhe a pasta de destino e a versão da configuração e entrega `(pasta, data)` com o conteúdo daquela versão (ou `None` se voltar), apagada no fim. Para restaurar só uma parte (ex.: uma rotina do n8n) |
| `restore_data(app, nome)` | Traz uma versão dos dados numa pasta nova e vazia (padrão `~/Restaurado/<app>-<nome>-<data>`), sem mexer na original |
| `targets(app, chave)` / `choose(app, chave, o_quê)` / `pick(pergunta, atuais)` | As pastas escolhidas por um app e a pergunta "Onde guardar as fotografias …?" (checklist com a marca ☁), depois de explicar que o backup é uma fotografia por dia, com versões, e não um espelho |
| `versions(app, pasta, dados="")` / `summary(app, dados=)` | As versões do app nesta máquina numa pasta (as de configuração, ou as de uma parte dos dados) e a tabela para o resumo |
| `link_code(url, usuário, pastas)` / `read_code(texto)` | O código de ligação mostrado pelo servidor e colado no cliente (sem segredos) |
| `configured()` / `settings()` / `save(...)` / `destinations()` / `save_destinations(...)` / `forget()` / `ensure_repository(valores, pasta)` | A ligação com o servidor; o `ensure_repository` cria o repositório na primeira vez e traduz os erros comuns |

As senhas vão por variável de ambiente (`RESTIC_REST_PASSWORD`, `RESTIC_PASSWORD`), nunca em argumentos.

## mail

Envio de e-mails pelos apps, pelo Worker do app `mail` (nesta ou em outra máquina). A máquina fica ligada ao envio
por `~/.astroverso/mail.env` (`MAIL_URL`, `MAIL_KEY`, `600`).

| Nome | O que faz |
|---|---|
| `send(para, assunto, texto="", html="", attachments=())` | Envia e devolve quem recebeu. `para`: um endereço ou uma lista; `attachments`: `Attachment(nome, tipo, dados, cid="")` (com `cid`, vai embutido no HTML). Sem configuração, não faz nada; falha ou destinatário não confirmado viram aviso na tela |
| `configured()` / `settings()` / `save(url, chave)` / `forget()` | Lê, grava e apaga o `mail.env` |
| `check(url=, key=)` | Confere o endereço e a chave (`GET /conferir`); levanta `MailError` |

## mailboxes

O contrato das caixas de e-mail entre apps, no padrão do `kit.routes`: o app `mail` publica, o Nextcloud cria as
contas no Mail.

| Nome | O que faz |
|---|---|
| `Mailbox(nome, endereço, servidor, porta, usuário, arquivo_da_senha, smtp_port=0)` | Uma caixa IMAP; `password()` lê a senha do arquivo (`600`, do app dono), que nunca vai para o JSON |
| `publish(app, caixas)` / `withdraw(app)` / `load()` | Grava `~/.astroverso/mailboxes/<app>.json` (`600`, de uma vez), apaga e lê todas, com o app de origem |

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
| `restart(nome)` | Reinicia a unidade (ex.: um serviço de longa duração depois de atualizar o código) |
| `active(nome)` | Se a unidade está ativa |

## watch

A verificação de hora em hora dos apps, com avisos no Discord só quando algo muda.

| Nome | O que faz |
|---|---|
| `Problem(nível, título, texto="", kind="")` | Um problema encontrado; `kind` agrupa títulos que mudam (ex.: "Cadeado vence em N dias"), para não repetir o aviso a cada dia |
| `run(app, collect, botões, saudável)` | Chama `collect(estado_anterior)` → `{chave: Problem}` e avisa o que apareceu, mudou de nível ou de tipo, e o que se resolveu (✅). Aviso não entregue é tentado na próxima. Estado em `~/.astroverso/<app>/watch.json` |
| `change(app, rótulo, porquê, o_quê)` | A `Change` do timer `astroverso-<app>-watch` (de hora em hora, a primeira 10 min depois de ligar), que roda `astroverso <app> action watch` |
| `carry(estado, chave)` | Mantém um problema que não deu para conferir agora |
| `summary(app)` | A tabela da verificação no resumo do app |

## logo

Os pixels do símbolo (`SYMBOL`, convertido de `simbolo.png`: `#` lavanda, `o` arco em degradê do violeta ao
magenta) e a fonte do nome (`FONT`), desenhados pelo `ui.banner()` com meio-blocos (`▀▄█`).

## app

`Action(id, rótulo, função, remote=False, confirm=False, menu=True)`, o `Protocol` `App` e `REQUIRED`, os nomes obrigatórios do `app.py` (contrato em
`apps/README.md`).

## testing

`run_in_pty(função, teclas, lines=24, columns=100)` roda a função num pseudo-terminal (processo filho), envia as
teclas uma a uma e devolve `PtyRun(result, screen, code)`: o retorno da função (em JSON), a tela sem as cores e o
código de saída. É assim que menus e prompts de qualquer pacote ou app são testados.
