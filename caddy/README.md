# caddy

Proxy reverso com HTTPS válido (Let's Encrypt) para os serviços da rede, por exemplo
`https://app.<domínio> → <ip>:3000`.

```bash
./project.sh install           # pergunta a configuração, prepara o host e sobe o container
./project.sh action add        # adiciona rotas (também pelo setup.sh: Gerenciar Astro → caddy)
./project.sh action remove     # remove rotas
./project.sh action list       # lista as rotas
./project.sh remove           # desfaz tudo o que o projeto criou (usado pelo Implodir Astro)
```

## Ações (Gerenciar Astro → caddy)

| Ação | O que faz |
|---|---|
| Listar rotas | Mostra as rotas, as manuais e as declaradas pelos projetos (com o nome do projeto) |
| Adicionar rotas | Pergunta o subdomínio (ou endereço completo) e o destino (ex.: `<ip>:3000`), um por vez, e recarrega o Caddy |
| Remover rotas | Escolhe com Espaço quais rotas manuais tirar e recarrega o Caddy |
| Recarregar rotas (inclui as declaradas por outros projetos) | Regrava o `Caddyfile` e recarrega o Caddy sem reiniciar |

## Perguntas da instalação

| Pergunta | Padrão |
|---|---|
| Domínio base dos serviços | — |
| Porta HTTP no host | `80` |
| Porta HTTPS no host | `443` |
| Token de API da Cloudflare | — (validado na hora) |

## HTTPS

A imagem é compilada com o módulo [`caddy-dns/cloudflare`](https://github.com/caddy-dns/cloudflare).
O Caddy prova ao Let's Encrypt que o domínio é seu criando um registro DNS temporário pela API da
Cloudflare (desafio DNS-01). Por isso funciona mesmo com os serviços acessíveis só na rede local, e o
certificado é aceito por qualquer aparelho sem instalar nada. A renovação é automática.

Requisitos:

- O DNS do domínio precisa estar na Cloudflare (o registro do domínio pode ficar em outro lugar)
- Um token criado em https://dash.cloudflare.com/profile/api-tokens com as permissões
  **Zone → Zone → Read** e **Zone → DNS → Edit**, sem expiração,
  restrito à zona do domínio

Os subdomínios diretos (`grafana.<domínio>`) usam um único certificado curinga `*.<domínio>`, o que
evita expor os nomes dos serviços nos registros públicos de certificados. Outros endereços ganham
certificados próprios.

O token fica em `~/.astro/caddy/.env` (permissão `600`), e os certificados em `~/.astro/caddy/data`.

## Rotas

As rotas manuais ficam em `~/.astro/caddy/.routes`, uma por linha: `endereço destino`. Rotas declaradas por
outros projetos (arquivos `~/.astro/<projeto>/.proxy`, como o painel do adguard e o cockpit) também são publicadas e
têm prioridade sobre uma rota manual com o mesmo endereço; a ação **Recarregar rotas** aplica mudanças nelas.
Ao adicionar, basta informar o
subdomínio (`grafana` vira `grafana.<domínio base>`) ou um endereço completo, e o destino
(`<ip>:3000`, `http://...` ou `https://...`). As mudanças são aplicadas sem reiniciar o Caddy.

Containers do grupo `astro` são acessíveis pelo nome; serviços do próprio sistema e containers na rede
do host, por `host.containers.internal`.

Os nomes não existem no DNS público: eles resolvem para esta máquina só dentro da rede, pela reescrita
`*.<domínio base>` do adguard.

## Remoção

`remove` tira o container, as imagens e as portas HTTP e HTTPS do firewall, e apaga `~/.astro/caddy` (token,
rotas manuais e certificados).
