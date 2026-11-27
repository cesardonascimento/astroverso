# cockpit

O painel web da máquina: uso de CPU e memória, logs, serviços, terminal, armazenamento, arquivos e os containers do
Astroverso (logs, reiniciar, parar), em `https://<nome-da-máquina>.<domínio>` pelo Caddy. O login é o usuário e a
senha do sistema; com **Acesso administrativo** ligado no topo do painel, ele mexe em qualquer coisa da máquina.

Diferente dos outros apps, o Cockpit não roda em container: são pacotes do sistema, porque ele administra a própria
máquina.

## O que a instalação faz

| Pergunta | Padrão |
|---|---|
| Endereço do Cockpit | `<nome-da-máquina>.<domínio>`: cada máquina da casa tem o seu painel |

1. Instala `cockpit`, `cockpit-podman` (containers), `cockpit-storaged` (armazenamento) e `cockpit-files` (arquivos)
   pela camada `kit.distro` (se faltarem).
2. Pergunta as mudanças no sistema.
3. Publica o endereço pelo `kit.routes` (`http://host.containers.internal:9090`; o Caddy do `network` recarrega
   sozinho).

Na reinstalação com a configuração salva, não pergunta nada.

## Mudanças na máquina

| Mudança | Por quê | ⚠ |
|---|---|---|
| Pacotes `cockpit`, `cockpit-podman`, `cockpit-storaged` e `cockpit-files` | O painel e as páginas de containers, armazenamento e arquivos | |
| `cockpit.socket` ligado (perguntada) | O painel sobe sob demanda, na porta 9090 | ⚠ |
| `/etc/cockpit/cockpit.conf` (perguntada): `Origins` com o endereço, `ProtocolHeader = X-Forwarded-Proto`, `AllowUnencrypted = true` | Sem isso, o Cockpit recusa o login vindo do Caddy | ⚠ |
| Serviço `cockpit` fechado no firewall (perguntada) | O painel só abre pelo endereço com cadeado; se o Caddy cair, o caminho de volta é o SSH | |
| `podman.socket` do usuário ligado (perguntada) | A página de containers enxerga os containers rootless do Astroverso | |
| `~/.astroverso/cockpit/.env` (o endereço) e `~/.astroverso/routes/cockpit.json` | A configuração e o endereço publicado para o Caddy | |
| Unidades do usuário `astroverso-cockpit-backup.timer` e `.service` (perguntada, com as pastas do vault) | Backup diário da configuração no vault (`kit.vault`) | |

## Armazenamento

Montar disco de dados é pelo app `disks` (no boot, destravado pelo TPM). O Armazenamento do Cockpit fica para
formatar e consultar: ele regrava as linhas do `fstab` que edita (o `kit.disks` reconhece as linhas do Astroverso
mesmo assim), e um disco montado por ele não sobe sozinho no boot.

## Ações

| Ação | O que faz |
|---|---|
| Resumo do Cockpit | Endereço, painel ligado e mudanças. Também no Discord |
| Mudanças no sistema / Fazer backup agora / Restaurar uma fotografia | Como nos outros apps |

## Remover

Desfaz as mudanças (desliga o painel, apaga o `cockpit.conf`, reabre o serviço no firewall, desliga o
`podman.socket`) e retira o endereço do Caddy. Os pacotes ficam: o Fedora Server já vem com o Cockpit.

Testes: `python3 -m unittest discover -s apps/cockpit/tests`.
