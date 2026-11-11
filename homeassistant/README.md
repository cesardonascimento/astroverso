# homeassistant

Automação da casa: junta num painel só os aparelhos de várias marcas e permite criar
rotinas entre eles. Acessível em `https://homeassistant.<domínio>` pelo Caddy.

```bash
./project.sh install           # instala, configura o proxy e publica o painel no Caddy
./project.sh remove           # desfaz tudo o que o projeto criou (usado pelo Implodir Astro)
```

É o **Home Assistant Container**, a imagem oficial `ghcr.io/home-assistant/home-assistant` com a versão fixada no
`docker-compose.yml`. Não tem a loja de complementos (add-ons), que só existe no Home Assistant OS: o que for
preciso (Mosquitto, Zigbee2MQTT, ESPHome...) entra como outro container deste projeto.

## Perguntas da instalação

| Pergunta | Padrão |
|---|---|
| Endereço do Home Assistant no Caddy | `homeassistant.<domínio do caddy>` |
| Porta do Home Assistant no host | `8123` |
| Nome da casa no Home Assistant | `Astro` |
| Usuário administrador do Home Assistant | `astro` |
| Senha do usuário | (secreta; só na primeira instalação, sem gravar em lugar nenhum) |

O fuso vem da máquina (`timedatectl`).

## Configuração inicial automática

Se o Home Assistant ainda não tiver usuário (`/api/onboarding`), a instalação faz a configuração inicial pela API
local (`http://127.0.0.1:<porta>`): cria o administrador (`/api/onboarding/users`, senha pela entrada padrão),
conclui as etapas `core_config`, `analytics` e `integration` e revoga o token usado. Depois, com o container parado,
grava em `.storage/core.config` (criado completo se ainda não existir) o nome da casa, o fuso, o país (da tabela
de fusos), o idioma e a moeda (de um locale do país instalado no sistema, ex.: `pt_BR`), as coordenadas aproximadas
da cidade do fuso e o sistema métrico (exceto nos EUA). A localização exata se ajusta em Configurações → Sistema →
Geral.

A cada instalação, grava também `internal_url` e `external_url` como `https://<endereço no Caddy>`: é o endereço
que o Home Assistant anuncia na rede, e o app do celular o encontra sozinho (a porta local é bloqueada para a rede).

## O que a instalação faz

- Sobe o container `astro-homeassistant` em **`network_mode: host`**: a descoberta de aparelhos (mDNS, SSDP,
  DHCP) depende de broadcast e multicast na rede da casa, que não passam pela rede do Podman.
- Monta `~/.astro/homeassistant/config` em `/config` (`configuration.yaml`, banco, integrações e usuários).
- Configura o proxy em **`.storage/http`** (com o container parado): porta, `use_x_forwarded_for` e
  `trusted_proxies` (o host, a rede `astro_default`, criada aqui se ainda não existir, e o IP da máquina). O Home
  Assistant ignora a seção `http:` do `configuration.yaml` depois da primeira inicialização.
- Bloqueia a porta para a rede local: o acesso passa só pelo Caddy
  (`https://<endereço> → http://host.containers.internal:<porta>`). De fora de casa, pelo Tailscale.

## Depois de instalar

No app do celular ou do tablet, use "Inserir endereço manualmente" com `https://<endereço no Caddy>` e entre com o
usuário administrador. Depois, em Configurações → Dispositivos e serviços → Adicionar integração, procure a marca ou o aparelho. Muitos aparelhos da rede local aparecem sozinhos
em "Descobertos".

O log mostra erros do Bluetooth (`Missing NET_ADMIN/NET_RAW`): o container rootless não controla o Bluetooth da
máquina. Não afeta integrações pela rede.

## Arquivos

| Caminho | Conteúdo |
|---|---|
| `~/.astro/homeassistant/.env` | Respostas da instalação e o fuso |
| `~/.astro/homeassistant/config/` | Toda a configuração do Home Assistant (montada em `/config`) |

No backup das configurações (rclone), o banco em uso (`home-assistant_v2.db`) fica de fora: entra uma cópia
consistente, `home-assistant_v2.backup.db`, feita pelo próprio SQLite logo antes. Na restauração, essa cópia volta
a ser o `home-assistant_v2.db`.

## Remoção

`remove` tira o container, a imagem, a rota do Caddy e o bloqueio da porta, e apaga `~/.astro/homeassistant`.
