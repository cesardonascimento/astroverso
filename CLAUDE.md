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
  nem neste arquivo. Eles vêm das perguntas da instalação (gravadas em `<projeto>/.env`) ou são detectados
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
- Nunca apagar `.env`, `.routes`, `.proxy` ou `data/` reais. Eles contêm segredos e não estão no git.
- `sudo` não funciona na sessão do Claude (sem TTY). `systemctl` e `pkexec` disparam uma janela gráfica do
  polkit para o usuário digitar a senha. Instalações que pedem `sudo` rodam em um terminal normal.
- Para testar menus e prompts, usar um pseudo-terminal em Python (`pty.fork`) enviando as teclas.
- Não pedir nem aceitar segredos (token da Cloudflare, senhas) no chat: eles entram pelo assistente.

## Arquitetura

```
setup.sh             assistente: atualiza o sistema (host_upgrade) e descobre */project.sh; não conhece os projetos
lib/ui.sh            logs com prefixo, prompts, ui_menu, ui_checklist (setas e Espaço)
lib/host.sh          host_base (sem suspensão, compose, boot, ssh, tailscale), firewall, portas, IP e sub-rede
lib/env.sh           env_get CHAVE [padrão]
lib/proxy.sh         proxy_publish / proxy_unpublish (rotas do projeto no Caddy via .proxy)
lib/disk.sh          disk_choose / disk_setup / disk_release (discos de dados no fstab e crypttab, TPM)
<projeto>/project.sh describe | status | actions | action <id> | install | remove [--purge]
```

- Contrato e bibliotecas documentados em `lib/README.md`.
- Compose de todo projeto: `name: astro` + `x-podman: in_pod: false` (agrupados, mas independentes).
- Estado da máquina (respostas que valem para todos os projetos, ex.: redirecionamento de porta confirmado) fica em
  `~/.config/astro/host.env`, fora do repositório.
- Configuração por prompts, gravada em `<projeto>/.env` (permissão 600, fora do git). "Usar a configuração já salva?" reaproveita.
  Toda resposta passa por um validador de `lib/env.sh` (`is_port`, `is_ipv4`, `is_hostname`...), porque vai parar
  em `.env`, YAML, `sed` ou Caddyfile.
- Segredos nunca em argumentos de comando (aparecem no `ps`): senha para o `htpasswd` e token para o `curl`
  vão pela entrada padrão.
- Um projeto publica um endereço no Caddy com `proxy_publish` (escreve `<projeto>/.proxy` e recarrega o Caddy).
  Rotas manuais ficam em `caddy/.routes`; as de projeto têm prioridade sobre uma manual com o mesmo endereço.
- Discos de dados: cada projeto escolhe os seus (`disk_choose`, UUIDs no `.env`) e os monta com `disk_setup` em
  `/srv/<rótulo>`. As linhas do projeto no `fstab`/`crypttab` vêm depois de `# astro:<projeto> <uuid>`, que também
  diz de quem é cada disco. **Nada pode pedir senha no boot** (a máquina é reiniciada de longe): LUKS só pelo TPM
  (PCR 7) com `headless=true`, e tudo com `nofail`.
- Versões fixadas: AdGuard na 1ª linha de `adguard/Dockerfile`; Caddy e `caddy-dns/cloudflare` em `caddy/Dockerfile`;
  Nextcloud, PostgreSQL e Valkey nas imagens de `nextcloud/docker-compose.yml`.

### Projetos

| Projeto | Resumo |
|---|---|
| adguard | Imagem customizada em **`network_mode: host`**. O entrypoint gera `AdGuardHome.yaml` do template se ele não existir. `.env` guarda só o **hash bcrypt** da senha. Reescritas `*.<domínio> → IP`. Configura o DNS da máquina, confere o Split DNS do Tailscale e publica o painel no Caddy (`PANEL_HOST`). |
| caddy | Let's Encrypt **curinga `*.<domínio>`** por DNS-01 na Cloudflare. O token precisa de **Zone:Read + DNS:Edit** na zona, sem expiração, e é validado na API ao instalar. Ações: listar, adicionar, remover e recarregar rotas. |
| cockpit | Pacotes do sistema (`cockpit`, `cockpit-podman`), não container. `cockpit.conf` em modo proxy; porta 9090 bloqueada para a rede no firewalld (rich rule). Rota `<nome-da-máquina>.<domínio> → http://host.containers.internal:9090`. |
| nextcloud | Imagem oficial `nextcloud:<versão>-apache` + PostgreSQL + Valkey + container de cron (mesma imagem, `/cron.sh`). Sem porta no host: o Caddy chega em `astro-nextcloud:80` pela `astro_default`. Senha do banco em `data/secrets` (lida pelos `*_FILE`; arquivo `644` em pasta `700`, porque o Postgres lê como o usuário `postgres`). A imagem instala com uma senha aleatória, trocada pela digitada com `occ user:resetpassword --password-from-env`. `trusted_proxies`, `overwriteprotocol`, fuso, região e cron aplicados pelo `occ` a cada instalação. Discos: dono `$USER` `770` (o `group::---` da ACL fecha o grupo) + ACL (também padrão) para o UID do `www-data` no host, `context=container_file_t` na montagem, `x-systemd.before=user@<uid>.service`; volumes em `docker-compose.override.yml` gerado e pasta no Nextcloud pelo `files_external` (`filesystem_check_changes 1`). `apache.conf` substitui o `000-default.conf` da imagem: `ServerName https://${NEXTCLOUD_HOST}:443` + `UseCanonicalName On` (redirecionamentos do `.well-known` em `https`) e HSTS. |
| sunshine | Pacote do sistema baixado da última release no GitHub (SHA-256 conferido), não container. Usuário de jogos sem `sudo`, com login automático no GDM, sem bloqueio de tela; o serviço de usuário sobe com a `graphical-session.target` dele. `setcap cap_sys_admin+p` para captura KMS. Instala o driver NVIDIA (RPM Fusion + chave MOK no Secure Boot), torna a NVIDIA a placa principal do GNOME (udev `mutter-device-preferred-primary`). O codificador não é fixado: o Sunshine testa (NVENC primeiro) a cada stream; a instalação só avisa se não houver tela na saída da NVIDIA. Padrão: tampa fechada e tela externa (TV ou plugue HDMI fantasma) no HDMI, que sai pela NVIDIA. `astro-sunshine-display` (Python + DBus do Mutter) no `global_prep_cmd` troca a tela, temporariamente, para a resolução exata do aparelho e volta no `undo`; nunca sai com erro. Alto-falantes internos mudos para o usuário de jogos (`pw-dump` + `wpctl`; o Fedora não traz `pactl`). Painel `47990` bloqueado na rede, rota `https+insecure://host.containers.internal:47990`. Discos de jogos: grupo `jogos` (usuário de jogos), `ntfs3` com `uid=$USER,gid=jogos,umask=007`, `x-gvfs-show`. |

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
  e o `status` do sunshine olha só o `custom.conf` do GDM, que é legível sem `sudo`.
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
  principal pode aparecer `777`. Um `chmod` fica gravado no disco e vale nas próximas montagens.
- `lsblk -J` só devolve a árvore (`children`) com `--tree` ou a coluna `NAME`.
- `$(...)` cujo último comando é `((n)) && ...` com `n=0` sai com 1 e, numa atribuição, derruba o `set -e`.
- `tailscale status --json` usa indentação de 2 espaços (a extração do bloco "Self" depende disso).
- O firewall do Fedora Workstation libera as portas TCP/UDP de 1025 a 65535 para a rede local.
- O Brave e o Chrome no Linux ignoram as CAs do sistema (usam o repositório NSS próprio).
- O repositório do Tailscale para RHEL e derivados é `rhel/<versão>`; para Fedora é `fedora`. No apt, derivados usam o `UBUNTU_CODENAME`.

## Pendências e ideias combinadas

- Segurança:
  - revisar as ACLs do Tailscale (hoje "todos acessam tudo" e a rede inteira está anunciada);
  - avaliar o modo paralelo do DoH (três provedores veem todas as consultas);
  - conferir no roteador se não há DMZ, UPnP ou redirecionamento de portas.
- Projeto de backup: `armazenamento-b` como espelho noturno do `armazenamento-a`; `armazenamento-c` a definir
  (`disk_setup` já serve). Até lá, a sessão do usuário de jogos ainda monta os dois pelo GNOME (com a senha do LUKS).
- Ação "verificar atualizações" para as versões fixadas.
- Ações de pós-configuração no adguard (ex.: gerenciar reescritas).
