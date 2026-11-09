# sunshine

Servidor de streaming de jogos para o [Moonlight](https://moonlight-stream.org). Transmite a tela, o
áudio e recebe os controles de um usuário próprio para jogos, que entra sozinho no boot. O usuário do
homelab continua cuidando dos containers em segundo plano.

```bash
./project.sh install           # instala, configura e publica o painel no Caddy
./project.sh remove [--purge]  # desativa; --purge apaga também as credenciais e os pareamentos
```

Como o cockpit, não roda em container: o Sunshine precisa da sessão gráfica, da GPU e de criar
controles virtuais (`/dev/uinput`, `/dev/uhid`), e usa várias portas UDP.

## Perguntas da instalação

| Pergunta | Padrão |
|---|---|
| Nome do usuário de jogos | `jogos` |
| Entrar sozinho com o usuário de jogos no boot, sem bloqueio de tela? | `S` |
| Endereço do Sunshine no Caddy | `sunshine.<nome-da-máquina>.<domínio do caddy>` |
| Quais discos são de jogos? | (nenhum marcado) |

O usuário de jogos não pode ser o mesmo da instalação, um usuário do sistema nem ter `sudo`.

## O que a instalação faz

- **Driver da NVIDIA:** se houver uma placa NVIDIA sem o driver proprietário, atualiza o kernel e instala o
  `akmod-nvidia` e o `xorg-x11-drv-nvidia-cuda` do RPM Fusion (Fedora), compilando o módulo para o kernel mais
  recente ou usa o `ubuntu-drivers` (Ubuntu). Com o Secure Boot
  ligado, gera a chave que assina o módulo e pede uma senha temporária para cadastrá-la. No boot seguinte,
  na tela azul do MOK: Enroll MOK → Continue → Yes → senha → Reboot.
- **Codificação pela Intel:** no Fedora, troca o `libva-intel-media-driver` (sem H.264/HEVC) pelo
  `intel-media-driver` do RPM Fusion, para o Sunshine codificar pela placa integrada quando a tela estiver nela.
- **Usuário de jogos:** cria o usuário sem `sudo` e pula a tela de boas-vindas do GNOME.
- **Configuração no `~/.astro` do usuário de jogos:** o Sunshine guarda a configuração (painel, aparelhos
  pareados, apps) em `~<usuário de jogos>/.astro/sunshine`, e `~/.config/sunshine` vira um atalho para lá
  (uma configuração antiga é movida, sem perder os pareamentos). As respostas da instalação ficam no
  `~/.astro/sunshine` de quem instala. Uma ACL dá a quem instala só leitura no `~/.astro` do usuário de jogos,
  para o backup das configurações (rclone), onde ela entra como `sunshine/usuario`. Na restauração, o Sunshine
  do usuário de jogos é parado, a pasta volta com o dono certo (`sudo`) e ele sobe de novo.
- **Senha do usuário de jogos:** pedida na instalação (com `chpasswd`, pela entrada padrão). Se ele já tiver
  senha, pergunta se mantém. Ela serve para entrar na tela, trocar de usuário e desbloquear.
- **Tela do usuário de jogos:** desativa o escurecimento e a suspensão. Com login automático, desativa também o
  bloqueio automático (`lock-enabled false`, `idle-delay 0`); sem ele, a tela bloqueia depois de 5 minutos
  parada. Em nenhum caso o bloqueio manual e a troca de usuário são proibidos (`disable-lock-screen false`).
- **Discos de jogos:** cria o grupo `jogos` com o usuário de jogos e monta cada disco escolhido em
  `/srv/<rótulo>` pelo `fstab`, com as regras de `lib/disk.sh` (nada pede senha no boot). NTFS usa o driver do
  kernel (`ntfs3`). Dono `$USER`, grupo `jogos`, `umask=007`: os dois leem e escrevem, os outros usuários não
  entram. A pasta principal de cada disco recebe `chmod 770`, porque o `ntfs3` usa a permissão gravada no disco
  (atributos do WSL) no lugar do `umask`; a permissão fica gravada no disco. O disco aparece no Arquivos (`x-gvfs-show`) e monta antes da sessão do usuário de jogos. Um NTFS
  marcado como sujo (desligado sem fechar no Windows) não monta: a instalação mostra o `ntfsfix` para corrigir.
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
- Dá ao binário a permissão `cap_sys_admin`, necessária para capturar a tela pelo KMS. Ela é refeita a
  cada instalação, porque uma atualização do pacote a apaga.
- **Tela no HDMI:** confere se há uma tela ligada na saída da NVIDIA (TV, monitor ou plugue HDMI
  fantasma). Se não houver, avisa: o stream sai pela Intel, sem NVENC, e só com a tampa aberta.
- **Captura pelo KMS:** grava `capture = kms` no `sunshine.conf`. Sem isso, o Sunshine também tenta o portal
  do GNOME ao iniciar, que abre uma janela de permissão na tela e o deixa parado (sem painel) até alguém
  responder.
- **Painel pelo Caddy:** inclui `https://<endereço do Sunshine no Caddy>` em `csrf_allowed_origins`. Sem isso, o
  Sunshine recusa qualquer alteração feita pelo painel (inclusive criar a senha) com "CSRF Protection Error".
- **Notebook em silêncio:** deixa mudas, para o usuário de jogos, as saídas de som internas (alto-falante e fone;
  HDMI fica de fora) com o `wpctl`; o PipeWire guarda o mudo entre os boots. Durante o stream, o som vai para a
  saída virtual do Sunshine e não é afetado. Precisa da sessão do usuário de jogos aberta.
- **Resolução de cada aparelho:** instala `scripts/display.py` em `/usr/local/bin/astro-sunshine-display` e
  o registra como comando global de preparo (`global_prep_cmd`) no `sunshine.conf` do usuário de jogos.
  Se o usuário já tiver um `global_prep_cmd` próprio, não mexe e avisa.
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

## Remoção

`remove` desativa o serviço, o login automático e a troca de resolução, reativa os alto-falantes, devolve à Intel o
papel de placa principal, libera os discos de jogos (saem do `fstab` e são desmontados) e tira a rota do Caddy. O
pacote do Sunshine, o driver da NVIDIA, o grupo `jogos`, os arquivos dos discos e o usuário de jogos (com os jogos e
os emuladores) são mantidos. `--purge` apaga também
`~/.config/sunshine` do usuário de jogos.
