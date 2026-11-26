# devenv

O ambiente de desenvolvimento no terminal, a partir de dois repositórios seus: o **astroverso-devenv** instala os
programas (pelo `linux/install.sh` dele) e o **astroverso-dotfiles** aplica as configurações por cima. Este app só
clona os dois e roda os instaladores: a lista de programas e as configurações são dos repositórios.

## O que a instalação faz

| Pergunta | Padrão |
|---|---|
| Repositório do astroverso-devenv | sem padrão (ex.: `git@github.com:<conta>/astroverso-devenv.git`) |
| Repositório do astroverso-dotfiles | sem padrão |

1. Confere o acesso aos dois repositórios. Repositório privado precisa da máquina aceita pelo GitHub: a chave desta
   máquina (app `system` → **Chave desta máquina para o GitHub**) ou o agente do seu computador (`ssh -A`).
2. Clona os dois em `~/Projects/<repositório>` (se já existirem, `git pull --ff-only`).
3. Roda o `linux/install.sh` do devenv (pede o `sudo`): zsh, Starship, Zellij, asdf com o Node LTS e o pnpm, Claude Code,
   Podman com `docker` e `docker compose` compatíveis, o zsh como shell.
4. Roda o `install.sh` dos dotfiles: os links das configurações e o timer diário do `dotfiles-update`.
5. Confere o que o `dotfiles-update` precisa para rodar sozinho todo dia (abaixo).

Na reinstalação com a configuração salva, não pergunta nada.

## O `dotfiles-update`

O timer dos dotfiles roda uma vez por dia, sem ninguém logado e sem o agente do seu computador. Para isso, a máquina
precisa de:

| O que | Por quê | Se faltar |
|---|---|---|
| O timer `astroverso-dotfiles-update.timer` ligado | É ele que roda a atualização | O `install.sh` dos dotfiles liga |
| O linger do usuário | Timers do usuário só rodam sem ninguém logado com ele | Os apps com containers já ligam; senão, `sudo loginctl enable-linger $USER` |
| Acesso ao repositório sem o agente | O timer usa a chave da própria máquina | App `system` → **Chave desta máquina para o GitHub** |

A instalação, o Resumo e a ação **Conferir o dotfiles-update** mostram o que falta. O app não liga nada disso por conta
própria.

## Mudanças na máquina

| Mudança | Por quê |
|---|---|
| `~/Projects/<devenv>` e `~/Projects/<dotfiles>` | Os dois repositórios |
| Tudo o que o `linux/install.sh` do devenv e o `install.sh` dos dotfiles fazem | Veja o README de cada um |
| `~/.astroverso/devenv/.env` (os endereços dos repositórios) | A configuração |
| Unidades do usuário `astroverso-devenv-backup.timer` e `.service` (perguntada, com as pastas de destino) | Backup diário da configuração no servidor de backup (`kit.backup`) |

## Ações

| Ação | O que faz |
|---|---|
| Resumo do ambiente | Os repositórios (último commit), os programas e o `dotfiles-update`. Também no Discord |
| Atualizar | Puxa os dois repositórios e roda os dois instaladores de novo (atualiza os programas) |
| Conferir o dotfiles-update | O que falta para o timer rodar sozinho. Também no Discord |
| Mudanças no sistema / Fazer backup agora / Restaurar uma versão | Como nos outros apps |

## Remover

Desliga o backup diário e apaga `~/.astroverso/devenv`. Os programas, os repositórios e as configurações dos dotfiles
ficam: este app só os instalou.

Testes: `python3 -m unittest discover -s apps/devenv/tests`.
