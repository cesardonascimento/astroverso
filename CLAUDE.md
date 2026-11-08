# CLAUDE.md

Regras para continuar o desenvolvimento do astro. O contexto da instalação atual (máquina, IPs,
domínio, contas) fica em `CLAUDE.local.md`, fora do git.

## Como trabalhar

- Responder sempre em **português do Brasil**, de forma direta.
- **Fazer commit e push depois de cada mudança**, sem perguntar. Mensagens em português, terminando com a linha
  `Co-Authored-By` da sessão.
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
setup.sh             assistente: descobre */project.sh e chama o contrato; não conhece os projetos
lib/ui.sh            logs com prefixo, prompts, ui_menu, ui_checklist (setas e Espaço)
lib/host.sh          host_base (compose, boot, ssh, tailscale), firewall, portas, IP e sub-rede
lib/env.sh           env_get CHAVE [padrão]
lib/proxy.sh         proxy_publish / proxy_unpublish (rotas do projeto no Caddy via .proxy)
<projeto>/project.sh describe | status | actions | action <id> | install | remove [--purge]
```

- Contrato e bibliotecas documentados em `lib/README.md`.
- Compose de todo projeto: `name: astro` + `x-podman: in_pod: false` (agrupados, mas independentes).
- Configuração por prompts, gravada em `<projeto>/.env` (permissão 600, fora do git). "Usar a configuração já salva?" reaproveita.
- Um projeto publica um endereço no Caddy com `proxy_publish` (escreve `<projeto>/.proxy` e recarrega o Caddy).
  Rotas manuais ficam em `caddy/.routes`; as de projeto têm prioridade sobre uma manual com o mesmo endereço.
- Versões fixadas: AdGuard na 1ª linha de `adguard/Dockerfile`; Caddy e `caddy-dns/cloudflare` em `caddy/Dockerfile`.

### Projetos

| Projeto | Resumo |
|---|---|
| adguard | Imagem customizada em **`network_mode: host`**. O entrypoint gera `AdGuardHome.yaml` do template se ele não existir e, a cada início, sincroniza porta do painel e IP do DNS com o `.env`. `.env` guarda só o **hash bcrypt** da senha. Reescritas `*.<domínio> → IP`. Configura o DNS da máquina, confere o Split DNS do Tailscale e publica o painel no Caddy (`PANEL_HOST`). |
| caddy | Let's Encrypt **curinga `*.<domínio>`** por DNS-01 na Cloudflare. O token precisa de **Zone:Read + DNS:Edit** na zona, sem expiração, e é validado na API ao instalar. Ações: listar, adicionar, remover e recarregar rotas. |
| cockpit | Pacotes do sistema (`cockpit`, `cockpit-podman`), não container. `cockpit.conf` em modo proxy; porta 9090 bloqueada para a rede no firewalld (rich rule). Rota `<nome-da-máquina>.<domínio> → http://host.containers.internal:9090`. |

## Armadilhas conhecidas

- O podman-compose interpola `${...}` em valores do `.env`, **mesmo entre aspas simples**. Por isso a senha vira hash antes de ir para o `.env`.
- Chamar uma função em contexto `cmd || funcao` desliga o `set -e` dentro dela. Usar `if ! cmd; then funcao; fi`.
- Portas publicadas no Podman rootless passam pelo `rootlessport`, um repassador em espaço de usuário: o serviço
  vê todos os clientes como `10.89.0.x`, e respostas **UDP** a quem chega pelo Tailscale saem com o endereço de
  origem errado (o cliente descarta). Serviços UDP que atendem a rede, como DNS, usam `network_mode: host`.
- Container → serviço do sistema: `host.containers.internal`, com o serviço escutando em `0.0.0.0`. O IP da
  máquina só funciona para portas publicadas por outros containers. Do lado do serviço, a conexão chega como local.
- Rootless + porta < 1024: `net.ipv4.ip_unprivileged_port_start` (`host_unprivileged_ports`, arquivo `99-astro.conf`).
- O `systemd-resolved` com o DNS secundário do roteador fica preso no roteador depois de o AdGuard reiniciar.
- Com `--accept-routes`, o Linux manda a rede local anunciada por outra máquina **pelo túnel**, mesmo estando nela
  (tabela 52, regra 5270). Solução: regra `priority 5260 lookup main suppress_prefixlength 0`
  (serviço `astro-tailscale-lan`, em `host_tailscale_lan_direct`), testada em namespace de rede isolado.
- O Tailscale tem regras próprias e **passa por fora do firewalld**. Rotas `~dominio` do Split DNS mandam as consultas para o servidor do Split DNS.
- `tailscale status --json` usa indentação de 2 espaços (a extração do bloco "Self" depende disso).
- O firewall do Fedora Workstation libera as portas TCP/UDP de 1025 a 65535 para a rede local.
- O Brave e o Chrome no Linux ignoram as CAs do sistema (usam o repositório NSS próprio).
- O repositório do Tailscale para RHEL e derivados é `rhel/<versão>`; para Fedora é `fedora`. No apt, derivados usam o `UBUNTU_CODENAME`.

## Pendências e ideias combinadas

- Segurança:
  - parar de publicar o painel do AdGuard na porta do host (acesso só pelo Caddy);
  - revisar as ACLs do Tailscale (hoje "todos acessam tudo" e a rede inteira está anunciada);
  - avaliar o modo paralelo do DoH (três provedores veem todas as consultas);
  - conferir no roteador se não há DMZ, UPnP ou redirecionamento de portas.
- Ação "verificar atualizações" para as versões fixadas.
- Ações de pós-configuração no adguard (ex.: gerenciar reescritas).
