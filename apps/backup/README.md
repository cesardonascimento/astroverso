# backup

O servidor de backup das configurações dos apps de todas as máquinas da casa, e a ligação de cada máquina a ele.
**Cada app manda o próprio backup** pelo `kit.backup` (ninguém varre os apps): o app chama o seu `backup(pasta)`,
o `restic` manda a pasta criptografada para o servidor, e o aviso sai no canal `#backup` do Discord.

```
qualquer máquina                                       máquina do servidor
  timer astroverso-<app>-backup (01:MM)                  container astroverso-backup
  → astroverso <app> action backup-now                   rclone serve restic --append-only --private-repos
  → backup(pasta) do app → restic ───── https://backup.<domínio>/<máquina>/ ──→  <pasta dos backups>/<máquina>/
                                       (Caddy; só rede local e Tailscale)        domingo 04:00: forget --prune + check
```

- **Um repositório por máquina**, criptografado no cliente; cada app é uma série de versões (marcada `app:<nome>`).
- **Só acréscimos:** com `--append-only`, uma máquina grava versões novas mas não apaga nada; com `--private-repos`,
  só enxerga o próprio repositório. Só o servidor apaga as versões antigas, pela regra (padrão: 30 diárias e 12
  mensais), na manutenção semanal.
- **O mesmo caminho em todas as máquinas**, inclusive a do servidor: tudo passa por `https://backup.<domínio>`.

## Modos

| Modo | O que faz |
|---|---|
| **Servidor** (uma máquina) | Pergunta a pasta dos backups (padrão `~/Backups/astroverso`; depois, um disco de backup) e a regra das versões, sobe o container, publica `backup.<domínio>`, cadastra esta máquina e liga o envio dela |
| **Cliente** (as outras) | Pergunta o endereço, o usuário e as duas senhas (da ação **Adicionar uma máquina** do servidor), confere e cria o repositório |

Nos dois modos, a máquina fica ligada ao servidor por `~/.astroverso/backup.env` (`600`), usado pelo `kit.backup` de
todos os apps dela. As senhas e a importância da senha do repositório: [senhas.md](docs/senhas.md).

## Backup nos apps (`kit.backup`)

Todo app que tem `backup(pasta)` e `restore(pasta)` ganha, com duas linhas:

- a mudança perguntada **"Fazer o backup da configuração do <app> todo dia (01:MM)"** (`kit.backup.change(APP)`;
  o minuto vem do nome do app, para não rodarem todos juntos);
- as ações **Fazer backup agora** (também no `/astro`) e **Restaurar uma versão** (com uma versão
  "antes-da-restauracao" antes de trocar).

Sem o servidor configurado na máquina, o backup diário só avisa e não faz nada.

## Mudanças na máquina

| Mudança | Por quê |
|---|---|
| Pacote `restic` | O programa de backup (criptografia, deduplicação, versões) |
| `~/.astroverso/backup.env` (`600`, endereço, usuário e as duas senhas) | Liga a máquina ao servidor: é o que o `kit.backup` dos apps usa |
| Servidor: Podman e *linger*; container `astroverso-backup` (imagem oficial `rclone/rclone`, versão fixada), sem porta na máquina | O servidor dos repositórios; o Caddy chega nele pelo nome |
| Servidor: `~/.astroverso/routes/backup.json` | O endereço `backup.<domínio>` no Caddy |
| Servidor: `~/.astroverso/backup/` (`.env`, `clients/<máquina>.env` `600`, `htpasswd`, `maintenance.json`) | A configuração, os dados de cada máquina e o resultado da manutenção |
| Servidor: a pasta dos backups (padrão `~/Backups/astroverso`) | Os repositórios |
| ⚠ Servidor: unidades `astroverso-backup-maintenance.timer` e `.service` (perguntada) | A manutenção semanal; sem ela, as versões nunca são apagadas |
| Servidor: unidades `astroverso-backup-watch.timer` e `.service` (perguntada) | A verificação de hora em hora |
| Unidades `astroverso-backup-backup.timer` e `.service` (perguntada) | O backup do próprio app (a configuração, sem as senhas) |

## Fora da máquina (passos seus)

| Passo | Por quê | Como fazer |
|---|---|---|
| Guardar a senha do repositório de cada máquina no gerenciador de senhas | Sem ela, os backups não abrem | [senhas.md](docs/senhas.md) |

## Ações

| Ação | O que faz |
|---|---|
| Resumo dos backups | Servidor, pasta e espaço, regra, e o último backup de cada app de cada máquina. Também no Discord |
| Adicionar uma máquina / Mostrar os dados de uma máquina / Descadastrar máquinas | Os dados de acesso de cada máquina (o repositório de quem sai fica na pasta) |
| Manutenção dos repositórios agora | A manutenção semanal na hora (também no Discord, com confirmação) |
| Fazer backup agora / Restaurar uma versão | Do próprio app backup |
| Mudanças no sistema / Verificar agora | Como nos outros apps |

## Verificação de hora em hora (servidor)

| O que confere | Nível |
|---|---|
| Servidor parado | erro |
| Máquina sem nenhum backup há mais de 36 h | erro |
| App de uma máquina sem backup há mais de 36 h (até 14 dias; depois disso, o app saiu da máquina) | aviso |
| Manutenção semanal com problema | erro |

## Remover

Desfaz as mudanças, remove o container e o endereço e desliga o envio desta máquina. A pasta dos backups **fica**
(apague à mão, se quiser).

## Backup do próprio app

Só o `.env` (modo, pasta e regra). As senhas das máquinas ficam de fora de propósito: elas abrem os backups, então
vivem no gerenciador de senhas.

Testes: `python3 -m unittest discover -s apps/backup/tests`.
