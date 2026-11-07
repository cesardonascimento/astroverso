# caddy

Proxy reverso com HTTPS válido (Let's Encrypt) para os serviços da rede, por exemplo
`https://adguard.cesardonascimento.com → astro-adguard:80`.

```bash
./project.sh install           # pergunta a configuração, prepara o host e sobe o container
./project.sh action add        # adiciona rotas (também pelo setup.sh: "Configurar um projeto instalado")
./project.sh action remove     # remove rotas
./project.sh action list       # lista as rotas
./project.sh remove [--purge]  # remove o container; --purge apaga os certificados
```

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
- Um token criado em https://dash.cloudflare.com/profile/api-tokens com o modelo **Edit zone DNS**,
  restrito à zona do domínio

Os subdomínios diretos (`grafana.<domínio>`) usam um único certificado curinga `*.<domínio>`, o que
evita expor os nomes dos serviços nos registros públicos de certificados. Outros endereços ganham
certificados próprios.

O token fica em `.env` (permissão `600`, fora do git).

## Rotas

Ficam em `.routes` (fora do git), uma por linha: `endereço destino`. Ao adicionar, basta informar o
subdomínio (`grafana` vira `grafana.<domínio base>`) ou um endereço completo, e o destino
(`192.168.3.43:3000`, `http://...` ou `https://...`). As mudanças são aplicadas sem reiniciar o Caddy.

Se o projeto `adguard` existir, a rota `adguard.<domínio base> → astro-adguard:80` é criada
na primeira instalação. Containers do grupo `astro` são acessíveis pelo nome.

Os nomes não existem no DNS público: eles resolvem para esta máquina só dentro da rede, pela reescrita
`*.<domínio base>` do adguard.
