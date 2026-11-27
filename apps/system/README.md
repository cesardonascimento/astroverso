# system

Configurações da própria máquina, em módulos: **nome da máquina**, **energia** (sempre ligada, mesmo de tampa fechada) e **SSH** (acesso
remoto, chaves autorizadas e a chave desta máquina para o GitHub). Cada mudança no sistema é perguntada na
instalação (padrão sim) e pode ser desfeita e refeita em **Gerenciar → Mudanças no sistema**; as marcadas com ⚠ são
importantes para a máquina continuar acessível.

## O que a instalação faz

1. **Nome da máquina:** pergunta o nome (o atual como padrão; letras minúsculas, números e hífen) e aplica pelo
   `hostnamectl`. Vem primeiro porque o Tailscale, o endereço do Cockpit e os backups usam o nome. Trocar depois
   pede reinstalar os apps que já usavam o nome antigo. O nome não volta ao anterior no Remover (decisão do usuário).
2. **Relógio:** pergunta se liga o acerto do relógio pela internet (NTP).
3. **Energia:** pergunta cada ajuste (tabela abaixo) e aplica os escolhidos.
4. **SSH:** pergunta cada ajuste e aplica os escolhidos. Na primeira vez, as chaves que já estão em
   `~/.ssh/authorized_keys` aparecem num checklist (marcadas) para você confirmar e dar um nome a cada uma (o PC).
5. Pergunta se deve preparar a chave desta máquina para o GitHub: cria `~/.ssh/id_ed25519` (se faltar), mostra a
   chave pública e o link para o passo a passo, e confere quando você disser que cadastrou.
6. Mostra o Resumo da máquina.

O login por senha no SSH continua como na distribuição: as chaves só deixam os seus PCs entrarem sem senha. Se um
PC autorizado for perdido, entre de outro aparelho com a senha e remova a chave dele em **Chaves SSH autorizadas**.

## Mudanças na máquina

| Mudança | Por quê | ⚠ |
|---|---|---|
| Nome da máquina (`hostnamectl set-hostname`, gravado em `HOSTNAME` no `.env`) | Identifica a máquina na rede, no Tailscale, no endereço do Cockpit e nos backups; fica no Remover | |
| Suspensão e hibernação mascaradas (`sleep`, `suspend`, `hibernate`, `hybrid-sleep`, `suspend-then-hibernate`) | Nada põe a máquina para dormir: ela fica acessível 24 horas | ⚠ |
| `/etc/systemd/logind.conf.d/99-astroverso-lid.conf` (`HandleLidSwitch`, `HandleLidSwitchExternalPower`, `HandleLidSwitchDocked` = `ignore`) | O notebook fica de tampa fechada sem suspender | ⚠ |
| `/etc/systemd/logind.conf.d/99-astroverso-keys.conf` (teclas de suspender e hibernar e `IdleAction` = `ignore`) | Uma tecla esbarrada não derruba o servidor; o botão de ligar segue normal | |
| Serviço `astroverso-console-blank` (`setterm --blank 1 --powerdown 1` no console, no boot) | A tela do console apaga depois de 1 minuto sem uso, em vez de ficar acesa de tampa fechada | |
| `openssh-server` instalado (se faltar) e `sshd` ligado agora e no boot | O acesso remoto ao terminal | ⚠ |
| Firewall: serviço `ssh` só da rede local e do Tailscale (`100.64.0.0/10`), por regras ricas | Mesmo com a porta 22 aberta no roteador por engano, a internet não chega ao SSH | |
| `/etc/ssh/sshd_config.d/10-astroverso.conf` (`AllowUsers <usuário>`, `PermitRootLogin no`), conferido pelo `sshd -t` | Só a sua conta desta máquina entra por SSH | |
| `~/.ssh/authorized_keys` gerado a partir de `~/.astroverso/system/ssh-keys.json` | Só os PCs da lista entram sem senha; a lista tem um nome por chave | |
| `~/.ssh/id_ed25519` (só se você pedir a chave para o GitHub) | A chave desta máquina para baixar e atualizar repositórios por SSH | |
| Pacote `chrony` e o acerto pela internet ligado (`timedatectl set-ntp true`: o `chronyd` liga, e o relógio do hardware passa a guardar UTC) (perguntada) | A hora certa sozinha: backups com a data certa, a sincronização da nuvem decidindo certo o arquivo mais novo e os timers no horário | |
| Pacote `dnf5-plugin-automatic`, `/etc/dnf/automatic.conf` (`apply_updates = yes`, `reboot = never`) e o timer `dnf5-automatic.timer` ligado (perguntada) | O sistema aplica as atualizações sozinho, todo dia por volta das 6h, sem nunca reiniciar; o reinício pendente é avisado no Discord | |
| Unidades do usuário `astroverso-system-watch.timer` e `.service` (perguntada) | A verificação de hora em hora (abaixo) | |
| `~/.astroverso/system/.env` (`CHANGE_<ID>=yes/no`) | As respostas da instalação, para o Reinstalar | |
| Unidades do usuário `astroverso-system-backup.timer` e `.service` (perguntada, padrão sim) | Backup diário da configuração do app no vault (`kit.vault`), com aviso no `#vault` | |

## Fora da máquina (passos seus)

| Passo | Por quê | Como fazer |
|---|---|---|
| Cadastrar a chave desta máquina no GitHub (opcional) | Para a máquina baixar e atualizar repositórios privados sem senha | [github.md](docs/github.md#cadastrar-a-chave) |

## Ações

| Ação | O que faz |
|---|---|
| Resumo da máquina | O nome da máquina, cada mudança (aplicada ou desfeita), as chaves autorizadas (PC, tipo, impressão digital) e a chave do GitHub. Também no Discord: `/astro system:summary` |
| Mudanças no sistema | Checklist com as mudanças aplicadas marcadas; marcar aplica, desmarcar desfaz (as ⚠ pedem confirmação) |
| Chaves SSH autorizadas | Lista, adiciona (cole a chave pública do PC) e remove chaves |
| Chave desta máquina para o GitHub | Cria a chave (se faltar), mostra a parte pública e confere o acesso |
| Verificar agora | A verificação de hora em hora na hora (também no Discord) |
| Fazer backup agora / Restaurar uma versão | Backup da configuração na hora (também no Discord) e restauração de uma versão guardada no vault (app `vault`), com uma cópia "antes-da-restauracao" |

## Verificação de hora em hora

Avisa no canal `#system` do Discord só quando algo muda, com os botões **Resumo da máquina** e **Verificar de novo**:

| O que confere | Nível |
|---|---|
| O acerto pela internet está ligado, mas o relógio não sincronizou (`timedatectl`: `NTPSynchronized=no`) | aviso |
| A última atualização automática falhou (`dnf5-automatic.service`) | erro |
| Uma atualização pede reinício (`dnf needs-restarting`): reinicie quando puder, pelo Cockpit, por exemplo | aviso |

## Remover

Desfaz as mudanças, menos o servidor SSH, e apaga `~/.astroverso/system`. O `sshd` e o `~/.ssh/authorized_keys`
ficam, para você não perder o acesso. A chave desta máquina (`~/.ssh/id_ed25519`) também fica.

## Backup

O `.env` (as respostas) e a lista de chaves. Ao restaurar, as mudanças são reaplicadas e o `authorized_keys` é
gerado de novo.

Testes: `python3 -m unittest discover -s apps/system/tests`.
