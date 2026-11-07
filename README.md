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

## Uso

```bash
gh repo clone cesardonascimento/astro-adguard ~/Projects/astro-adguard
cd ~/Projects/astro-adguard
./adguard up      # cria ou recria o container
./adguard down    # remove o container (dados em ./data são mantidos)
```

O `up` executa, nesta ordem:

1. **`.env`**: se não existir, cria a partir do `.env.example` pedindo a senha do painel
2. **Host**: libera a porta 53 (sysctl + systemd-resolved), firewall, instala o
   podman-compose, habilita início no boot e conecta o Tailscale com `--accept-routes`.
   Cada etapa só roda se ainda não estiver feita, então o `sudo` só é pedido na 1ª vez
3. **Container**: build + recriação, aguarda o AdGuard responder e mostra os endereços

Rode em um terminal interativo (o `sudo` precisa pedir senha).

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

## Logs e status

```bash
podman compose logs -f
podman compose ps
```

## Estrutura

```
adguard                           script único: up / down
Dockerfile                        imagem customizada
docker-compose.yml                orquestração
config/AdGuardHome.yaml.template  config padrão (edite aqui para mudar o padrão)
scripts/docker-entrypoint.sh      gera a config na 1ª execução
data/                             dados em runtime (fora do git)
```

## Mudando a configuração

- **Pelo painel**: alterações ficam em `data/conf/AdGuardHome.yaml` (só nessa máquina).
- **Para todas as máquinas**: edite `config/AdGuardHome.yaml.template`, faça commit,
  e em cada máquina rode `./adguard up` com `ADGUARD_FORCE_CONFIG=true` uma vez (um `.bak` é mantido).

## Atualizando o AdGuard

Mude `ADGUARD_VERSION` na primeira linha do `Dockerfile`, depois `./adguard up`.
Se o `schema_version` mudar, o AdGuard migra a config sozinho.
