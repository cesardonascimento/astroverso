# cloud

Liga pastas a contas na nuvem pelo [rclone](https://rclone.org), **nas duas vias** (as duas pontas ficam iguais). A
pasta fica num disco da máquina ou **dentro do Nextcloud** (ex.: `/proton` da sua conta ⇄ a raiz do Proton Drive). Não
tem nada a ver com os backups nem com o Nextcloud em si: é só manter cópias dos seus dados nos serviços de nuvem e
vice-versa. Você escolhe as pastas e para onde elas vão. Provedores: Proton Drive (`proton.py`); o Nextcloud entra pelo
WebDAV (`nextcloud.py`), só como lado de uma sincronização; outro provedor entra como outro módulo.

## O que a instalação faz

1. Instala o `rclone` (pacote da distribuição, sem container).
2. **Contas na nuvem:** conecta uma conta (o login é testado na hora). Passo a passo: [proton.md](docs/proton.md) e
   [nextcloud.md](docs/nextcloud.md) (com uma senha de app).
3. **Sincronizações:** cada uma liga uma pasta ("Na máquina (um disco)", pelo seletor de pastas `kit.folders`, ou
   "Dentro do Nextcloud", navegando pelas pastas da sua conta) a uma pasta de uma conta na nuvem (num menu que navega
   pelas pastas da nuvem, com "Criar uma pasta aqui"). Na primeira pasta do Nextcloud, o app usa a mesma conexão do
   app `vault` (com confirmação) ou pede uma senha de app.
4. Publica as pastas ligadas pelo `kit.clouds` (`~/.astroverso/clouds/cloud.json`): é a marca ☁ nos seletores dos
   outros apps (ex.: "Proton Drive (duas vias)").
5. Pergunta as mudanças no sistema e mostra o Resumo da nuvem.

Na reinstalação com a configuração salva, não pergunta nada (a conta sem login nesta máquina pede o login).

## Duas vias (de 2 em 2 horas, das 08:00 às 20:00)

`rclone bisync` das duas pastas às 08, 10, 12, 14, 16, 18 e 20 horas: fora da madrugada, que fica para os backups
(01:00) e a fotografia dos discos (03:00).

| Situação | O que acontece |
|---|---|
| Arquivo alterado dos dois lados | Fica o mais novo; o outro vira `<nome>.conflict1` ao lado |
| Primeira rodada, ou o estado se perdeu | Junta os dois lados sem apagar nada (`--resync --resync-mode newer`). Arquivo igual dos dois lados (tamanho e data) não é transferido: uma pasta que já estava sincronizada volta sem baixar tudo |
| Rodada interrompida (internet, reinício) | A seguinte continua (`--resilient --recover`); as travas que sobraram são limpas |
| Mais de 5% dos arquivos para apagar | Para sem apagar nada; **Liberar exclusões** mostra a lista e libera com a sua confirmação (`--force`) |

Renomear ou mover uma pasta grande, para o rclone, é apagar uma e criar outra: pode passar dos 5%.

Não existe "sincronizar sem exclusões de dia e com exclusões à noite": numa sincronização de duas vias, uma exclusão
que não vai para o outro lado faz o arquivo voltar de lá na rodada seguinte. A proteção é a trava de 5%.

## Detalhes

- **Pasta do Nextcloud:** passa sempre pelo Nextcloud (WebDAV), nunca pela pasta dos arquivos dele no disco (o seletor
  recusa uma pasta com `.ncdata`/`.ocdata` acima dela). Ele fica em dia sem varredura, os arquivos ficam com o dono
  certo, e o que a nuvem apagar vai para a lixeira e as versões dele. Entre duas contas, o rclone roda sem `podman unshare`.
- Pasta num disco desligado ou travado (`kit.disks.available`): a rodada não roda (uma pasta vazia pareceria "tudo
  apagado") e fica como falha.
- O rclone roda por `podman unshare`, para mexer também nos arquivos gravados por containers (ex.: o Nextcloud).
- Uma trava impede duas rodadas ao mesmo tempo: a rodada seguinte pula a vez.

## Mudanças na máquina

| Mudança | Por quê | ⚠ |
|---|---|---|
| Pacote `rclone` | O programa que fala com a nuvem | |
| `~/.astroverso/cloud/` (`.env`, `rclone.conf` `600` com as contas e as senhas ofuscadas, `accounts.json`, `jobs.json`, `state.json` com a última rodada, `watch.json`) | A configuração e o estado | |
| `~/.astroverso/clouds/cloud.json` | As pastas ligadas, para a marca ☁ dos outros apps | |
| `~/.cache/rclone/bisync/` | As listas da última rodada de cada sincronização (do próprio rclone) | |
| Unidades do usuário `astroverso-cloud-sync.timer` e `.service` (perguntada) | As sincronizações de 2 em 2 horas, das 08:00 às 20:00 (a reinstalação tira o antigo `astroverso-cloud-send`) | ⚠ |
| Unidades do usuário `astroverso-cloud-watch.timer` e `.service` (perguntada) | A verificação de hora em hora | |
| Unidades do usuário `astroverso-cloud-backup.timer` e `.service` (perguntada) | Backup diário da configuração (sem as senhas) no vault | |

## Fora da máquina (passos seus)

| Passo | Por quê | Como fazer |
|---|---|---|
| Entrar uma vez pelo site do Proton Drive | O rclone não conclui o primeiro acesso de uma conta nova | [proton.md](docs/proton.md#antes-de-começar) |
| Criar uma senha de app no Nextcloud (se não usar a do app `vault`) | O app cloud não usa a sua senha de login | [nextcloud.md](docs/nextcloud.md#criar-a-senha-de-app) |

## Ações

| Ação | O que faz |
|---|---|
| Resumo da nuvem | Contas, sincronizações com a última rodada, mudanças e verificação. Também no Discord |
| Contas na nuvem | Adicionar, entrar de novo (sessão encerrada) e remover uma conta desta máquina (nada é apagado na nuvem) |
| Sincronizações | Adicionar e tirar (tirar não apaga nada, nem na máquina nem na nuvem) |
| Sincronizar agora | Uma rodada na hora (também no Discord) |
| Liberar exclusões | Para uma rodada travada nos 5%: mostra o que seria apagado e, com confirmação, roda liberando |
| Mudanças no sistema / Verificar agora / Fazer backup agora / Restaurar uma versão | Como nos outros apps. O backup leva as contas (provedor e e-mail) e as sincronizações, sem as senhas: na restauração, cada conta pede o login de novo |

## Verificação de hora em hora

Avisa no canal `#cloud` do Discord só quando algo muda, com os botões **Resumo da nuvem** e **Sincronizar agora**:

| O que confere | Nível |
|---|---|
| Rodada com exclusões travadas | erro |
| Rodada que falhou (login, internet, disco indisponível) | erro |
| Sincronização sem rodada certa há mais de 14 h | aviso |

## Remover

Desliga os timers e a verificação, retira as pastas ligadas do `kit.clouds` e apaga `~/.astroverso/cloud` (com as
senhas). As pastas da máquina e da nuvem ficam como estão.

Testes: `python3 -m unittest discover -s apps/cloud/tests`.
