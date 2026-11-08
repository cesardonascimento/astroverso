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
| Endereço do Sunshine no Caddy | `sunshine.<domínio do caddy>` |

O usuário de jogos não pode ser o mesmo da instalação, um usuário do sistema nem ter `sudo`.

## O que a instalação faz

- **Driver da NVIDIA:** se houver uma placa NVIDIA sem o driver proprietário, instala o `akmod-nvidia` e o
  `xorg-x11-drv-nvidia-cuda` do RPM Fusion (Fedora) ou usa o `ubuntu-drivers` (Ubuntu). Com o Secure Boot
  ligado, gera a chave que assina o módulo e pede uma senha temporária para cadastrá-la. No boot seguinte,
  na tela azul do MOK: Enroll MOK → Continue → Yes → senha → Reboot.
- **Usuário de jogos:** cria o usuário sem senha e sem `sudo`, pula a tela de boas-vindas do GNOME e
  desativa o bloqueio de tela, o escurecimento e a suspensão para ele.
- **Login automático:** configura o GDM (`custom.conf`) para entrar com o usuário de jogos.
- **Sunshine:** baixa o pacote `.rpm` ou `.deb` da versão mais recente em
  [github.com/LizardByte/Sunshine/releases](https://github.com/LizardByte/Sunshine/releases), confere o
  SHA-256 publicado pelo GitHub e instala. Se a versão instalada já for a mais recente, não baixa nada.
  Rodar a instalação de novo atualiza o Sunshine.
- Dá ao binário a permissão `cap_sys_admin`, necessária para capturar a tela pelo KMS. Ela é refeita a
  cada instalação, porque uma atualização do pacote a apaga.
- Habilita o serviço de usuário do Sunshine para o usuário de jogos: ele sobe com a sessão gráfica,
  aberta pelo login automático no boot.
- Libera no firewall as portas do Moonlight: TCP `47984`, `47989` e `48010`, UDP `47998-48000`, `48002` e
  `48010`.
- Bloqueia a porta `47990` (painel) para a rede local: o acesso passa só pelo Caddy, em
  `https://sunshine.<domínio>`. O painel usa um certificado autoassinado, então a rota usa o destino
  `https+insecure://`.

## Depois de instalar

Reinicie a máquina. O login automático, o driver da NVIDIA e o Sunshine só entram em ação no boot.
No primeiro acesso ao painel, o Sunshine pede para criar o usuário e a senha de administração.

## Remoção

`remove` desativa o serviço e o login automático e tira a rota do Caddy. O pacote do Sunshine, o driver
da NVIDIA e o usuário de jogos (com os jogos e os emuladores) são mantidos. `--purge` apaga também
`~/.config/sunshine` do usuário de jogos.
