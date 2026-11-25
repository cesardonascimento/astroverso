# system

Configurações da própria máquina, em módulos: **energia** (sempre ligada, mesmo de tampa fechada) e **SSH** (acesso
remoto, chaves autorizadas e a chave desta máquina para o GitHub). Cada mudança no sistema é perguntada na
instalação (padrão sim) e pode ser desfeita e refeita em **Gerenciar → Mudanças no sistema**; as marcadas com ⚠ são
importantes para a máquina continuar acessível.

## O que a instalação faz

1. **Energia:** pergunta cada ajuste (tabela abaixo) e aplica os escolhidos.
2. **SSH:** pergunta cada ajuste e aplica os escolhidos. Na primeira vez, as chaves que já estão em
   `~/.ssh/authorized_keys` aparecem num checklist (marcadas) para você confirmar e dar um nome a cada uma (o PC).
3. Pergunta se deve preparar a chave desta máquina para o GitHub: cria `~/.ssh/id_ed25519` (se faltar), mostra a
   chave pública e o link para o passo a passo, e confere quando você disser que cadastrou.
4. Mostra o Resumo da máquina.

O login por senha no SSH continua como na distribuição: as chaves só deixam os seus PCs entrarem sem senha. Se um
PC autorizado for perdido, entre de outro aparelho com a senha e remova a chave dele em **Chaves SSH autorizadas**.

## Mudanças na máquina

| Mudança | Por quê | ⚠ |
|---|---|---|
| Suspensão e hibernação mascaradas (`sleep`, `suspend`, `hibernate`, `hybrid-sleep`, `suspend-then-hibernate`) | Nada põe a máquina para dormir: ela fica acessível 24 horas | ⚠ |
| `/etc/systemd/logind.conf.d/99-astroverso-lid.conf` (`HandleLidSwitch`, `HandleLidSwitchExternalPower`, `HandleLidSwitchDocked` = `ignore`) | O notebook fica de tampa fechada sem suspender | ⚠ |
| `/etc/systemd/logind.conf.d/99-astroverso-keys.conf` (teclas de suspender e hibernar e `IdleAction` = `ignore`) | Uma tecla esbarrada não derruba o servidor; o botão de ligar segue normal | |
| Serviço `astroverso-console-blank` (`setterm --blank 1 --powerdown 1` no console, no boot) | A tela do console apaga depois de 1 minuto sem uso, em vez de ficar acesa de tampa fechada | |
| `openssh-server` instalado (se faltar) e `sshd` ligado agora e no boot | O acesso remoto ao terminal | ⚠ |
| Firewall: serviço `ssh` só da rede local e do Tailscale (`100.64.0.0/10`), por regras ricas | Mesmo com a porta 22 aberta no roteador por engano, a internet não chega ao SSH | |
| `/etc/ssh/sshd_config.d/10-astroverso.conf` (`AllowUsers <usuário>`, `PermitRootLogin no`), conferido pelo `sshd -t` | Só a sua conta desta máquina entra por SSH | |
| `~/.ssh/authorized_keys` gerado a partir de `~/.astroverso/system/ssh-keys.json` | Só os PCs da lista entram sem senha; a lista tem um nome por chave | |
| `~/.ssh/id_ed25519` (só se você pedir a chave para o GitHub) | A chave desta máquina para baixar e atualizar repositórios por SSH | |
| `~/.astroverso/system/.env` (`CHANGE_<ID>=yes/no`) | As respostas da instalação, para o Reinstalar | |
| Unidades do usuário `astroverso-system-backup.timer` e `.service` (perguntada, padrão sim) | Backup diário da configuração do app no servidor de backup (`kit.backup`), com aviso no `#backup` | |

## Fora da máquina (passos seus)

| Passo | Por quê | Como fazer |
|---|---|---|
| Cadastrar a chave desta máquina no GitHub (opcional) | Para a máquina baixar e atualizar repositórios privados sem senha | [github.md](docs/github.md#cadastrar-a-chave) |

## Ações

| Ação | O que faz |
|---|---|
| Resumo da máquina | Cada mudança (aplicada ou desfeita), as chaves autorizadas (PC, tipo, impressão digital) e a chave do GitHub. Também no Discord: `/astro system:summary` |
| Mudanças no sistema | Checklist com as mudanças aplicadas marcadas; marcar aplica, desmarcar desfaz (as ⚠ pedem confirmação) |
| Chaves SSH autorizadas | Lista, adiciona (cole a chave pública do PC) e remove chaves |
| Chave desta máquina para o GitHub | Cria a chave (se faltar), mostra a parte pública e confere o acesso |
| Fazer backup agora / Restaurar uma versão | Backup da configuração na hora (também no Discord) e restauração de uma versão guardada no servidor de backup (app `backup`), com uma cópia "antes-da-restauracao" |

## Remover

Desfaz as mudanças, menos o servidor SSH, e apaga `~/.astroverso/system`. O `sshd` e o `~/.ssh/authorized_keys`
ficam, para você não perder o acesso. A chave desta máquina (`~/.ssh/id_ed25519`) também fica.

## Backup

O `.env` (as respostas) e a lista de chaves. Ao restaurar, as mudanças são reaplicadas e o `authorized_keys` é
gerado de novo.

Testes: `python3 -m unittest discover -s apps/system/tests`.
