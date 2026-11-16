# desktop

Área de trabalho de quem instala no backup das configurações: os apps Flatpak instalados (pelo Bazaar ou pela
linha de comando) e as extensões do GNOME, com as opções delas. Os **dados** dos apps (`~/.var/app`) ficam de
fora: depois de restaurar, cada app volta instalado, mas zerado.

```bash
./project.sh install           # prepara ~/.astro/desktop e faz a primeira foto da área de trabalho
./project.sh backup            # chamado pelo backup das configurações (01:00 e "agora")
./project.sh restore <pasta>   # chamado por "Backup: configurações ⬅️ local"
./project.sh remove            # apaga ~/.astro/desktop (usado pelo Implodir Astro)
```

Sem container e sem perguntas na instalação.

## O que vai para o backup

A cada backup das configurações, o comando `backup` atualiza `~/.astro/desktop`, que vai junto com os outros
serviços (criptografado):

| Arquivo | O que é |
|---|---|
| `flatpak-apps.txt` | um app por linha: id, origem (ex.: `flathub`) e instalação (`system` ou `user`) |
| `extensions/` | cópia de `~/.local/share/gnome-shell/extensions` (as extensões instaladas pelo usuário) |
| `gnome-shell.dconf` | `dconf dump /org/gnome/shell/`: extensões ligadas, favoritos da dock e as opções de cada extensão |

As extensões que vêm com o sistema (ex.: Apps Menu) não são copiadas, mas ficam ligadas pela lista do `dconf`.

## Restauração

Em Administração → Backup: configurações ⬅️ local → `desktop`:

- instala de novo, pela origem guardada, os apps Flatpak que faltam (os do sistema pedem `sudo`). Um app que não
  instala vira aviso; o resto segue;
- devolve as extensões para `~/.local/share/gnome-shell/extensions` (substitui as de mesmo nome);
- carrega o `gnome-shell.dconf` com `dconf load /org/gnome/shell/`;
- avisa para sair e entrar de novo na sessão: o GNOME só carrega extensões novas no login.

## Remoção

Apaga `~/.astro/desktop`. Os apps e as extensões instalados continuam na máquina.
