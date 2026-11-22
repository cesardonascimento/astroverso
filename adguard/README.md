# adguard

AdGuard Home customizado. Instalado pelo `setup.sh` da raiz ou diretamente:

```bash
./project.sh install           # pergunta a configuração, prepara o host e sobe o container
./project.sh remove           # desfaz tudo o que o projeto criou (usado pelo Implodir Astroverso)
```

## O que vem customizado

| Item | Valor |
|---|---|
| Versão base | `adguard/adguardhome:v0.107.80` (fixada na 1ª linha do `Dockerfile`) |
| Assistente de instalação | Pulado: a config já vem pronta |
| Login do painel | Perguntado na instalação (senha guardada como hash bcrypt) |
| Upstreams | DoH Cloudflare; DoH Google só se o Cloudflare falhar (`fallback_dns`). Bootstrap `1.1.1.1`, `1.0.0.1` e `8.8.8.8` |
| Cache | 32 MB, otimista, TTL mín. 60s |
| Segurança | DNSSEC + Safe Browsing ligados |
| Listas | AdGuard DNS, AdAway, OISD Big, HaGeZi PRO, HaGeZi TIF, HaGeZi Apple, Windows/Office e Xiaomi (rastreadores), HaGeZi DNS Rebind Protection, HaGeZi NSFW (StevenBlack incluída, desligada) |
| Logs | Consultas: 7 dias · Estatísticas: 30 dias |

## Perguntas da instalação

| Pergunta | Padrão |
|---|---|
| Usuário do painel | `astroverso` |
| Senha do painel | — |
| Porta do painel no host | `8080` |
| IP do host onde o DNS escuta | `0.0.0.0` (todos) |
| Fuso horário | o do host |
| Idioma do painel | `pt-br` |
| Responder *.<domínio do caddy> com o IP desta máquina? | sim (só com o Caddy configurado) |
| Adicionar outros domínios? | não (sem o Caddy: "Adicionar domínios de reescrita?") |
| Domínios | um por vez, sem o `*.`; Enter vazio termina |
| IP de destino das reescritas | o IP onde o DNS escuta (ou o IP da máquina na rede) |
| Endereço do painel no Caddy | `adguard.<domínio do caddy>` (ou do primeiro domínio de reescrita) |

Cada domínio informado (`dominio.com` ou `*.dominio.com`) vira a reescrita `*.dominio.com → IP`,
que cobre todos os subdomínios mas não o domínio puro.

As respostas ficam em `~/.astroverso/adguard/.env`. Ao reinstalar, dá para reaproveitá-las. Se você responder de novo,
a config do AdGuard é regerada, e a anterior fica em `~/.astroverso/adguard/data/conf/AdGuardHome.yaml.bak`.

## Rede do host

O container usa `network_mode: host`, sem repassador de portas do Podman no meio. Com isso:

- as respostas UDP saem pelo endereço em que a consulta chegou. Com o repassador do Podman rootless
  (`rootlessport`), quem consultava pelo Tailscale recebia a resposta com o endereço de origem errado e
  a descartava;
- o registro de consultas mostra o IP real de cada aparelho.

A porta do painel e o IP do DNS ficam na própria configuração do AdGuard, gerada a partir do `.env` na
primeira execução ou quando a configuração é respondida de novo.

## Preparação do host

- Libera a porta 53 para Podman rootless e desativa o DNS stub do `systemd-resolved`
- Libera o DNS no firewalld. Com o painel publicado no Caddy, a porta do painel é bloqueada para a rede
  (acesso só por HTTPS); sem o Caddy, ela é liberada

Depois que o container sobe:

- Pergunta se esta máquina deve usar só o AdGuard como DNS (via NetworkManager), ignorando o secundário
  do roteador (padrão: não). Só o AdGuard garante os nomes internos na própria máquina, mas a deixa sem
  DNS quando ele está parado; com o secundário ela nunca fica sem DNS
- Mantendo o secundário, instala a verificação do DNS primário: `astroverso-dns-check.service`, disparado pelo
  NetworkManager a cada conexão (`/etc/NetworkManager/dispatcher.d/90-astroverso-dns-check`). Ela renova a
  conexão até 3 vezes se o primeiro DNS entregue pelo roteador não for o AdGuard, espera o AdGuard responder
  (até 5 min) e reinicia o `systemd-resolved` se ele estiver usando o secundário. Log: `journalctl -t adguard`.
  Removida ao escolher "só o AdGuard" ou ao remover o projeto
- Confere se o Split DNS do Tailscale desvia algum domínio das reescritas para outro servidor
  (ex: um AdGuard antigo). Se desviar, mostra o que trocar no painel do Tailscale e verifica de novo
- Publica o painel no Caddy (`.proxy`) no endereço respondido na instalação

## Mudando a configuração padrão

- **Pelo painel**: as alterações ficam em `~/.astroverso/adguard/data/conf/AdGuardHome.yaml` (entram no backup das
  configurações; a pasta `data/work`, com estatísticas e cache, fica de fora).
- **Para todas as máquinas**: edite `config/AdGuardHome.yaml.template`, faça commit e reinstale
  respondendo a configuração de novo.

## Logs

```bash
podman compose logs -f
```

## Troca de domínio

`project.sh domain <antigo> <novo>` (chamado pelo "Trocar o domínio" do assistente) troca a reescrita
`*.<antigo>` por `*.<novo>` no `AdGuardHome.yaml` (o resto da configuração do painel fica), sobe o container de
novo, exige o Split DNS do Tailscale para o domínio novo apontando para esta máquina (com instruções e nova
verificação) e republica o painel no Caddy.

## Remoção

`remove` volta o DNS desta máquina para o automático (se ele estava em "só o AdGuard"), reativa o DNS stub do
`systemd-resolved`, tira a verificação do DNS primário, o container, as imagens, as liberações e o bloqueio da
porta no firewall e a rota do Caddy, e apaga `~/.astroverso/adguard`.
