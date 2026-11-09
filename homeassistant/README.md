# homeassistant

Automação da casa: junta num painel só os aparelhos de várias marcas (Tuya, LG, Samsung...) e permite criar
rotinas entre eles. Acessível em `https://homeassistant.<domínio>` pelo Caddy.

```bash
./project.sh install           # instala, configura o proxy e publica o painel no Caddy
./project.sh remove [--purge]  # remove o container; --purge apaga também a configuração
```

É o **Home Assistant Container**, a imagem oficial `ghcr.io/home-assistant/home-assistant` com a versão fixada no
`docker-compose.yml`. Não tem a loja de complementos (add-ons), que só existe no Home Assistant OS: o que for
preciso (Mosquitto, Zigbee2MQTT, ESPHome...) entra como outro container deste projeto.

## Perguntas da instalação

| Pergunta | Padrão |
|---|---|
| Endereço do Home Assistant no Caddy | `homeassistant.<domínio do caddy>` |
| Porta do Home Assistant no host | `8123` |

O fuso vem da máquina (`timedatectl`).

## O que a instalação faz

- Sobe o container `astro-homeassistant` em **`network_mode: host`**: a descoberta de aparelhos (mDNS, SSDP,
  DHCP) depende de broadcast e multicast na rede da casa, que não passam pela rede do Podman.
- Monta `~/.astro/homeassistant/config` em `/config` (`configuration.yaml`, banco, integrações e usuários).
- Configura o proxy em **`.storage/http`** (com o container parado): porta, `use_x_forwarded_for` e
  `trusted_proxies` (o host, a rede `astro_default` e o IP da máquina). Desde a migração da seção `http:` para a
  interface, o Home Assistant ignora essa seção do `configuration.yaml` depois da primeira inicialização.
- Bloqueia a porta para a rede local: o acesso passa só pelo Caddy
  (`https://<endereço> → http://host.containers.internal:<porta>`). De fora de casa, pelo Tailscale.

## Depois de instalar

Abra o endereço logo: o primeiro acesso cria o usuário administrador. Depois, em Configurações → Dispositivos e
serviços → Adicionar integração:

| Aparelhos | Integração |
|---|---|
| Tuya (Wi-Fi) e o hub Zigbee da Tuya | **Tuya** (login pelo QR code no app Smart Life ou Tuya) |
| TV LG | **LG webOS TV** (local) |
| Ar-condicionado LG | **LG ThinQ** (token pessoal da conta LG) |
| Ar-condicionado Samsung | **SmartThings** |

O log mostra erros do Bluetooth (`Missing NET_ADMIN/NET_RAW`): o container rootless não controla o Bluetooth da
máquina. Não afeta as integrações acima.

## Arquivos

| Caminho | Conteúdo |
|---|---|
| `~/.astro/homeassistant/.env` | Respostas da instalação e o fuso |
| `~/.astro/homeassistant/config/` | Toda a configuração do Home Assistant (montada em `/config`) |

No backup das configurações (rclone), o banco em uso (`home-assistant_v2.db`) fica de fora: entra uma cópia
consistente, `home-assistant_v2.backup.db`, feita pelo próprio SQLite logo antes. Na restauração, essa cópia volta
a ser o `home-assistant_v2.db`.

## Remoção

`remove` tira o container, a rota do Caddy e o bloqueio da porta, e mantém a configuração. `--purge` apaga
também a pasta da configuração.
