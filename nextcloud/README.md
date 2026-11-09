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
| Quais discos guardam arquivos do Nextcloud? | (nenhum marcado) |
| Senha do LUKS de `<disco>` | (só para um disco criptografado que o TPM ainda não destrava) |
| Senha do administrador | (sem padrão; só na primeira instalação) |

O usuário administrador só é criado na primeira instalação: trocar a resposta depois não renomeia a conta.
Trocar a pasta dos arquivos depois de instalado pede confirmação: com **S**, os containers param e os arquivos
são movidos para a pasta nova (que precisa estar vazia); com **N**, a pasta antiga é mantida.

## O que a instalação faz

- **Discos:** monta cada disco escolhido em `/srv/<rótulo>` pelo `fstab`, com as regras de `lib/disk.sh`
  (TPM nos criptografados, nada pede senha no boot). Em cada um:
  - dono `$USER`, permissão `770` com o grupo zerado na ACL (`group::---`): outros usuários da máquina não entram;
  - ACL para o `www-data` do container (o UID dele no host vem do `podman unshare`), também como padrão para o
    que for criado depois. `$USER` e o Nextcloud leem e escrevem nos mesmos arquivos;
  - `context=system_u:object_r:container_file_t:s0` na montagem: o SELinux libera o container sem reetiquetar o disco;
  - `x-systemd.before=user@<uid>.service`: no boot, o disco monta antes de os containers subirem;
  - `x-gvfs-hide`: não aparece no Arquivos.

  O disco entra nos containers em `/mnt/<rótulo>` por um `docker-compose.override.yml` gerado, e no Nextcloud do
  administrador como a pasta `<rótulo>` (app Armazenamento externo, verificação de mudanças a cada acesso). Assim,
  arquivos gravados por fora, por exemplo pela sincronização com outra nuvem, aparecem no Nextcloud.
- Gera a senha do banco em `data/secrets/db_password` (pasta `700`). Os containers a leem pelas variáveis
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
| `.env` | Respostas da instalação (os discos ficam em `DISKS`, pelo UUID) |
| `docker-compose.override.yml` | Volumes dos discos |
| `data/secrets/` | Senha do banco |
| `data/html/` | Código, configuração (`config/config.php`) e apps do Nextcloud |
| `data/db/` | Banco de dados |
| `~/.nextcloud/` | Arquivos dos usuários (pasta padrão) |

## Remoção

`remove` derruba os containers, tira a rota do Caddy e libera os discos (saem do `fstab` e do `crypttab` e são
desmontados), mantendo tudo em `data/`. `--purge` apaga `data/`. Uma pasta dos arquivos fora do projeto e os
arquivos dos discos nunca são apagados.
