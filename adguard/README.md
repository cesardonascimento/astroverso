# adguard

AdGuard Home customizado. Instalado pelo `setup.sh` da raiz ou diretamente:

```bash
./project.sh install           # pergunta a configuração, prepara o host e sobe o container
./project.sh remove            # remove o container, mantém ./data
./project.sh remove --purge    # remove o container e apaga ./data
```

## O que vem customizado

| Item | Valor |
|---|---|
| Versão base | `adguard/adguardhome:v0.107.80` (fixada na 1ª linha do `Dockerfile`) |
| Assistente de instalação | Pulado: a config já vem pronta |
| Login do painel | Perguntado na instalação (senha guardada como hash bcrypt) |
| Upstreams | DoH Cloudflare, Quad9 e Google em modo **paralelo** |
| Cache | 32 MB, otimista, TTL mín. 60s |
| Segurança | DNSSEC + Safe Browsing ligados |
| Listas | AdGuard DNS, AdAway, OISD Big, HaGeZi PRO, HaGeZi TIF (StevenBlack incluída, desligada) |
| Logs | Consultas: 7 dias · Estatísticas: 30 dias |

## Perguntas da instalação

| Pergunta | Padrão |
|---|---|
| Usuário do painel | `admin` |
| Senha do painel | — |
| Porta do painel no host | `8080` |
| IP do host onde o DNS escuta | `0.0.0.0` (todos) |
| Fuso horário | o do host |
| Idioma do painel | `pt-br` |
| Adicionar reescritas DNS? | não |
| IP de destino das reescritas | o IP onde o DNS escuta (ou o IP da máquina na rede) |
| Domínios | um por vez, Enter vazio termina |
| Endereço do painel no Caddy | `adguard.<domínio do caddy>` (ou do primeiro domínio de reescrita) |

Cada domínio informado (`dominio.com` ou `*.dominio.com`) vira a reescrita `*.dominio.com → IP`,
que cobre todos os subdomínios mas não o domínio puro.

As respostas ficam em `.env`. Ao reinstalar, dá para reaproveitá-las. Se você responder de novo,
a config do AdGuard é regerada, e a anterior fica em `data/conf/AdGuardHome.yaml.bak`.

## Rede do host

O container usa `network_mode: host`, sem repassador de portas do Podman no meio. Com isso:

- as respostas UDP saem pelo endereço em que a consulta chegou. Com o repassador do Podman rootless
  (`rootlessport`), quem consultava pelo Tailscale recebia a resposta com o endereço de origem errado e
  a descartava;
- o registro de consultas mostra o IP real de cada aparelho.

A porta do painel e o IP do DNS ficam na própria configuração do AdGuard. O entrypoint sincroniza esses
dois valores com o `.env` a cada inicialização, o que também migra instalações antigas.

## Preparação do host

- Libera a porta 53 para Podman rootless e desativa o DNS stub do `systemd-resolved`
- Libera DNS e a porta do painel no firewalld
- Impede a máquina de suspender ou hibernar (alvos do systemd mascarados, tampa ignorada no `logind`,
  suspensão automática do GNOME desligada)
- Instala o podman-compose e o Tailscale (dnf ou apt) se faltarem, habilita a inicialização no boot e conecta o Tailscale com `--accept-routes`
- Ativa o servidor SSH; se houver chave em `~/.ssh/authorized_keys`, oferece desativar o login por senha
- Oferece anunciar a rede local (detectada automaticamente, ex: `<rede>/24`) no Tailscale para acesso remoto,
  ativando o encaminhamento de pacotes e o masquerade do firewalld; lembra de aprovar a rota no painel
- Pede o redirecionamento da porta UDP do Tailscale no roteador para esta máquina (conexões diretas de fora
  de casa, sem relay) e só continua após a confirmação, guardada em `~/.config/astro/host.env`

Depois que o container sobe:

- Oferece fazer esta máquina usar só o AdGuard como DNS (via NetworkManager), sem o DNS secundário
  do roteador. Sem isso, quando o AdGuard reinicia o sistema passa para o roteador e não volta,
  e os nomes das reescritas param de resolver
- Confere se o Split DNS do Tailscale desvia algum domínio das reescritas para outro servidor
  (ex: um AdGuard antigo). Se desviar, mostra o que trocar no painel do Tailscale e verifica de novo
- Publica o painel no Caddy (`.proxy`) no endereço respondido na instalação

## Mudando a configuração padrão

- **Pelo painel**: as alterações ficam em `data/conf/AdGuardHome.yaml` (só nessa máquina).
- **Para todas as máquinas**: edite `config/AdGuardHome.yaml.template`, faça commit e reinstale
  respondendo a configuração de novo.

## Logs

```bash
podman compose logs -f
```
