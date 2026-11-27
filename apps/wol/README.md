# wol

Wake-on-LAN: liga as máquinas da rede de casa pelo "pacote mágico", pelo gerenciador ou pelo Discord. Quem manda o
pacote é a máquina do Astroverso, que está na rede: pelo Discord, funciona de qualquer lugar.

## O que a instalação faz

1. Oferece cadastrar uma máquina (abaixo).
2. Pergunta o backup diário e mostra o Resumo das máquinas.

**Cadastrar uma máquina** (ação **Máquinas da rede**): nome (o do Discord) e IP fixo. Com a máquina ligada, o app manda um
ping e lê o MAC da tabela de vizinhos (`ip neigh`); sem resposta, pede o MAC digitado. O que ligar na máquina:
[wake-on-lan.md](docs/wake-on-lan.md).

## Ligar

Se a máquina já responde ao ping, só avisa. Senão, manda o pacote mágico (UDP porta 9, para o broadcast geral e o da rede
local, pela biblioteca padrão do Python) a cada 4 s, por até 3 min, até ela responder.

## Mudanças na máquina

| Mudança | Por quê |
|---|---|
| `~/.astroverso/wol/` (`.env`, `machines.json` `600` com nome, IP e MAC de cada máquina) | O cadastro |
| Unidades do usuário `astroverso-wol-backup.timer` e `.service` (perguntada) | Backup diário do cadastro no vault (`kit.vault`) |

Sem porta aberta nem ajuste no firewall: o pacote só sai pela rede local.

## Fora da máquina (passos seus)

| Passo | Por quê | Como fazer |
|---|---|---|
| Reserva de IP no roteador para cada máquina | O app confere pelo IP se ela ligou | [wake-on-lan.md](docs/wake-on-lan.md#reserva-de-ip-no-roteador) |
| Wake-on-LAN na BIOS e na placa de rede (e o ping liberado no Windows) | Sem isso, a placa ignora o pacote | [wake-on-lan.md](docs/wake-on-lan.md#bios) |

## Ações

| Ação | O que faz |
|---|---|
| Resumo das máquinas | Cada máquina com IP, MAC, se está ligada agora (ping) e o comando do Discord. Também no Discord |
| Ligar uma máquina | Escolhe numa lista e liga |
| Máquinas da rede | Adicionar e remover |
| Ligar `<nome>` | Uma por máquina cadastrada, só no Discord: `/astro wol:ligar-<nome>` (aparece no `/astro` quando o agente atualiza a lista) |
| Mudanças no sistema / Fazer backup agora / Restaurar uma versão | Como nos outros apps |

## Remover

Desliga o backup diário e apaga `~/.astroverso/wol`.

Testes: `python3 -m unittest discover -s apps/wol/tests`.
