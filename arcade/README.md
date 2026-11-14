# arcade

Videogame retrô do homelab: o [ES-DE](https://es-de.org) (a vitrine dos jogos, com capas e vídeos) e o
[RetroArch](https://www.retroarch.com) (os emuladores) num usuário próprio para jogos, transmitidos pelo
[Sunshine](https://github.com/LizardByte/Sunshine) para o [Moonlight](https://moonlight-stream.org). O Sunshine
só existe aqui para isso.

O usuário de jogos é a **exceção** do homelab: ele entra sozinho no boot e fica com a tela aberta na TV, e por
isso é separado do usuário que instala, que lida com dados sensíveis e nunca fica logado. Para todo o resto,
quem manda é o usuário que instala.

```bash
./project.sh install           # instala, configura e publica o painel do Sunshine no Caddy
./project.sh remove           # desfaz tudo o que o projeto criou, inclusive o usuário de jogos (usado pelo Implodir Astro)
```

Como o cockpit, não roda em container: o Sunshine precisa da sessão gráfica, da GPU e de criar
controles virtuais (`/dev/uinput`, `/dev/uhid`), e usa várias portas UDP; o ES-DE e o RetroArch rodam na
tela do usuário de jogos.

## Perguntas da instalação

| Pergunta | Padrão |
|---|---|
| Nome do usuário de jogos | `ristar` |
| Entrar sozinho com o usuário de jogos no boot, sem bloqueio de tela? | `S` |
| Endereço do Sunshine no Caddy | `sunshine.<nome-da-máquina>.<domínio do caddy>` |
| Onde está a pasta de mídias do ES-DE? | (sem padrão: navegar pelos discos) |
| Onde estão as ROMs? (uma ou mais pastas) | (sem padrão: navegar pelos discos) |
| Guardar o RetroArch e o ES-DE todas as noites? | `S` |
| Pasta do backup do RetroArch e do ES-DE | `Arcade` ao lado da pasta do backup das configurações do rclone (ex.: `<disco>/proton/Astro/Arcade`), ou `<primeiro disco privado>/Astro/Arcade` |
| Restaurar o RetroArch/ES-DE do backup em `<pasta>`? | `S` (só com a configuração local vazia e o backup com arquivos) |
| Carregar uma configuração existente do RetroArch? | `N` (só com a configuração local vazia, sem backup ou recusando-o) |
| Carregar uma configuração existente do ES-DE? | `N` (só com a configuração local vazia, sem backup ou recusando-o) |

O usuário de jogos não pode ser o mesmo da instalação, um usuário do sistema nem ter `sudo`. Se o `.env`
salvo aponta para um usuário que não existe mais (ex.: renomeado), a instalação pergunta tudo de novo, em vez
de criá-lo. As pastas são escolhidas navegando pelos discos da máquina (os compartilhados primeiro), com a
opção de digitar um caminho; as de mídias e ROMs precisam ser legíveis pelo usuário de jogos (discos
compartilhados).

## O que a instalação faz

- **Driver da NVIDIA:** se houver uma placa NVIDIA sem o driver proprietário, atualiza o kernel e instala o
  `akmod-nvidia` e o `xorg-x11-drv-nvidia-cuda` do RPM Fusion (Fedora), compilando o módulo para o kernel mais
  recente ou usa o `ubuntu-drivers` (Ubuntu). Com o Secure Boot
  ligado, gera a chave que assina o módulo e pede uma senha temporária para cadastrá-la. No boot seguinte,
  na tela azul do MOK: Enroll MOK → Continue → Yes → senha → Reboot.
- **Codificação pela Intel:** no Fedora, troca o `libva-intel-media-driver` (sem H.264/HEVC) pelo
  `intel-media-driver` do RPM Fusion, para o Sunshine codificar pela placa integrada quando a tela estiver nela.
- **Usuário de jogos:** cria o usuário sem `sudo` e pula a tela de boas-vindas do GNOME. A Central de Programas
  dele fica sem downloads automáticos: ele não pode instalar atualizações, e os downloads disputavam a internet
  com o stream.
- **Configuração no `~/.astro` do usuário de jogos:** tudo fica em `~<usuário de jogos>/.astro/arcade`, e os
  lugares que os programas esperam viram atalhos para lá:

  | Pasta | Atalho |
  |---|---|
  | `sunshine/` (painel, aparelhos pareados, apps) | `~/.config/sunshine` |
  | `es-de/` (settings, gamelists, custom_systems, temas) | `~/ES-DE` |
  | `retroarch/` (`retroarch.cfg`, núcleos, saves, states, BIOS) | `~/.var/app/org.libretro.RetroArch/config/retroarch` |

  Num usuário que já existia, uma pasta real num desses lugares é movida para lá (sem perder os pareamentos).
  As respostas da instalação ficam no `~/.astro/arcade` de quem instala. Uma ACL dá a quem instala só leitura no
  `~/.astro` do usuário de jogos, para o backup das configurações.
- **Senha do usuário de jogos:** pedida na instalação (com `chpasswd`, pela entrada padrão). Se ele já tiver
  senha, pergunta se mantém. Ela serve para entrar na tela, trocar de usuário e desbloquear.
- **Tela do usuário de jogos:** desativa o escurecimento e a suspensão. Com login automático, desativa também o
  bloqueio automático (`lock-enabled false`, `idle-delay 0`); sem ele, a tela bloqueia depois de 5 minutos
  parada. Em nenhum caso o bloqueio manual e a troca de usuário são proibidos (`disable-lock-screen false`).
- **Discos de jogos:** não são do arcade. Ficam em "Discos da máquina" como compartilhados: todos os usuários
  acessam, eles aparecem no Arquivos e montam antes de qualquer login, inclusive o automático.
- **Login automático (opcional):** configura o GDM (`custom.conf`) para entrar com o usuário de jogos. Com a
  resposta **N**, tira o login automático dele, e o Sunshine só começa depois que alguém entra com ele na tela.
  Com login automático e senha, o chaveiro do GNOME não é destravado no boot: programas que guardam senhas
  nele (ex.: navegador) pedem a senha do usuário na primeira vez.
- **NVIDIA como placa principal:** com o driver proprietário, uma regra do udev
  (`61-astro-mutter-primary-gpu.rules`, tag `mutter-device-preferred-primary`) faz o GNOME desenhar a tela
  e rodar os aplicativos na NVIDIA, sem copiar cada quadro da Intel. O GNOME escolhe a placa principal assim
  que começa, e no boot a NVIDIA aparece alguns segundos depois da Intel: por isso o GDM espera por ela
  (`gdm.service.d/astro-nvidia.conf`, `udevadm wait` de até 30s no `/dev/dri/by-path/pci-<placa>-card`). Se ela
  não aparecer, o GDM sobe mesmo assim.
- **Sunshine:** baixa o pacote `.rpm` ou `.deb` da versão mais recente em
  [github.com/LizardByte/Sunshine/releases](https://github.com/LizardByte/Sunshine/releases), confere o
  SHA-256 publicado pelo GitHub e instala. Se a versão instalada já for a mais recente, não baixa nada.
  Rodar a instalação de novo atualiza o Sunshine.
- Dá ao binário as permissões `cap_sys_admin`, necessária para capturar a tela pelo KMS, e `cap_sys_nice`,
  para o Sunshine ter prioridade alta na placa de vídeo enquanto o jogo também a usa. Elas são refeitas a cada
  instalação, porque uma atualização do pacote as apaga.
- **Tela no HDMI:** confere se há uma tela ligada na saída da NVIDIA (TV, monitor ou plugue HDMI
  fantasma). Se não houver, avisa: o stream sai pela Intel, sem NVENC, e só com a tampa aberta.
- **Captura pelo KMS:** grava `capture = kms` no `sunshine.conf`. Sem isso, o Sunshine também tenta o portal
  do GNOME ao iniciar, que abre uma janela de permissão na tela e o deixa parado (sem painel) até alguém
  responder.
- **Painel pelo Caddy:** inclui `https://<endereço do Sunshine no Caddy>` em `csrf_allowed_origins`. Sem isso, o
  Sunshine recusa qualquer alteração feita pelo painel (inclusive criar a senha) com "CSRF Protection Error".
- **Som no HDMI:** grava `/etc/wireplumber/wireplumber.conf.d/51-astro-hdmi.conf`, que dá às saídas HDMI
  (`alsa_output.*.hdmi-*`) prioridade maior que a do alto-falante. Com algo plugado no HDMI (TV, monitor ou plugue
  fantasma), o som sai por ele; sem nada, sai pelo notebook. Vale para todos os usuários. Uma saída escolhida à mão
  nas Configurações do GNOME passa por cima da prioridade. Durante o stream, o som vai para a saída virtual do
  Sunshine e não é afetado. Numa instalação antiga, apaga o serviço `astro-arcade-speakers` (que deixava os
  alto-falantes mudos) e, com a sessão do usuário de jogos ativa, tira o mudo das saídas internas e a saída padrão
  escolhida à mão (`scripts/audio.py`, com o `wpctl`).
- **Apps no Moonlight:** o `apps.json` do Sunshine fica com **Desktop** e **ES-DE** (`/usr/local/bin/es-de`,
  `auto-detach`). Os apps de fábrica que não servem aqui ("Low Res Desktop", com `xrandr`, e "Steam Big Picture")
  saem; um app criado pelo painel é mantido. A capa do ES-DE é `~/.config/sunshine/covers/es-de.png` do usuário de
  jogos (PNG em pé, 2:3), usada se existir; ela entra no backup das configurações com a pasta do Sunshine.
- **Resolução de cada aparelho:** instala `scripts/display.py` em `/usr/local/bin/astro-sunshine-display` e
  o registra como comando global de preparo (`global_prep_cmd`) no `sunshine.conf` do usuário de jogos. No início
  de cada stream ele também cria `/tmp/astro-sunshine-stream`, apagado no fim: com ele, o rclone não sincroniza
  com a nuvem durante o jogo.
  Se o usuário já tiver um `global_prep_cmd` próprio, não mexe e avisa.
- **RetroArch:** instala o Flatpak `org.libretro.RetroArch` do Flathub para o sistema todo (o pacote do
  Fedora traz poucos núcleos), adicionando ou ativando o repositório Flathub se ele faltar ou vier desativado. Precisa do `flatpak`.
  Com placa NVIDIA, instala no Flatpak o driver GL da mesma versão do driver da máquina
  (`org.freedesktop.Platform.GL.nvidia-<versão>`) e tira os antigos: sem ele, o RetroArch não usa a NVIDIA.
  Isso é refeito na instalação e na ação "Atualizar ES-DE, RetroArch e núcleos". Depois de uma atualização do
  driver (pela atualização do sistema), rode uma delas.
- **ES-DE:** baixa o `ES-DE_x64.AppImage` da versão mais recente pela API do GitLab do projeto, confere o
  SHA-256 publicado lá e instala em `/usr/local/bin/es-de`, com o atalho e o ícone no menu de aplicativos. De
  dentro do AppImage, guarda em `/usr/local/share/astro-arcade/es_systems.xml` a lista de sistemas da versão
  instalada. O runtime do AppImage usa o `fusermount3` (pacote `fuse3`), sem a `libfuse` 2. Rodar a instalação
  de novo (ou a ação "Atualizar") atualiza o ES-DE.
- **Configurações existentes:** com a pasta local vazia, oferece carregar uma configuração do RetroArch, uma do
  ES-DE e as gamelists. A cópia (`tar`, com `sudo`) junta o conteúdo da pasta escolhida ao da local e passa tudo
  para o usuário de jogos. Do RetroArch, pula os `.dll` e `.exe` do Windows; do ES-DE, os `logs`. Escolher a
  pasta do ES-DE do Windows (a que tem o `ES-DE.exe`) funciona: a instalação usa a `ES-DE/` de dentro dela.
- **`retroarch.cfg`:** sem arquivo, cria um só com `video_fullscreen = "true"` (o resto vem do padrão do
  RetroArch). Com um vindo do Windows, apaga as linhas com caminhos do Windows (`:\saves`, `C:\...`) e drivers
  do Windows (`wasapi`, `xinput`, `dinput`, `winmm`, `d3d*`...), que voltam ao padrão do Linux.
- **`es_settings.xml`:** grava `ROMDirectory` (a primeira pasta de ROMs) e `MediaDirectory` e apaga outras
  opções com caminhos do Windows. O resto fica como está.
- **Várias pastas de ROMs:** o ES-DE tem uma pasta de ROMs só. Os sistemas das outras pastas ganham um bloco em
  `es-de/custom_systems/es_systems.xml`, copiado da lista da versão instalada com o `<path>` trocado pelo
  caminho absoluto. Os blocos gerados ficam listados em `custom_systems/.astro-sistemas` e são refeitos a cada
  instalação e atualização (acompanham a versão do ES-DE); blocos escritos à mão são mantidos. Um sistema em
  duas pastas fica na primeira, com um aviso; pastas que não são sistemas do ES-DE são listadas.
- **Núcleos do RetroArch:** para cada sistema com ROMs, baixa o núcleo padrão do ES-DE do buildbot da
  libretro (a mesma fonte do atualizador do RetroArch, sem checksum publicado) em `retroarch/cores`. Só baixa o
  que falta; a ação "Atualizar" baixa todos de novo. Lista os sistemas sem núcleo do RetroArch por padrão (ex.:
  switch, que usa emulador próprio).
- Habilita o serviço de usuário do Sunshine para o usuário de jogos: ele sobe com a sessão gráfica dele,
  aberta pelo login automático no boot ou quando alguém entra com ele na tela.
- Libera no firewall as portas do Moonlight: TCP `47984`, `47989` e `48010`, UDP `47998-48000`, `48002` e
  `48010`.
- Bloqueia a porta `47990` (painel) para a rede local: o acesso passa só pelo Caddy, em
  `https://sunshine.<nome-da-máquina>.<domínio>`. O painel usa um certificado autoassinado, então a rota usa o destino
  `https+insecure://`.

## Tela

A configuração padrão considera o notebook **com a tampa fechada e uma tela externa na porta HDMI**, que
sai pela NVIDIA. Com a tampa fechada, o GNOME desliga a tela interna (que é da Intel) e a tela externa
vira a única. Uma TV ou um plugue HDMI fantasma servem igualmente; trocar um pelo outro não exige
reinstalar, porque a porta é a mesma.

O codificador não é fixado: a cada stream, o Sunshine testa os codificadores (NVENC primeiro) e usa o
primeiro que funcionar com a tela do momento. Com a tela no HDMI, é o NVENC; sem ela e com a tampa
aberta, o da Intel. O log do Sunshine mostra o escolhido (`Found H.264 encoder: h264_nvenc`).

## Resolução

Quando um aparelho abre um stream, o Sunshine passa a resolução e a taxa de quadros pedidas
(`SUNSHINE_CLIENT_WIDTH`, `SUNSHINE_CLIENT_HEIGHT`, `SUNSHINE_CLIENT_FPS`) para o
`astro-sunshine-display do`, que troca a tela para esse modo pelo `org.gnome.Mutter.DisplayConfig`. Ao
fechar o aplicativo no Moonlight, o `undo` volta à resolução original.

- Só troca se a tela anunciar a resolução exata; a taxa escolhida é a mais próxima da pedida. Se não
  houver, a tela fica como está e o Sunshine redimensiona o vídeo.
- Só age com um único monitor ativo (ex.: tampa fechada e tela no HDMI).
- A troca é temporária: o GNOME a desfaz no próximo login ou ao trocar o cabo, sem gravar no perfil de
  telas.
- Nunca falha: um erro vai para o log do Sunshine e o stream segue sem ajuste.

Para conferir em qual placa está a tela ligada:

```bash
grep -H . /sys/class/drm/card*-*/status
```

O endereço padrão leva o nome da máquina para permitir mais de um Sunshine na rede. Por ter dois níveis
abaixo do domínio, ele não é coberto pelo certificado curinga `*.<domínio>`: o Caddy emite um certificado
próprio para ele, também pelo DNS da Cloudflare.

## Depois de instalar

Reinicie a máquina. O login automático, o driver da NVIDIA e o Sunshine só entram em ação no boot. Sem login
automático, entre com o usuário de jogos na tela para o Sunshine começar.
No primeiro acesso ao painel, o Sunshine pede para criar o usuário e a senha de administração.
O ES-DE fica no menu de aplicativos do usuário de jogos e abre o RetroArch sozinho para cada jogo.

## Ações

| Ação | O que faz |
|---|---|
| Carregar uma configuração do RetroArch | Copia o backup (se houver) ou outra pasta de configuração para a local (sem `.dll`/`.exe`) e limpa o `retroarch.cfg` |
| Carregar uma configuração do ES-DE | Copia o backup (se houver) ou outra pasta de dados do ES-DE e regrava as pastas de ROMs e mídias |
| Trocar as pastas de ROMs e de mídias | Pergunta as pastas de novo, refaz o `custom_systems` e baixa os núcleos que faltarem |
| Atualizar ES-DE, RetroArch e núcleos | Instala o ES-DE mais recente, atualiza o Flatpak (com o driver GL da NVIDIA igual ao da máquina) e baixa todos os núcleos de novo |
| Backup: Arcade ➡️ local (agora) | Copia na hora o RetroArch e o ES-DE para a pasta de backup (só com o backup ligado). No Discord: `/astro command:backup:arcade` |

## Backup

No backup das configurações (rclone, criptografado) entram só o Sunshine (`sunshine/`, sem os logs), o
`retroarch.cfg` e o `es_settings.xml` do usuário de jogos. Na restauração, o Sunshine é parado, os arquivos voltam
com o dono certo (`sudo`) e ele sobe de novo.

O resto vai para a **pasta do backup do RetroArch e do ES-DE** (`ARCADE_BACKUP`), uma cópia comum, sem
criptografia, feita pelo comando `backup` do projeto, que o rclone chama à 01:00 (e no "Fazer backup agora" e no
"Implodir Astro"). É um `rclone sync` incremental de `~<usuário de jogos>/.astro/arcade`, lido pela ACL, sem `sudo`:

| Pasta | O que entra |
|---|---|
| `retroarch/` | `retroarch.cfg`, `saves/`, `states/`, `system/` (BIOS), `config/` (overrides e remaps), `playlists/`, `screenshots/`, `records/` |
| `es-de/` | `settings/`, `collections/`, `gamelists/`, `themes/` |

Núcleos, assets, shaders, `custom_systems` e logs ficam de fora: o Astro e os programas os refazem. Dentro da
pasta da nuvem, a cópia segue para ela e para o disco de backup nas rodadas das 03:00 (com as versões delas). Uma
falha (disco desmontado, rclone ausente) marca o backup das configurações como falho, e o "Implodir Astro" não
continua.

Na instalação, com a configuração local vazia e o backup com arquivos, o assistente oferece restaurar dele. As
ações "Carregar uma configuração do RetroArch/ES-DE" também oferecem o backup primeiro.

## Troca de domínio

`project.sh domain <antigo> <novo>` (chamado pelo "Trocar o domínio" do assistente) troca o endereço do painel em
`csrf_allowed_origins`, reinicia o Sunshine (um stream em andamento cai) e republica a rota no Caddy, sem
reinstalar o resto.

## Remoção

`remove` desativa o login automático, encerra a sessão do usuário de jogos e **apaga o usuário com a home inteira**
(`userdel -r`: Sunshine, ES-DE, RetroArch, saves, states, BIOS e núcleos). Também apaga o ES-DE (programa e atalho),
o `astro-sunshine-display` e a regra de som no HDMI, tira o `setcap` do Sunshine, devolve à Intel o papel de
placa principal, tira a espera do GDM, as portas de stream e o bloqueio do painel no firewall e a rota do Caddy,
e apaga `~/.astro/arcade`. O pacote do Sunshine, o RetroArch (Flatpak), o driver da NVIDIA e os discos (são da
máquina) ficam.
