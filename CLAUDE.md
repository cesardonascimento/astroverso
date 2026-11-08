# CLAUDE.md

Contexto para continuar o desenvolvimento do astro, o homelab do Cesar.

## Como trabalhar com o Cesar

- Responder sempre em **português do Brasil**, de forma direta.
- **Fazer commit e push depois de cada mudança**, sem perguntar. Mensagens em português, terminando com a linha
  `Co-Authored-By` da sessão.
- **Sem comentários no código.** Mensagens de log, sim, bem formatadas.
- Toda mensagem na tela usa o prefixo do projeto (`[astro]`, `[adguard]`, `[caddy]`...), inclusive prompts,
  o prompt do `sudo` e os logs de dentro dos containers. Usar as funções de `lib/ui.sh`, nunca `echo` solto.
- Preferir o caminho simples e remover etapas desnecessárias. Ele pede revisões nesse sentido.
- **Tudo funciona pela rede local** (`192.168.3.43`), mesmo com o Tailscale conectado. Não sugerir o IP do
  Tailscale como caminho de acesso.
- `README.md` da raiz é **enxuto**, um passo a passo. Detalhes técnicos vão nos READMEs dos projetos e em `lib/README.md`.
- Quando algo pertence ao script (ex.: uma verificação manual que ele não quer esquecer), colocar no
  assistente como etapa, com aviso e instruções.

## Regras de segurança ao testar (aprendidas na prática)

- **Nunca testar na pasta real nem no container real.** Copiar para o scratchpad e trocar `name:` do compose,
  `container_name`, imagem, portas (`15353`, `18080`, `18081`, `18443`) e a constante `CONTAINER` do `project.sh`.
  Um teste antigo recriou o container real e apagou o `adguard/.env` do Cesar.
- Nunca apagar `.env`, `.routes`, `.proxy` ou `data/` reais. Eles contêm segredos e não estão no git.
- `sudo` não funciona nesta sessão (sem TTY). `systemctl` e `pkexec` disparam uma janela gráfica do polkit
  em que o Cesar digita a senha. Instalações que pedem `sudo` ele roda em um terminal normal.
- Para testar menus e prompts, usar um pseudo-terminal em Python (`pty.fork`) enviando as teclas. O `script`
  não está instalado.
- Não pedir nem aceitar segredos (token da Cloudflare, senhas) no chat: eles entram pelo assistente.

## Ambiente

| Item | Valor |
|---|---|
| Máquina | **rigel**, notebook Redmi G, Fedora 44, usuário `astro`, Podman rootless 5.x, Homebrew disponível |
| Rede | cabo `enp8s0`, IP **192.168.3.43** (reserva DHCP pelo MAC `7c:d3:0a:92:f0:46`), gateway `192.168.3.1` (roteador Huawei) |
| Tailscale | tailnet `cesardonascimento.com` (`tail6099ad.ts.net`); rigel = `100.102.185.113`, `--operator=astro`, `--accept-routes`, anuncia `192.168.3.0/24` (aprovado). Outras: aldebaran (antigo AdGuard, sendo desativado), sirius, antares (iOS) |
| Split DNS (painel Tailscale) | `cesardonascimento.com → 192.168.3.43` |
| Domínio | `cesardonascimento.com`, registrado na Hostinger, **DNS na Cloudflare** (`carmelo`/`surina.ns.cloudflare.com`), todos os registros "DNS only". Site na Hostinger (`2.57.91.91`), e-mail no Proton (MX, SPF, DKIM e DMARC) |
| DNS desta máquina | só o AdGuard (`ipv4.ignore-auto-dns` no NetworkManager) |
| GitHub | `cesardonascimento/astro` (privado), `gh` logado, git como "Cesar do Nascimento <git@cesardonascimento.com>" |

## Arquitetura

```
setup.sh             assistente: descobre */project.sh e chama o contrato; não conhece os projetos
lib/ui.sh            logs com prefixo, prompts, ui_menu, ui_checklist (setas e Espaço)
lib/host.sh          host_base (compose, boot, ssh, tailscale), firewall, portas, IP e sub-rede
lib/env.sh           env_get CHAVE [padrão]
<projeto>/project.sh describe | status | actions | action <id> | install | remove [--purge]
```

- Contrato e bibliotecas documentados em `lib/README.md`.
- Compose de todo projeto: `name: astro` + `x-podman: in_pod: false` (agrupados, mas independentes).
- Configuração por prompts, gravada em `<projeto>/.env` (permissão 600, fora do git). "Usar a configuração já salva?" reaproveita.
- Um projeto publica um endereço no Caddy escrevendo `<projeto>/.proxy` (`host destino`) e chamando
  `../caddy/project.sh action reload`. Rotas manuais ficam em `caddy/.routes`.
- Versões fixadas: AdGuard `v0.107.80` (1ª linha de `adguard/Dockerfile`); Caddy `2.11.9` + `caddy-dns/cloudflare v0.2.4` (`caddy/Dockerfile`).

### Projetos

| Projeto | Resumo |
|---|---|
| adguard | Imagem customizada; o entrypoint gera `AdGuardHome.yaml` do template se ele não existir. `.env` guarda só o **hash bcrypt** da senha. Reescritas `*.dominio → IP`. Configura o DNS desta máquina e confere o Split DNS do Tailscale. Painel publicado em `:8080`. |
| caddy | Let's Encrypt **curinga `*.cesardonascimento.com`** por DNS-01 na Cloudflare. O token precisa de **Zone:Read + DNS:Edit** na zona, sem expiração, e é validado na API ao instalar. Ações: listar, adicionar, remover e recarregar rotas. |
| cockpit | Pacotes do sistema (`cockpit`, `cockpit-podman`), não container. `cockpit.conf` em modo proxy; porta 9090 bloqueada para a rede no firewalld (rich rule). Rota `rigel.cesardonascimento.com → http://host.containers.internal:9090`. |

## Armadilhas conhecidas

- O podman-compose interpola `${...}` em valores do `.env`, **mesmo entre aspas simples**. Por isso a senha vira hash antes de ir para o `.env`.
- Chamar uma função em contexto `cmd || funcao` desliga o `set -e` dentro dela. Usar `if ! cmd; then funcao; fi`.
- Container → serviço do sistema: `host.containers.internal`, com o serviço escutando em `0.0.0.0`. O IP da rigel
  só funciona para portas publicadas por outros containers. Do lado do serviço, a conexão chega como local.
- Rootless + porta < 1024: `net.ipv4.ip_unprivileged_port_start` (`host_unprivileged_ports`, arquivo `99-astro.conf`).
- O `systemd-resolved` com o DNS secundário do roteador fica preso no roteador depois de o AdGuard reiniciar.
- O Tailscale tem regras próprias e **passa por fora do firewalld**. Rotas `~dominio` do Split DNS mandam as consultas para o servidor do Split DNS.
- `tailscale status --json` usa indentação de 2 espaços (a extração do bloco "Self" depende disso).
- O firewall do Fedora Workstation libera as portas TCP/UDP de 1025 a 65535 para a rede local.
- O Brave e o Chrome no Linux ignoram as CAs do sistema (usam o repositório NSS próprio).
- O provedor de internet bloqueia `9.9.9.9` (os erros de bootstrap do Quad9 no log do AdGuard são normais) e a porta 25 de saída.
- O repositório do Tailscale para RHEL e derivados é `rhel/<versão>`; para Fedora é `fedora`. No apt, derivados usam o `UBUNTU_CODENAME`.

## Pendências e ideias combinadas

- Segurança:
  - parar de publicar o painel do AdGuard em `:8080` (acesso só pelo Caddy);
  - revisar as ACLs do Tailscale (hoje "todos acessam tudo" e a rede inteira está anunciada);
  - avaliar o modo paralelo do DoH (três provedores veem todas as consultas);
  - conferir no roteador se não há DMZ, UPnP ou redirecionamento de portas.
- Ação "verificar atualizações" para as versões fixadas.
- Ações de pós-configuração no adguard (ex.: gerenciar reescritas).
- O certificado HTTPS do site na Hostinger venceu em julho de 2025 (problema anterior, fora do astro).
- Firmware pendente: KEK CA 2011 → 2023 do Secure Boot (`fwupdmgr update`, decisão do Cesar).
- O Cesar vai desativar o AdGuard da aldebaran.
