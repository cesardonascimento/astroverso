# cloud

Liga pastas da máquina a uma conta na nuvem pelo [rclone](https://rclone.org): **sincronizações de duas vias** (as
duas pontas ficam iguais) e **envios de uma via** (a nuvem vira um espelho da pasta). Você escolhe as pastas e para
onde elas vão: o Astroverso não decide o que vai para a nuvem. Por enquanto, a nuvem é o Proton Drive
(`proton.py`; outro provedor entra como outro módulo).

## O que a instalação faz

1. Instala o `rclone` (pacote da distribuição, sem container).
2. **Contas na nuvem:** conecta uma conta (o login é testado na hora). Passo a passo: [proton.md](docs/proton.md).
3. **Sincronizações e envios:** cada um é uma pasta da máquina (pelo seletor de pastas, `kit.folders`) e uma pasta da
   conta (num menu que navega pelas pastas da nuvem, com "Criar uma pasta aqui").
4. Publica as pastas ligadas pelo `kit.clouds` (`~/.astroverso/clouds/cloud.json`): é a marca ☁ nos seletores dos
   outros apps (ex.: "Proton Drive (duas vias)").
5. Pergunta as mudanças no sistema e mostra o Resumo da nuvem.

Na reinstalação com a configuração salva, não pergunta nada (a conta sem login nesta máquina pede o login).

## Duas vias (de hora em hora)

`rclone bisync` da pasta da máquina com a da nuvem, no minuto 20 de cada hora.

| Situação | O que acontece |
|---|---|
| Arquivo alterado dos dois lados | Fica o mais novo; o outro vira `<nome>.conflict1` ao lado |
| Primeira rodada, ou o estado se perdeu | Junta os dois lados sem apagar nada (`--resync --resync-mode newer`). Arquivo igual dos dois lados (tamanho e data) não é transferido: uma pasta que já estava sincronizada volta sem baixar tudo |
| Rodada interrompida (internet, reinício) | A seguinte continua (`--resilient --recover`); as travas que sobraram são limpas |
| Mais de 5% dos arquivos para apagar | Para sem apagar nada; **Liberar exclusões** mostra a lista e libera com a sua confirmação (`--force`) |

Renomear ou mover uma pasta grande, para o rclone, é apagar uma e criar outra: pode passar dos 5%.

## Uma via (todo dia às 05:00)

`rclone sync` da pasta da máquina para a da nuvem: o que sai da pasta sai da nuvem. Às 05:00, depois dos backups da
madrugada (e da manutenção de domingo do app `backup`), para não enviar uma pasta de backups no meio de uma gravação.
Trava em 5% dos arquivos da pasta (mínimo 10) para apagar, liberada pela mesma ação.

## Nas duas

- Pasta num disco desligado ou travado (`kit.disks.available`): a rodada não roda (uma pasta vazia pareceria "tudo
  apagado") e fica como falha.
- O rclone roda por `podman unshare`, para mexer também nos arquivos gravados por containers (ex.: o Nextcloud).
- Uma trava impede duas rodadas ao mesmo tempo: a sincronização da hora pula a vez; o envio das 05:00 espera.
- Sem regra nem validação de destino: se um envio cair dentro de uma pasta de duas vias, a escolha é sua.

## Mudanças na máquina

| Mudança | Por quê | ⚠ |
|---|---|---|
| Pacote `rclone` | O programa que fala com a nuvem | |
| `~/.astroverso/cloud/` (`.env`, `rclone.conf` `600` com as contas e as senhas ofuscadas, `accounts.json`, `jobs.json`, `state.json` com a última rodada, `watch.json`) | A configuração e o estado | |
| `~/.astroverso/clouds/cloud.json` | As pastas ligadas, para a marca ☁ dos outros apps | |
| `~/.cache/rclone/bisync/` | As listas da última rodada de cada sincronização (do próprio rclone) | |
| Unidades do usuário `astroverso-cloud-sync.timer` e `.service` (perguntada) | As sincronizações de duas vias de hora em hora | ⚠ |
| Unidades do usuário `astroverso-cloud-send.timer` e `.service` (perguntada) | Os envios às 05:00 | ⚠ |
| Unidades do usuário `astroverso-cloud-watch.timer` e `.service` (perguntada) | A verificação de hora em hora | |
| Unidades do usuário `astroverso-cloud-backup.timer` e `.service` (perguntada, com as pastas de destino) | Backup diário da configuração (sem as senhas) no servidor de backup | |

## Fora da máquina (passos seus)

| Passo | Por quê | Como fazer |
|---|---|---|
| Entrar uma vez pelo site do Proton Drive | O rclone não conclui o primeiro acesso de uma conta nova | [proton.md](docs/proton.md#antes-de-começar) |

## Ações

| Ação | O que faz |
|---|---|
| Resumo da nuvem | Contas, sincronizações e envios com a última rodada, mudanças e verificação. Também no Discord |
| Contas na nuvem | Adicionar, entrar de novo (sessão encerrada) e remover uma conta desta máquina (nada é apagado na nuvem) |
| Sincronizações e envios | Adicionar e tirar (tirar não apaga nada, nem na máquina nem na nuvem) |
| Sincronizar agora / Enviar agora | Uma rodada na hora (também no Discord) |
| Liberar exclusões | Para uma rodada travada nos 5%: mostra o que seria apagado e, com confirmação, roda liberando |
| Mudanças no sistema / Verificar agora / Fazer backup agora / Restaurar uma versão | Como nos outros apps. O backup leva as contas (provedor e e-mail), as sincronizações e os envios, sem as senhas: na restauração, cada conta pede o login de novo |

## Verificação de hora em hora

Avisa no canal `#cloud` do Discord só quando algo muda, com os botões **Resumo da nuvem** e **Sincronizar agora**:

| O que confere | Nível |
|---|---|
| Rodada com exclusões travadas | erro |
| Rodada que falhou (login, internet, disco indisponível) | erro |
| Duas vias sem rodada certa há mais de 3 h, envio há mais de 30 h | aviso |

## Remover

Desliga os timers e a verificação, retira as pastas ligadas do `kit.clouds` e apaga `~/.astroverso/cloud` (com as
senhas). As pastas da máquina e da nuvem ficam como estão.

Testes: `python3 -m unittest discover -s apps/cloud/tests`.
