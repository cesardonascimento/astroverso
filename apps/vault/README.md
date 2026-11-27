# vault

O cofre das cópias de segurança da casa (restic), com as **pastas do vault**, e a ligação de cada máquina a ele. **Quem decide o que vai
para onde são os apps:** cada app manda o próprio backup pelo `kit.vault` e escolhe para quais pastas do vault ele
vai (ninguém varre os apps). O app `vault` só diz quais pastas existem. O aviso sai no canal `#vault` do Discord.

```
qualquer máquina                                          máquina do servidor
  timer astroverso-<app>-backup (01:MM)                     container astroverso-vault
  → astroverso <app> action backup-now                      rclone serve restic --append-only --private-repos
  → backup(pasta) do app → restic ── https://vault.<domínio>/<máquina>/<id da pasta>/ ──→ <pasta do vault>/<máquina>/
                                     (Caddy; só rede local e Tailscale)                    domingo 04:00: forget --prune + check
```

- **Pastas do vault** são só caminhos na máquina do servidor (sem nome, sem regra de local ou nuvem). O seletor
  mostra o disco, o espaço e a marca ☁ quando a pasta está ligada a uma nuvem (`kit.clouds`), só como informação.
- **Um repositório por máquina em cada pasta do vault** (`<pasta>/<máquina>/`), criptografado no cliente. Os apps
  da máquina dividem o repositório, cada um com a própria série de versões (marca `app:<nome>`; os dados também com
  `dados:<nome>`). Dentro da pasta, tudo fica criptografado e em pedaços: abre-se pelo Restaurar dos apps.
- **Só acréscimos:** com `--append-only`, uma máquina grava versões novas mas não apaga nada; com `--private-repos`,
  só enxerga o próprio repositório. Só o servidor apaga as versões antigas, pela regra (padrão: 30 diárias e 12
  mensais), na manutenção semanal.
- **Pasta do vault num disco ausente** (desligado, desconectado) fica fora do container, e o servidor sobe com as
  outras. A verificação de hora em hora (que também roda 10 min depois de a máquina ligar) refaz o container quando o
  conjunto de pastas disponíveis muda: tira a que sumiu e devolve a que voltou. Sem nenhuma pasta disponível, o
  servidor fica parado até uma voltar. O container é somente leitura: um backup para uma pasta ausente falha com erro,
  em vez de ser gravado num lugar temporário que some ao reiniciar.
- **O mesmo caminho em todas as máquinas**, inclusive a do servidor: tudo passa por `https://vault.<domínio>`.

## Modos

| Modo | O que faz |
|---|---|
| **Servidor** (uma máquina) | Pergunta a regra das versões e as pastas do vault (pelo menos uma), sobe o container, publica `vault.<domínio>`, cadastra esta máquina e liga o envio dela. Se as pastas já têm backups desta máquina (reinstalação), pede a senha do repositório antiga em vez de gerar outra |
| **Cliente** (as outras) | Pede o código de ligação (endereço, usuário e pastas do vault, sem segredos) e as duas senhas, da ação **Adicionar uma máquina** do servidor; confere e cria os repositórios |

Nos dois modos, a máquina fica ligada ao servidor por `~/.astroverso/vault.env` (`600`) e
`~/.astroverso/vault-folders.json`, usados pelo `kit.vault` de todos os apps dela. Pasta do vault nova ou
retirada: no servidor, a lista desta máquina se atualiza sozinha; nas outras, **Atualizar as pastas do vault** com o
código novo. As senhas e a importância da senha do repositório: [senhas.md](docs/senhas.md).

## Backup nos apps (`kit.vault`)

Todo app que tem `backup(pasta)` e `restore(pasta)` ganha, com duas linhas:

- a mudança perguntada **"Fazer o backup da configuração do <app> todo dia (01:MM)"** (`kit.vault.change(APP)`;
  o minuto vem do nome do app, para não rodarem todos juntos). Ao ligar, ela pergunta **para quais pastas de
  destino** (pode marcar mais de uma; a resposta fica no `.env` do app). Para trocar, desligue e ligue de novo;
- as ações **Fazer backup agora** (também no `/astro`) e **Restaurar uma fotografia** (escolhe a pasta do vault e a
  data, com uma versão "antes-da-restauracao" antes de trocar).

Apps com dados (ex.: a pasta dos arquivos do Nextcloud, as pastas dos discos) usam também `kit.vault.data_change`
(02:MM), com as pastas do vault escolhidas à parte, e restauram numa pasta nova, sem mexer na original.

Sem a máquina ligada a um servidor, ligar o backup só avisa: ele fica para depois, em Mudanças no sistema.

## Mudanças na máquina

| Mudança | Por quê |
|---|---|
| Pacote `restic` | O programa de backup (criptografia, deduplicação, versões) |
| `~/.astroverso/vault.env` (`600`, endereço, usuário e as duas senhas) e `~/.astroverso/vault-folders.json` | Liga a máquina ao servidor: é o que o `kit.vault` dos apps usa |
| Servidor: Podman e *linger*; container `astroverso-vault` (imagem oficial `rclone/rclone`, versão fixada), sem porta na máquina | O servidor dos repositórios; o Caddy chega nele pelo nome |
| Servidor: `~/.astroverso/routes/backup.json` | O endereço `vault.<domínio>` no Caddy |
| Servidor: `~/.astroverso/backup/` (`.env`, `destinations.json`, `clients/<máquina>.env` `600`, `htpasswd`, `maintenance.json`) | A configuração, as pastas do vault, os dados de cada máquina e o resultado da manutenção |
| Servidor: `<pasta do vault>/<máquina>/` em cada pasta do vault | Os repositórios. Pasta num disco do app `disks` entra no container sem reetiquetar (o disco já é `container_file_t`) |
| ⚠ Servidor: unidades `astroverso-vault-maintenance.timer` e `.service` (perguntada) | A manutenção semanal; sem ela, as versões nunca são apagadas |
| Servidor: unidades `astroverso-vault-watch.timer` e `.service` (perguntada) | A verificação de hora em hora |
| Unidades `astroverso-vault-backup.timer` e `.service` (perguntada) | O backup do próprio app (a configuração, sem as senhas) |

## Fora da máquina (passos seus)

| Passo | Por quê | Como fazer |
|---|---|---|
| Guardar a senha do repositório de cada máquina no gerenciador de senhas | Sem ela, os backups não abrem | [senhas.md](docs/senhas.md) |
| PC com Windows (sem Astroverso): restic, dois arquivos `.ps1` e uma tarefa agendada | O PC manda os backups das pastas dele para o servidor, acompanhado como as outras máquinas (etiquetas `app:windows` e `dados:<nome>`) | [windows.md](docs/windows.md) |

## Ações

| Ação | O que faz |
|---|---|
| Resumo dos backups | Servidor, regra, pastas do vault com o espaço e a marca ☁, e o último backup de cada app de cada máquina em cada pasta. Também no Discord |
| Pastas do vault (servidor) | Adicionar (pelo seletor de pastas) e tirar pastas do vault. Os backups de uma pasta tirada ficam nela |
| Adicionar uma máquina / Mostrar os dados de uma máquina / Descadastrar máquinas (servidor) | Os dados de acesso, o código de ligação e o endereço do repositório em cada pasta do vault (para um PC sem Astroverso) de cada máquina (os repositórios de quem sai ficam nas pastas). Máquina que está voltando: usa a senha do repositório antiga, conferida nos backups que já existem; só a senha de acesso é nova |
| Atualizar as pastas do vault (cliente) | Cola o código de ligação novo depois de uma mudança nas pastas do servidor |
| Manutenção dos repositórios agora | A manutenção semanal na hora (também no Discord, com confirmação) |
| Fazer backup agora / Restaurar uma fotografia | Do próprio app vault |
| Mudanças no sistema / Verificar agora | Como nos outros apps |

## Verificação de hora em hora (servidor)

| O que confere | Nível |
|---|---|
| Servidor parado | erro |
| Pasta do vault indisponível (disco desligado ou travado, pelo `kit.disks`) | erro |
| Máquina sem nenhum backup há mais de 36 h | erro |
| App de uma máquina sem backup numa pasta há mais de 36 h (até 14 dias; depois disso, o app saiu da máquina ou da pasta) | aviso |
| Manutenção semanal com problema | erro |

## Remover

Desfaz as mudanças, remove o container e o endereço e desliga o envio desta máquina. As pastas do vault **ficam**
(apague à mão, se quiser).

## Backup do próprio app

O `.env` (modo e regra) e a lista das pastas do vault. As senhas das máquinas ficam de fora de propósito: elas abrem os backups, então
vivem no gerenciador de senhas.

Testes: `python3 -m unittest discover -s apps/vault/tests`.
