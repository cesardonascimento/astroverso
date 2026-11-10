# nextcloud

Nuvem própria para arquivos, fotos, contatos e agenda, acessível em `https://nextcloud.<domínio>` pelo Caddy
e pelos apps do Nextcloud no celular e no computador.

```bash
./project.sh install           # instala, configura e publica o endereço no Caddy
./project.sh remove [--purge]  # remove os containers; --purge apaga também o banco, a configuração e os arquivos
```

## Containers

| Container | Imagem | Função |
|---|---|---|
| `astro-nextcloud` | `nextcloud:<versão>-apache` | O Nextcloud (PHP + Apache), na porta 80 só da rede dos containers |
| `astro-nextcloud-db` | `postgres:<versão>-alpine` | Banco de dados |
| `astro-nextcloud-redis` | `valkey/valkey:<versão>-alpine` | Cache e travas de arquivo, sem gravar nada em disco |
| `astro-nextcloud-cron` | a mesma do Nextcloud | Roda as tarefas em segundo plano a cada 5 minutos |

As versões ficam fixadas no `docker-compose.yml`. O Nextcloud só atualiza uma versão principal por vez
(ex.: da 35 para a 36).

Nenhuma porta é aberta na máquina: o Caddy alcança o `astro-nextcloud` pelo nome, na rede `astro_default`.

## Perguntas da instalação

| Pergunta | Padrão |
|---|---|
| Endereço do Nextcloud no Caddy | `nextcloud.<domínio do caddy>` |
| Usuário administrador | `astro` |
| Pasta dos arquivos | `~/.nextcloud` (no home de quem instala) |
| Quais discos aparecem no Nextcloud? | (nenhum marcado; a lista vem de "Discos da máquina") |
| Senha do administrador | (sem padrão; só na primeira instalação) |

O usuário administrador só é criado na primeira instalação: trocar a resposta depois não renomeia a conta.
Trocar a pasta dos arquivos depois de instalado pede confirmação: com **S**, os containers param e os arquivos
são movidos para a pasta nova (que precisa estar vazia); com **N**, a pasta antiga é mantida.

## O que a instalação faz

- **Discos:** usa os discos escolhidos entre os de "Discos da máquina" (`lib/disk.sh`), que já montam em
  `/srv/<rótulo>` no boot, antes dos containers, e com `context=system_u:object_r:container_file_t:s0` (o SELinux
  libera o container sem reetiquetar o disco). Um disco que não está montado, ou foi montado sem essa opção, fica
  de fora com um aviso. Num disco **privado**, aplica uma ACL para o `www-data` do container (o UID dele no host
  vem do `podman unshare`), também como padrão para o que for criado depois: `$USER` e o Nextcloud leem e
  escrevem nos mesmos arquivos. Num disco **compartilhado**, o Nextcloud acessa como qualquer usuário, sem ACL.

  O disco entra nos containers em `/mnt/<rótulo>` por um `docker-compose.override.yml` gerado, e no Nextcloud do
  administrador como a pasta `<rótulo>` (app Armazenamento externo, verificação de mudanças a cada acesso). Assim,
  arquivos gravados por fora, por exemplo pela sincronização com outra nuvem, aparecem no Nextcloud.
- Gera a senha do banco em `~/.astro/nextcloud/data/secrets/db_password` (pasta `700`). Os containers a leem pelas variáveis
  `*_FILE`, então ela nunca vai para o `.env`.
- Prepara a pasta dos arquivos para o usuário `www-data` do container (`podman unshare chown 33:33`,
  permissão `770`).
- Sobe os containers. Na primeira vez, a imagem instala o Nextcloud sozinha com uma senha de administrador
  aleatória, que é trocada em seguida pela senha digitada (`occ user:resetpassword --password-from-env`) e
  apagada. A senha digitada nunca aparece em argumentos de comando. Se o Nextcloud recusar a senha (curta ou
  vazada em algum site), ela é pedida de novo.
- Ajusta pelo `occ`, a cada instalação:
  - `trusted_domains` e `overwrite.cli.url` com o endereço do Caddy;
  - `trusted_proxies` com a sub-rede da `astro_default`, para ver o IP real de quem acessa;
  - `overwriteprotocol` em `https`;
  - fuso da máquina e região dos telefones, tirada do fuso (`zone.tab`);
  - janela de manutenção às 3h no fuso da máquina;
  - tarefas em segundo plano pelo cron;
  - contas novas sem os arquivos de exemplo (`skeletondirectory` vazio);
  - índices que faltam no banco e reparos.
- Troca o site padrão do Apache por `apache.conf`, que avisa ao Apache que o endereço público é
  `https://<endereço>` (`ServerName` com `https://` e `UseCanonicalName On`). Sem isso, o Apache, que recebe
  o acesso do Caddy em HTTP, redireciona `/.well-known/caldav` e `/.well-known/carddav` para `http://`. O
  mesmo arquivo liga o HSTS (`Strict-Transport-Security`, 180 dias), para o navegador nunca usar HTTP.
- Publica a rota `https://<endereço> → http://astro-nextcloud:80` no Caddy.

## Arquivos gerados

| Caminho | Conteúdo |
|---|---|
| `~/.astro/nextcloud/.env` | Respostas da instalação (os discos ficam em `DISKS`, pelo caminho em `/srv`; um `.env` antigo com UUIDs é convertido) |
| `~/.astro/nextcloud/docker-compose.override.yml` | Volumes dos discos |
| `~/.astro/nextcloud/data/secrets/` | Senha do banco |
| `~/.astro/nextcloud/data/html/` | Código, configuração (`config/config.php`) e apps do Nextcloud |
| `~/.astro/nextcloud/data/db/` | Banco de dados |
| `~/.astro/nextcloud/backup/` | Dump do banco (`pg_dump`), gerado à 01:00 para o backup das configurações |
| `~/.nextcloud/` | Arquivos dos usuários (pasta padrão) |

## Backup das configurações

À 01:00, o rclone pede ao projeto um dump do banco (`pg_dump -Fc`, em `~/.astro/nextcloud/backup`). No arquivo
do backup entram o `.env`, a senha do banco, o dump, `config/`, `custom_apps/`, `themes/` e `version.php`; o
banco em uso e o código (que a imagem recria) ficam de fora. A pasta dos arquivos (`~/.nextcloud`) também fica
de fora: os arquivos do dia a dia ficam nos discos (`armazenamento-a`), que têm o próprio backup.

## Restauração

`restore` (chamado pela opção "Restaurar uma versão das configurações"):

- para os containers, troca `~/.astro/nextcloud` pela configuração do backup e **mantém o código** que já está na
  máquina (`cp --update=none`), já que o backup só tem `config/`, `custom_apps/`, `themes/` e `version.php`;
- prepara a pasta dos arquivos, se ela não existir (com o `.ncdata`, que o Nextcloud exige);
- recria o banco do zero: sobe só o Postgres, recria o usuário do banco que o Nextcloud criou na instalação
  (`oc_<admin>`, nome e senha lidos do `config.php`, senha pela entrada padrão), e carrega o dump com
  `pg_restore` mantendo os donos;
- sobe tudo e roda `occ maintenance:data-fingerprint`, para os apps sincronizarem de novo.

## Remoção

`remove` derruba os containers e tira a rota do Caddy, mantendo tudo em `~/.astro/nextcloud`. Os discos continuam
montados (são da máquina). `--purge` apaga `~/.astro/nextcloud/data`. Uma pasta dos arquivos fora do projeto e os
arquivos dos discos nunca são apagados.
