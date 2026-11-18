# Migração astro → astroverso (rodar no servidor real)

Arquivo temporário: depois de concluir todos os passos e confirmar que tudo funciona, apague
este arquivo e comite a remoção. Ele só existe para levar o contexto desta mudança para a
sessão do Claude que roda no servidor real (`rigel`), onde há acesso a `sudo`, systemd,
containers e Cloudflare de verdade — o que não existe na sessão que fez o refactoring do código.

## O que já mudou no código (comitado e no GitHub)

O repositório (agora `astroverso-homelab`) deixou de ser "o astro" e passou a ser o módulo
homelab da suíte **Astroverso**. O codinome técnico mudou de `astro` para `astroverso` em tudo
que identifica o módulo como sistema:

- comando do assistente: `astro` → `astroverso`
- pasta de estado: `~/.astro` → `~/.astroverso`
- rede do compose: `astro_default` → `astroverso_default`
- containers e imagens: `astro-<serviço>` → `astroverso-<serviço>`
- variáveis de ambiente: `ASTRO_*` → `ASTROVERSO_*`
- unidades systemd e seus drop-ins: prefixo `astro-`/`astro.` → `astroverso-`
- marcas no `/etc/fstab`, `/etc/crypttab` (`# astro <uuid> <tipo>`) e no `/etc/samba/smb.conf`
  (`# astro samba: inicio/fim`) → `# astroverso ...`
- sufixo de backup `.astro-bak` → `.astroverso-bak`
- rótulos de menu: "Instalar/Reinstalar/Gerenciar/Implodir Astro" → "...Astroverso"
- Worker e KV do Cloudflare do mailserver: `astro-mailserver` → `astroverso-mailserver`
- cabeçalho informativo `X-Astro-Mailserver` → `X-Astroverso-Mailserver`

**"astro" continua existindo**, só que com outro sentido: é o nome de usuário padrão dos módulos
do Astroverso (ex.: admin padrão do Nextcloud) e o nome/comando do bot do Discord (`/astro`,
autocompletar, `custom_id`, etc.). Isso é proposital, não ficou pela metade.

### O que NÃO foi renomeado, de propósito, e não deve ser renomeado agora

Estes itens são referenciados por **rotinas reais do n8n que vivem só no banco de dados**, fora
deste repositório. Renomear qualquer um deles no código sem editar também o fluxo real no editor
do n8n quebra a automação em produção:

- os IDs de credencial do n8n: `astroImapInbox01`, `astroDiscordBot01`, `astroNextcloud001`,
  `astroAnthropic001`, `astroEnvioEmail01`, `astroHookAstro001`
- o caminho do webhook `astro-contas-email` (`EMAIL_HOOK` em `n8n/project.sh`)
- o cabeçalho `X-Astro-Chave` / `x-astro-chave` (usado tanto para o `N8N_HOOK_TOKEN` quanto para o
  `SEND_KEY` do mailserver)
- o módulo Node `astro-qr` (pasta `n8n/astro-qr`, exigido por `require("astro-qr")` dentro de nós
  Code de fluxos reais)

Se um dia quiser renomear isso também, é uma tarefa separada e deliberada: precisa abrir cada
fluxo afetado no editor do n8n e editar manualmente, porque eles não estão versionados aqui.

## O problema a resolver aqui

O código já está renomeado e no GitHub. A instalação **real** deste servidor ainda está toda sob
os nomes antigos (`~/.astro`, containers `astro-*`, unidades systemd, marcas no fstab/crypttab/
samba, Worker/KV do Cloudflare). Depois do `git pull`, o código passa a esperar os nomes novos,
então é preciso migrar o que está rodando — sem perder segredos nem dados.

## Passo a passo

0. **Segurança antes de tudo**
   - `git status` no repositório: confirme que não há trabalho local não comitado que o `pull`
     possa atropelar.
   - Com o código **atual** (antes do `pull`), rode um backup das configurações agora
     (Administração → "Fazer backup agora" ou equivalente).
   - Rode "Buscar os e-mails agora" do mailserver (fetch force), para esvaziar a fila que está no
     KV da Cloudflare antes de ele ser recriado com outro nome mais adiante.

1. **Atualizar o código**: `cd` no repositório e `git pull`.

2. **Mover o estado**: `mv ~/.astro ~/.astroverso` (mover, nunca copiar nem apagar o antigo antes
   de confirmar — isso preserva todos os `.env`, as marcas de `~/.astro/.concluidas` e os dados de
   cada projeto).

3. **Comando do assistente**: `rm -f ~/.local/bin/astro` e depois
   `ln -sfn <repo>/setup.sh ~/.local/bin/astroverso` (ou rode o assistente uma vez pelo caminho
   completo, `bash <repo>/setup.sh`, que recria o link sozinho).

4. **Marcas em arquivos do sistema** (fazer ANTES de rodar "Discos da máquina" ou reinstalar o
   samba, senão o assistente pode achar que nada está configurado e duplicar entradas):
   - Backup manual primeiro: `sudo cp -a /etc/fstab /etc/fstab.manual-bak` e
     `sudo cp -a /etc/crypttab /etc/crypttab.manual-bak`.
   - Trocar **só o texto do comentário** `# astro ` por `# astroverso ` no início das linhas de
     marca em `/etc/fstab` e `/etc/crypttab` (não tocar na linha de montagem/criptografia que vem
     depois da marca). Revisar o diff antes de salvar.
   - `sudo cp -a /etc/samba/smb.conf /etc/samba/smb.conf.manual-bak`, depois trocar
     `# astro samba: inicio` / `# astro samba: fim` por `# astroverso samba: inicio` /
     `# astroverso samba: fim`. Rodar `testparm` para confirmar que continua válido.

5. **Parar e remover o que é antigo**, para o reinstalar não deixar duplicado:
   - Containers de cada projeto (`podman stop` e `podman rm` em cada um): `astro-adguard`,
     `astro-caddy`, `astro-discord`, `astro-mailserver`, `astro-n8n`, `astro-n8n-runners`,
     `astro-nextcloud`, `astro-nextcloud-cron`, `astro-nextcloud-redis`, `astro-nextcloud-db`.
   - Unidades de usuário antigas: `systemctl --user disable --now` em todas as `astro-*.service`/
     `.timer`/`.path` (disco, discord runner, rclone tick/local/config, mailserver fetch, sunshine
     lock/awake), depois `rm -f ~/.config/systemd/user/astro-*` e `systemctl --user daemon-reload`.
   - Unidades e drop-ins de sistema antigos (precisa de terminal normal, com `sudo`):
     `astro-dns-check.service`, `/etc/sysctl.d/99-astro.conf`,
     `/etc/sysctl.d/99-astro-tailscale.conf`, `/etc/ssh/sshd_config.d/10-astro.conf`,
     `/etc/systemd/logind.conf.d/99-astro.conf`, `/etc/dconf/db/gdm.d/95-astro-power`,
     `/etc/NetworkManager/dispatcher.d/90-astro-dns-check`,
     `/etc/systemd/resolved.conf.d/99-astro-adguard.conf`,
     `/etc/systemd/system/gdm.service.d/astro-nvidia.conf`. O código novo recria os equivalentes
     `astroverso-*` sozinho quando cada etapa rodar de novo — aqui é só apagar o antigo.
   - Rede: `podman network rm astro_default` depois que os containers acima já saíram.

6. **Cloudflare (mailserver)**: o Worker e o KV `astro-mailserver` ficam órfãos depois do passo 7
   (o reinstall cria `astroverso-mailserver` novo e reaponta o Email Routing). Confirme que o novo
   está recebendo e-mail antes de apagar o Worker e o KV antigos pelo painel da Cloudflare — não
   existe um "renomear", só criar o novo e apagar o velho.

7. **Reinstalar**: no menu, escolher **"Reinstalar Astroverso"** e marcar pelo menos Máquina,
   Discos da máquina e todos os projetos instalados. Em cada um, responder "sim" para "usar a
   configuração já salva?" (os `.env` já foram com o `mv` do passo 2). Isso recria containers,
   imagens, unidades systemd e rotas do Caddy com os nomes novos, com os mesmos segredos de antes.
   Deixe o n8n para o fim dos serviços (ele reimporta as credenciais com os hostnames novos dos
   outros projetos).

8. **Verificar**:
   - `podman ps` só mostra `astroverso-*`, nada `astro-*`.
   - `systemctl --user list-timers` só mostra `astroverso-*`.
   - `/astro` no Discord continua respondendo (esse nome não muda, de propósito).
   - Cada rota do Caddy abre normalmente.
   - `grep astroverso /etc/fstab /etc/crypttab /etc/samba/smb.conf` mostra as marcas novas.
   - `git status` no repositório está limpo.

9. **Não renomear em nenhuma hipótese**, nem pelo editor do n8n: `astro-qr`, os IDs de credencial
   do n8n, o webhook `astro-contas-email`, nem o cabeçalho `X-Astro-Chave`/`x-astro-chave` — ver a
   seção acima.

10. Com tudo confirmado, apague este arquivo e comite a remoção.
