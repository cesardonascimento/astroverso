# backup

O servidor de backup da casa, com as **pastas de destino**, e a ligação de cada máquina a ele. **Quem decide o que vai
para onde são os apps:** cada app manda o próprio backup pelo `kit.backup` e escolhe para quais pastas de destino ele
vai (ninguém varre os apps). O app `backup` só diz quais pastas existem. O aviso sai no canal `#backup` do Discord.

```
qualquer máquina                                          máquina do servidor
  timer astroverso-<app>-backup (01:MM)                     container astroverso-backup
  → astroverso <app> action backup-now                      rclone serve restic --append-only --private-repos
  → backup(pasta) do app → restic ── https://backup.<domínio>/<máquina>/<id da pasta>/ ──→ <pasta de destino>/<máquina>/
                                     (Caddy; só rede local e Tailscale)                    domingo 04:00: forget --prune + check
```

- **Pastas de destino** são só caminhos na máquina do servidor (sem nome, sem regra de local ou nuvem). O seletor
  mostra o disco, o espaço e a marca ☁ quando a pasta está ligada a uma nuvem (`kit.clouds`), só como informação.
- **Um repositório por máquina em cada pasta de destino** (`<pasta>/<máquina>/`), criptografado no cliente. Os apps
  da máquina dividem o repositório, cada um com a própria série de versões (marca `app:<nome>`; os dados também com
  `dados:<nome>`). Dentro da pasta, tudo fica criptografado e em pedaços: abre-se pelo Restaurar dos apps.
- **Só acréscimos:** com `--append-only`, uma máquina grava versões novas mas não apaga nada; com `--private-repos`,
  só enxerga o próprio repositório. Só o servidor apaga as versões antigas, pela regra (padrão: 30 diárias e 12
  mensais), na manutenção semanal.
- **O mesmo caminho em todas as máquinas**, inclusive a do servidor: tudo passa por `https://backup.<domínio>`.

## Modos

| Modo | O que faz |
|---|---|
| **Servidor** (uma máquina) | Pergunta a regra das versões e as pastas de destino (pelo menos uma), sobe o container, publica `backup.<domínio>`, cadastra esta máquina e liga o envio dela. Se as pastas já têm backups desta máquina (reinstalação), pede a senha do repositório antiga em vez de gerar outra |
| **Cliente** (as outras) | Pede o código de ligação (endereço, usuário e pastas de destino, sem segredos) e as duas senhas, da ação **Adicionar uma máquina** do servidor; confere e cria os repositórios |

Nos dois modos, a máquina fica ligada ao servidor por `~/.astroverso/backup.env` (`600`) e
`~/.astroverso/backup-destinations.json`, usados pelo `kit.backup` de todos os apps dela. Pasta de destino nova ou
retirada: no servidor, a lista desta máquina se atualiza sozinha; nas outras, **Atualizar as pastas de destino** com o
código novo. As senhas e a importância da senha do repositório: [senhas.md](docs/senhas.md).

## Backup nos apps (`kit.backup`)

Todo app que tem `backup(pasta)` e `restore(pasta)` ganha, com duas linhas:

- a mudança perguntada **"Fazer o backup da configuração do <app> todo dia (01:MM)"** (`kit.backup.change(APP)`;
  o minuto vem do nome do app, para não rodarem todos juntos). Ao ligar, ela pergunta **para quais pastas de
  destino** (pode marcar mais de uma; a resposta fica no `.env` do app). Para trocar, desligue e ligue de novo;
- as ações **Fazer backup agora** (também no `/astro`) e **Restaurar uma versão** (escolhe a pasta de destino e a
  data, com uma versão "antes-da-restauracao" antes de trocar).

Apps com dados (ex.: a pasta dos arquivos do Nextcloud, as pastas dos discos) usam também `kit.backup.data_change`
(02:MM), com as pastas de destino escolhidas à parte, e restauram numa pasta nova, sem mexer na original.

Sem a máquina ligada a um servidor, ligar o backup só avisa: ele fica para depois, em Mudanças no sistema.

## Mudanças na máquina

| Mudança | Por quê |
|---|---|
| Pacote `restic` | O programa de backup (criptografia, deduplicação, versões) |
| `~/.astroverso/backup.env` (`600`, endereço, usuário e as duas senhas) e `~/.astroverso/backup-destinations.json` | Liga a máquina ao servidor: é o que o `kit.backup` dos apps usa |
| Servidor: Podman e *linger*; container `astroverso-backup` (imagem oficial `rclone/rclone`, versão fixada), sem porta na máquina | O servidor dos repositórios; o Caddy chega nele pelo nome |
| Servidor: `~/.astroverso/routes/backup.json` | O endereço `backup.<domínio>` no Caddy |
| Servidor: `~/.astroverso/backup/` (`.env`, `destinations.json`, `clients/<máquina>.env` `600`, `htpasswd`, `maintenance.json`) | A configuração, as pastas de destino, os dados de cada máquina e o resultado da manutenção |
| Servidor: `<pasta de destino>/<máquina>/` em cada pasta de destino | Os repositórios. Pasta num disco do app `disks` entra no container sem reetiquetar (o disco já é `container_file_t`) |
| ⚠ Servidor: unidades `astroverso-backup-maintenance.timer` e `.service` (perguntada) | A manutenção semanal; sem ela, as versões nunca são apagadas |
| Servidor: unidades `astroverso-backup-watch.timer` e `.service` (perguntada) | A verificação de hora em hora |
| Unidades `astroverso-backup-backup.timer` e `.service` (perguntada) | O backup do próprio app (a configuração, sem as senhas) |

## Fora da máquina (passos seus)

| Passo | Por quê | Como fazer |
|---|---|---|
| Guardar a senha do repositório de cada máquina no gerenciador de senhas | Sem ela, os backups não abrem | [senhas.md](docs/senhas.md) |
| PC com Windows (sem Astroverso): restic, dois arquivos `.ps1` e uma tarefa agendada | O PC manda os backups das pastas dele para o servidor, acompanhado como as outras máquinas (etiquetas `app:windows` e `dados:<nome>`) | [windows.md](docs/windows.md) |

## Ações

| Ação | O que faz |
|---|---|
| Resumo dos backups | Servidor, regra, pastas de destino com o espaço e a marca ☁, e o último backup de cada app de cada máquina em cada pasta. Também no Discord |
| Pastas de destino (servidor) | Adicionar (pelo seletor de pastas) e tirar pastas de destino. Os backups de uma pasta tirada ficam nela |
| Adicionar uma máquina / Mostrar os dados de uma máquina / Descadastrar máquinas (servidor) | Os dados de acesso, o código de ligação e o endereço do repositório em cada pasta de destino (para um PC sem Astroverso) de cada máquina (os repositórios de quem sai ficam nas pastas). Máquina que está voltando: usa a senha do repositório antiga, conferida nos backups que já existem; só a senha de acesso é nova |
| Atualizar as pastas de destino (cliente) | Cola o código de ligação novo depois de uma mudança nas pastas do servidor |
| Manutenção dos repositórios agora | A manutenção semanal na hora (também no Discord, com confirmação) |
| Fazer backup agora / Restaurar uma versão | Do próprio app backup |
| Mudanças no sistema / Verificar agora | Como nos outros apps |

## Verificação de hora em hora (servidor)

| O que confere | Nível |
|---|---|
| Servidor parado | erro |
| Pasta de destino indisponível (disco desligado ou travado, pelo `kit.disks`) | erro |
| Máquina sem nenhum backup há mais de 36 h | erro |
| App de uma máquina sem backup numa pasta há mais de 36 h (até 14 dias; depois disso, o app saiu da máquina ou da pasta) | aviso |
| Manutenção semanal com problema | erro |

## Remover

Desfaz as mudanças, remove o container e o endereço e desliga o envio desta máquina. As pastas de destino **ficam**
(apague à mão, se quiser).

## Backup do próprio app

O `.env` (modo e regra) e a lista das pastas de destino. As senhas das máquinas ficam de fora de propósito: elas abrem os backups, então
vivem no gerenciador de senhas.

Testes: `python3 -m unittest discover -s apps/backup/tests`.
