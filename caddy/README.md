# caddy

Proxy reverso com HTTPS para os serviços da rede, por exemplo
`https://adguard.cesardonascimento.com → astro-adguard:80`.

```bash
./project.sh install           # pergunta a configuração, prepara o host e sobe o container
./project.sh action add        # adiciona rotas (também pelo setup.sh: "Configurar um projeto instalado")
./project.sh action remove     # remove rotas
./project.sh action list       # lista as rotas
./project.sh action ca         # como instalar o certificado em outros aparelhos
./project.sh remove [--purge]  # remove o container; --purge apaga certificados e a CA
```

## Perguntas da instalação

| Pergunta | Padrão |
|---|---|
| Domínio base dos serviços | — |
| Porta HTTP no host | `80` |
| Porta HTTPS no host | `443` |

## Rotas

Ficam em `.routes` (fora do git), uma por linha: `endereço destino`. Ao adicionar, basta informar o
subdomínio (`grafana` vira `grafana.<domínio base>`) ou um endereço completo, e o destino
(`192.168.3.43:3000`, `http://...` ou `https://...`). As mudanças são aplicadas sem reiniciar o Caddy.

Se o projeto `adguard` existir, a rota `adguard.<domínio base> → astro-adguard:80` é criada
na primeira instalação. Containers do grupo `astro` são acessíveis pelo nome, sem depender de IP ou porta no host.

Os nomes precisam resolver para esta máquina na rede. Com o adguard, isso é feito pela reescrita
`*.<domínio base>` configurada na instalação dele.

## HTTPS

O Caddy usa uma autoridade certificadora própria (`local_certs`): nada precisa ser contratado, mas
cada aparelho precisa confiar no certificado raiz uma vez. A instalação oferece fazer isso nesta
máquina; para os outros, abra `http://ca.<domínio base>` e baixe `astro-ca.crt`.

O `remove --purge` apaga a CA. Na reinstalação uma nova é gerada e os aparelhos precisam do novo certificado.
