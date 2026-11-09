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
| Pasta dos arquivos | `nextcloud/data/files` |
| Senha do administrador | (sem padrão; só na primeira instalação) |

O usuário administrador só é criado na primeira instalação: trocar a resposta depois não renomeia a conta.
Trocar a pasta dos arquivos depois de instalado também não move os arquivos.

## O que a instalação faz

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
  - índices que faltam no banco e reparos.
- Publica a rota `https://<endereço> → http://astro-nextcloud:80` no Caddy.

## Arquivos gerados

| Caminho | Conteúdo |
|---|---|
| `.env` | Respostas da instalação |
| `data/secrets/` | Senha do banco |
| `data/html/` | Código, configuração (`config/config.php`) e apps do Nextcloud |
| `data/db/` | Banco de dados |
| `data/files/` | Arquivos dos usuários (se a pasta padrão for mantida) |

## Remoção

`remove` derruba os containers e tira a rota do Caddy, mantendo tudo em `data/`. `--purge` apaga `data/`.
Uma pasta dos arquivos fora do projeto nunca é apagada.
