# nextcloud

Nuvem própria para arquivos, fotos, agenda e contatos, em `https://nextcloud.<domínio>`, pelos apps do Nextcloud no
celular e no computador.

## Containers

| Container | Imagem | Para quê |
|---|---|---|
| `astroverso-nextcloud` | `nextcloud:<versão>-apache` | O Nextcloud (PHP + Apache), na porta 80 só da rede dos containers |
| `astroverso-nextcloud-db` | `postgres:<versão>-alpine` | Banco de dados |
| `astroverso-nextcloud-redis` | `valkey/valkey:<versão>-alpine` | Cache e travas de arquivo, sem gravar nada em disco |
| `astroverso-nextcloud-cron` | a mesma do Nextcloud (`/cron.sh`) | Tarefas em segundo plano a cada 5 minutos |

Versões fixadas em `nextcloud.py`. O Nextcloud só sobe uma versão principal por vez (ex.: da 35 para a 36): ao trocar
a versão no código, suba uma principal por reinstalação. O Nextcloud sobe depois do banco e do cache (`Requires` do
systemd), e o cron depois do Nextcloud.

## O que a instalação faz

| Pergunta | Padrão |
|---|---|
| Endereço do Nextcloud | `nextcloud.<domínio>` |
| Usuário administrador (só na primeira vez) | `astroverso` |
| Senha do administrador (só na primeira vez) | sem padrão; se o Nextcloud recusar (curta, comum ou vazada), pede de novo |
| Pasta dos arquivos (só na primeira vez) | `~/Nextcloud`; vazia ou a de um Nextcloud anterior. Escolhida pelo seletor de pastas (`kit.folders`): os discos do app `disks` com o espaço livre e a marca ☁ das pastas ligadas a uma nuvem. Para guardar tudo num disco de dados, escolha uma pasta nele (ex.: `/srv/<disco>/nextcloud`) |

1. Gera a senha do banco e uma senha inicial do administrador em `~/.astroverso/nextcloud/secrets/`, lidas pelos
   containers por arquivo (`*_FILE`): nunca vão para o `.env` nem para argumentos de comando.
2. Prepara a pasta dos arquivos para o `www-data` do container (`podman unshare chown 33:33`, `770`).
3. Sobe os containers. Na primeira vez, a imagem instala o Nextcloud sozinha (alguns minutos) com a senha inicial,
   trocada em seguida pela digitada (`occ user:resetpassword --password-from-env`, senha por variável de ambiente).
4. Ajusta pelo `occ`, a cada instalação: `trusted_domains`, `trusted_proxies` (a rede dos containers, para ver o IP
   real de quem acessa), `overwriteprotocol https`, `overwrite.cli.url`, fuso e região dos telefones (do fuso da
   máquina), janela de manutenção às 3h no horário local, tarefas pelo cron e contas novas sem arquivos de exemplo.
   Na primeira vez, também confere os índices do banco e repara o que faltar.
5. O `apache.conf` avisa ao Apache que o endereço público é `https://` (sem isso, `/.well-known/caldav` e
   `/.well-known/carddav` redirecionam para `http://`) e liga o HSTS.
6. Publica `nextcloud.<domínio>` pelo `kit.routes` (o Caddy do `network` recarrega sozinho).
7. Pergunta as mudanças no sistema: as contas de e-mail automáticas, a verificação de hora em hora e o
   backup da configuração (enviado pelo app `vault` para a pasta dos backups no Nextcloud).
8. **Contas de e-mail:** para cada caixa publicada por outro app em `~/.astroverso/mailboxes/` (`kit.mailboxes`, ex.: o
   app `mail`), liga o app Mail do Nextcloud (instala se faltar) e cria ou atualiza no Mail do administrador a conta
   `Astroverso <Nome>`. A senha vai por variável de ambiente para um script PHP pela entrada padrão (o `occ` só aceita
   senha como argumento). Contas `Astroverso ...` cujas caixas sumiram são apagadas.

## Os arquivos num disco

Os arquivos ficam **dentro** do Nextcloud (a pasta dos arquivos, `<pasta>/<usuário>/files/...`), não num armazenamento
externo: tudo passa por ele, que vê cada mudança na hora, com lixeira e versões, sem briga de donos e permissões.
Continuam sendo arquivos normais no disco: num outro Linux, com a senha do LUKS e `sudo`, dá para abri-los sem o
Nextcloud.

- Com a pasta num disco do app `disks`, a instalação para se o disco não estiver montado, e a verificação de hora em
  hora avisa quando ele some (o Nextcloud não abre os arquivos, mas não apaga nada).
- **Trazer uma pasta para o Nextcloud** (ação) move uma pasta da máquina (ex.: o conteúdo de um disco) para dentro dos
  arquivos de um usuário: `podman unshare mv` (instantâneo no mesmo disco), dono passado para o `www-data` do container
  e `occ files:scan` só daquela pasta. Depois, ela só é usada pelo Nextcloud.
- Sincronizar uma pasta do Nextcloud com uma nuvem (ex.: Proton Drive) é pelo app `cloud`, com o Nextcloud como conta
  (WebDAV), nunca gravando direto na pasta dos arquivos.

## Mudanças na máquina

| Mudança | Por quê |
|---|---|
| Podman instalado e *linger* ligado para o usuário | Os containers rodam como serviços do usuário e sobem no boot sem ninguém logado |
| 4 containers por Quadlet (tabela acima), na rede `astroverso`, sem porta aberta na máquina | O Nextcloud e o que ele precisa; o Caddy chega no `astroverso-nextcloud` pelo nome |
| `~/.astroverso/nextcloud/` (`html/`, `db/`, `secrets/`, `apache.conf`, `.env`) | O código e a configuração do Nextcloud, o banco, as senhas e as respostas da instalação |
| `~/Nextcloud` (ou a pasta escolhida), do `www-data` do container | Os arquivos de todos os usuários do Nextcloud |
| `~/.astroverso/routes/nextcloud.json` | O endereço publicado para o Caddy |
| Unidades do usuário `astroverso-nextcloud-mailboxes.path` e `.service` (perguntada, padrão sim) | Quando uma caixa de e-mail é publicada ou retirada, a conta no Nextcloud Mail é criada, atualizada ou apagada na hora (`astroverso nextcloud action mailboxes`) |
| Unidades do usuário `astroverso-nextcloud-watch.timer` e `.service` (perguntada, padrão sim, em **Mudanças no sistema**) | A cada hora, confere o Nextcloud e avisa no Discord quando algo quebra e quando volta ao normal |
| Unidades do usuário `astroverso-nextcloud-backup.timer` e `.service` (perguntada, padrão sim) | Backup diário da configuração do app no vault (`kit.vault`), com aviso no `#vault` |

## Fora da máquina (passos seus)

| Passo | Por quê | Como fazer |
|---|---|---|
| Conectar o celular, o computador, a agenda e os contatos | Os apps do Nextcloud e o CalDAV/CardDAV ficam nos aparelhos | [apps.md](docs/apps.md) |

## Ações

| Ação | O que faz |
|---|---|
| Resumo do Nextcloud | Situação, versão, endereço, administrador, pasta e espaço livre, última rodada das tarefas, erros da verificação do Nextcloud (`occ setupchecks`), os containers e os avisos em aberto. Também no Discord: `/astro nextcloud:summary` |
| Mudanças no sistema | Liga ou desliga as contas de e-mail automáticas e a verificação de hora em hora |
| Atualizar as contas de e-mail | Cria, atualiza ou apaga as contas do Nextcloud Mail a partir das caixas publicadas (também no Discord) |
| Trocar a senha do administrador | Pede a nova senha e a aplica (pede de novo se o Nextcloud recusar) |
| Reparar o Nextcloud | Índices do banco, reparos e a reverificação dos arquivos (`occ files:scan --all`), útil depois de copiar arquivos por fora. Também no Discord, com confirmação |
| Verificar agora | Roda a verificação de hora em hora na hora |
| Trazer uma pasta para o Nextcloud | Move uma pasta da máquina para os arquivos de um usuário e a cataloga (veja "Os arquivos num disco") |
| Fazer backup agora / Restaurar uma versão | Backup da configuração na hora (também no Discord) e restauração de uma versão guardada no vault (app `vault`), com uma cópia "antes-da-restauracao" |

## Verificação de hora em hora

Avisa no canal `#nextcloud` do Discord (pelo `kit.discord`) só quando algo muda, com os botões **Resumo do
Nextcloud** e **Verificar de novo**:

| O que confere | Nível |
|---|---|
| Algum container parado | erro |
| Nextcloud em manutenção | aviso |
| Erro na verificação do próprio Nextcloud (`occ setupchecks`) | aviso, um por erro |
| Pasta dos arquivos com menos de 10% livre | aviso |
| Disco da pasta dos arquivos desligado ou travado (`kit.disks`) | erro |

## Backup

O backup da configuração vai, criptografado, para a pasta dos backups no Nextcloud (app `vault`). Os arquivos dos
usuários não entram: ficam protegidos pela fotografia do disco (app `disks`).

- **configuração** (`backup(pasta)` e `restore(pasta)`, pelo `kit.vault`): dump do banco (`pg_dump`, com o Nextcloud
  rodando), `config/`, `custom_apps/`, `themes/` e `version.php` (por `podman unshare tar`, que guarda os donos), o
  `.env` e as senhas.
- **restore:** para os containers, traz a configuração (mantendo o código que a imagem recria), apaga o banco, sobe
  só o Postgres, recria o usuário do banco que o Nextcloud criou na instalação (nome e senha do `config.php`, pela
  entrada padrão) e carrega o dump; depois reinstala com as respostas salvas e roda `occ
  maintenance:data-fingerprint`, para os apps sincronizarem de novo.

## Remover

Desfaz a verificação, remove os containers e as imagens, retira o endereço do Caddy e apaga `~/.astroverso/nextcloud`.
A pasta dos arquivos só é apagada se você confirmar (padrão não), e só se for mesmo uma pasta de dados do Nextcloud.

Testes: `python3 -m unittest discover -s apps/nextcloud/tests`.
