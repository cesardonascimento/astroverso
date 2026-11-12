# n8n

Plataforma de automações montadas pelo navegador, com blocos prontos para centenas de serviços. Roda isolada:
só na rede local, pelo Caddy, e sem comunicação com os servidores da empresa que a desenvolve.

```bash
./project.sh install           # perguntas, containers e rota no Caddy
./project.sh remove            # desfaz tudo o que o projeto criou (usado pelo Implodir Astro)
```

## Perguntas da instalação

| Pergunta | Padrão |
|---|---|
| Endereço do n8n no Caddy | `n8n.<domínio>` |
| E-mail do administrador | `n8n@<domínio>` (só o login: não precisa existir, o n8n não manda e-mails) |
| Nome e sobrenome do administrador | — |
| Senha do administrador | (secreta, mínimo 8 caracteres; ao reinstalar, pergunta se troca) |

## O que vem configurado

| Item | Como |
|---|---|
| Versão | `n8nio/n8n` e `n8nio/runners` fixadas em `docker-compose.yml`, sempre na mesma versão |
| Containers | `astro-n8n` (editor, agendamentos e execuções) e `astro-n8n-runners` (roda o código do nó Code, em JavaScript ou Python, separado do n8n), na rede `astro_default`, sem porta no host |
| Endereço | `https://<endereço>` pelo Caddy (`http://astro-n8n:5678`); webhooks com o mesmo endereço, só na rede local |
| Banco | SQLite em `~/.astro/n8n/data/n8n` |
| Administrador | criado pela instalação por variáveis de ambiente (`N8N_INSTANCE_OWNER_*`), reaplicado a cada início; e-mail, nome e senha ficam travados na interface e mudam pela reinstalação |
| Chave de criptografia | `N8N_ENCRYPTION_KEY`, gerada uma vez no `.env`: protege as credenciais cadastradas no n8n |
| Isolamento | telemetria, aviso de versão nova e galeria de modelos desligados, ganchos de diagnóstico vazios (página "Isolate n8n" da documentação); o assistente de IA da n8n fica desligado |
| Máquina protegida | o nó Execute Command fica desligado, como no padrão da versão 2: o n8n não roda comandos no servidor |
| Histórico | execuções apagadas depois de 14 dias |
| Fuso | o da máquina |

## Backup e restauração

O backup das configurações (rclone, 01:00) chama `project.sh backup`, que roda `n8n export:entities` com o n8n
ligado (fluxos, credenciais, usuários e o resto do banco, em `data/n8n/backup/entities.zip`) e deixa o
`database.sqlite` de fora, porque a cópia do arquivo com o n8n rodando pode sair inconsistente.

A restauração para o n8n, troca a configuração e carrega a exportação num banco novo, por um container avulso
(`import:entities --truncateTables=true`), antes de subir o n8n de novo. A chave de criptografia vem junto, no
`.env` do backup.

## Arquivos gerados

| Caminho | Conteúdo |
|---|---|
| `~/.astro/n8n/.env` | Endereço, fuso, dados do administrador, chave de criptografia e token do executor de código (600) |
| `~/.astro/n8n/data/owner_password_hash` | Hash bcrypt da senha do administrador |
| `~/.astro/n8n/data/n8n` | Banco, configuração e exportação do backup do n8n |

## Remoção

`remove` apaga os containers, as imagens, a rota do Caddy e `~/.astro/n8n` (fluxos, credenciais e histórico).
