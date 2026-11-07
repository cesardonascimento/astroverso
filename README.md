# astro-adguard

AdGuard Home customizado rodando em container (Podman ou Docker), versionado
para subir idêntico em qualquer PC.

## O que vem customizado

| Item | Valor |
|---|---|
| Versão base | `adguard/adguardhome:v0.107.80` (fixada) |
| Assistente de instalação | Pulado — config já vem pronta |
| Login do painel | Definido no `.env` (senha guardada como hash bcrypt) |
| Upstreams | DoH Cloudflare, Quad9 e Google em modo **paralelo** |
| Cache | 32 MB, otimista, TTL mín. 60s |
| Segurança | DNSSEC + Safe Browsing ligados |
| Listas | AdGuard DNS, AdAway, OISD Big, HaGeZi PRO, HaGeZi TIF (StevenBlack incluída, desligada) |
| Logs | Consultas: 7 dias · Estatísticas: 30 dias |
| Idioma / fuso | pt-br / America/Sao_Paulo |

## Subindo em uma máquina nova

```bash
git clone <seu-repo> ~/Projects/astro-adguard
cd ~/Projects/astro-adguard
./scripts/setup-host.sh          # só na primeira vez em cada máquina (usa sudo)
cp .env.example .env             # edite a senha!
podman compose up -d --build
```

Painel: `http://<ip-da-maquina>:8080`

## Variáveis do `.env`

| Variável | Padrão | Função |
|---|---|---|
| `ADGUARD_USERNAME` | `admin` | Usuário do painel |
| `ADGUARD_PASSWORD` | — | Senha do painel (obrigatória na 1ª execução) |
| `ADGUARD_LANGUAGE` | `pt-br` | Idioma do painel |
| `TZ` | `America/Sao_Paulo` | Fuso horário |
| `ADGUARD_FORCE_CONFIG` | `false` | `true` regera a config do template a cada start (salva `.bak`) |
| `DNS_BIND_IP` | `0.0.0.0` | IP do host onde o DNS escuta |
| `WEB_PORT` | `8080` | Porta do painel no host |

Usuário, senha, idioma e fuso só são aplicados quando a config é gerada.

## Comandos do dia a dia

```bash
podman compose up -d --build     # sobe / atualiza
podman compose down              # para e remove o container (dados ficam em ./data)
podman compose logs -f           # logs
podman compose ps                # status + healthcheck
```

## Estrutura

```
Dockerfile                        imagem customizada
docker-compose.yml                orquestração
config/AdGuardHome.yaml.template  config padrão (edite aqui para mudar o padrão)
scripts/docker-entrypoint.sh      gera a config na 1ª execução
scripts/setup-host.sh             prepara o host (porta 53, firewall, compose, Tailscale)
data/                             dados em runtime (fora do git)
```

## Mudando a configuração

- **Pelo painel**: alterações ficam em `data/conf/AdGuardHome.yaml` (só nessa máquina).
- **Para todas as máquinas**: edite `config/AdGuardHome.yaml.template`, faça commit,
  e em cada máquina rode com `ADGUARD_FORCE_CONFIG=true` uma vez (um `.bak` é mantido).

## Atualizando o AdGuard

Mude `ADGUARD_VERSION` na primeira linha do `Dockerfile`, depois `podman compose up -d --build`.
Se o `schema_version` mudar, o AdGuard migra a config sozinho.
