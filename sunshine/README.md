# sunshine

Acesso remoto à tela da máquina: o [Sunshine](https://github.com/LizardByte/Sunshine) transmite a área de
trabalho do usuário que instala para o [Moonlight](https://moonlight-stream.org), com imagem, som, teclado,
mouse e controles.

```bash
./project.sh install           # instala, configura e publica o painel do Sunshine no Caddy
./project.sh remove           # desfaz tudo o que o projeto criou (usado pelo Implodir Astro)
```

Como o cockpit, não roda em container: o Sunshine precisa da sessão gráfica, da GPU e de criar controles
virtuais (`/dev/uinput`, `/dev/uhid`), e usa várias portas UDP.

## Perguntas da instalação

| Pergunta | Padrão |
|---|---|
| Endereço do Sunshine no Caddy | `sunshine.<nome-da-máquina>.<domínio do caddy>` |

## O que a instalação faz

- **Driver da NVIDIA:** se houver uma placa NVIDIA sem o driver proprietário, atualiza o kernel e instala o
  `akmod-nvidia` e o `xorg-x11-drv-nvidia-cuda` do RPM Fusion (Fedora), compilando o módulo para o kernel mais
  recente, ou usa o `ubuntu-drivers` (Ubuntu). Com o Secure Boot ligado, gera a chave que assina o módulo e pede
  uma senha temporária para cadastrá-la. No boot seguinte, na tela azul do MOK: Enroll MOK → Continue → Yes →
  senha → Reboot.
- **Codificação pela Intel:** no Fedora, troca o `libva-intel-media-driver` (sem H.264/HEVC) pelo
  `intel-media-driver` do RPM Fusion, para o Sunshine codificar pela placa integrada quando a tela estiver nela.
- **NVIDIA como placa principal:** com o driver proprietário, uma regra do udev
  (`61-astro-mutter-primary-gpu.rules`, tag `mutter-device-preferred-primary`) faz o GNOME desenhar a tela
  e rodar os aplicativos na NVIDIA, sem copiar cada quadro da Intel. O GNOME escolhe a placa principal assim
  que começa, e no boot a NVIDIA aparece alguns segundos depois da Intel: por isso o GDM espera por ela
  (`gdm.service.d/astro-nvidia.conf`, `udevadm wait` de até 30s no `/dev/dri/by-path/pci-<placa>-card`). Se ela
  não aparecer, o GDM sobe mesmo assim.
- **Login automático com a tela bloqueada:** configura o GDM (`custom.conf`) para entrar com o usuário que
  instala no boot, e o serviço de usuário `astro-sunshine-lock` (com a `graphical-session.target`) bloqueia a
  sessão logo depois: `loginctl lock-session` na sessão gráfica, repetido a cada 2s até o GNOME confirmar
  (`LockedHint`), por até 1 minuto. O início automático do GNOME (`~/.config/autostart`) não serve: no GNOME 50, o
  comando roda antes de o GNOME conseguir bloquear. O Sunshine sobe com a sessão e transmite a tela de
  bloqueio; quem conecta destrava com a senha. A tela bloqueia de novo depois de 5 minutos parada
  (`idle-delay 300`, `lock-delay 0`, sem escurecer antes). Com o login automático, o chaveiro do GNOME não é
  destravado no boot.
- **Sunshine:** baixa o pacote `.rpm` ou `.deb` da versão mais recente em
  [github.com/LizardByte/Sunshine/releases](https://github.com/LizardByte/Sunshine/releases), confere o
  SHA-256 publicado pelo GitHub e instala. Se a versão instalada já for a mais recente, não baixa nada.
  Rodar a instalação de novo atualiza o Sunshine.
- Dá ao binário as permissões `cap_sys_admin`, necessária para capturar a tela pelo KMS, e `cap_sys_nice`,
  para o Sunshine ter prioridade alta na placa de vídeo. Elas são refeitas a cada instalação, porque uma
  atualização do pacote as apaga.
- **Tela no HDMI:** confere se há uma tela ligada na saída da NVIDIA (monitor ou plugue HDMI fantasma). Se não
  houver, avisa: o stream sai pela Intel, sem NVENC, e só com a tampa aberta.
- **Configuração em `~/.astro/sunshine/config`:** com `~/.config/sunshine` como atalho para lá. Uma pasta real
  em `~/.config/sunshine` é movida (sem perder os pareamentos). Assim ela entra no backup das configurações, sem
  os logs.
- **Captura pelo KMS:** grava `capture = kms` no `sunshine.conf`. Sem isso, o Sunshine também tenta o portal
  do GNOME ao iniciar, que abre uma janela de permissão na tela e o deixa parado (sem painel) até alguém
  responder.
- **Painel pelo Caddy:** inclui `https://<endereço do Sunshine no Caddy>` em `csrf_allowed_origins`. Sem isso, o
  Sunshine recusa qualquer alteração feita pelo painel (inclusive criar a senha) com "CSRF Protection Error".
- **Apps no Moonlight:** o `apps.json` fica com **Desktop** (`scripts/apps.py`). Os apps de fábrica que não
  servem aqui ("Low Res Desktop", com `xrandr`, e "Steam Big Picture") saem; um app criado pelo painel é mantido.
- **Resolução de cada aparelho:** instala `scripts/display.py` em `/usr/local/bin/astro-sunshine-display` e
  o registra como comando global de preparo (`global_prep_cmd`) no `sunshine.conf`. No início de cada stream,
  ele troca a tela, pelo DBus do Mutter, para a resolução exata do aparelho (se a tela aceitar) e volta no fim.
  Se o `sunshine.conf` já tiver um `global_prep_cmd` próprio, não mexe e avisa.
- Habilita o serviço de usuário do Sunshine: ele sobe com a sessão gráfica, aberta pelo login automático.
- Libera no firewall as portas do Moonlight: TCP `47984`, `47989` e `48010`, UDP `47998-48000`, `48002` e
  `48010`.
- Bloqueia a porta `47990` (painel) para a rede local: o acesso passa só pelo Caddy, em
  `https://sunshine.<nome-da-máquina>.<domínio>`. O painel usa um certificado autoassinado, então a rota usa o
  destino `https+insecure://host.containers.internal:47990`.

No primeiro acesso ao painel, crie o usuário e a senha do Sunshine. Para parear um aparelho, abra o Moonlight
nele, escolha a máquina e digite no painel (PIN) o código que o Moonlight mostra.

## Remoção

Desliga o login automático e o serviço de bloqueio no login, desabilita o serviço do Sunshine, tira o `setcap`, o ajuste de
resolução, a regra da placa principal e a espera do GDM, fecha as portas, tira a rota do Caddy e apaga
`~/.astro/sunshine` com o atalho `~/.config/sunshine`. Ficam o pacote do Sunshine e o driver da NVIDIA.

## Arquivos

| Caminho | O que é |
|---|---|
| `~/.astro/sunshine/.env` | `SUNSHINE_HOST` |
| `~/.astro/sunshine/config/` | configuração do Sunshine (`sunshine.conf`, `apps.json`, pareamentos, credenciais) |
| `~/.astro/sunshine/.proxy` | rota do painel no Caddy |
| `~/.config/systemd/user/astro-sunshine-lock.service` | bloqueio da tela logo depois do login automático |
| `/usr/local/bin/astro-sunshine-display` | troca de resolução durante o stream |
| `/etc/udev/rules.d/61-astro-mutter-primary-gpu.rules` | NVIDIA como placa principal do GNOME |
| `/etc/systemd/system/gdm.service.d/astro-nvidia.conf` | GDM espera a NVIDIA no boot |
