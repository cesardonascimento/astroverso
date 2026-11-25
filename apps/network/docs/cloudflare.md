# Cloudflare: token para o cadeado

O Caddy do `network` dá a cada serviço um endereço com cadeado (HTTPS), como `https://adguard.<domínio>`. Ele usa um
só certificado curinga, `*.<domínio>`, emitido de graça pelo Let's Encrypt e renovado sozinho.

Para emitir o certificado, o Let's Encrypt pede uma prova de que o domínio é seu: um registro temporário no DNS do
domínio (o desafio DNS-01). O Caddy cria esse registro na Cloudflare, espera a conferência e o apaga em seguida.
Por isso precisa de um **token** da Cloudflare. Com esse método, nenhuma porta da casa fica aberta para a internet.

Requisito: o DNS do domínio precisa estar na Cloudflare, com o domínio aparecendo como uma zona na sua conta (o
registro do domínio pode ser em outra empresa).

Nos exemplos, `<domínio>` é o seu domínio. O instalador mostra o valor certo na tela.

## Criar o token

1. Abra <https://dash.cloudflare.com/profile/api-tokens> (ícone da conta → **My Profile** → **API Tokens**).
2. Clique em **Create Token**.
3. No modelo **Edit zone DNS**, clique em **Use template**.
4. Em **Permissions**, deixe duas linhas (use **+ Add more** para a segunda):
   - **Zone** · **Zone** · **Read**: o instalador usa para conferir que o token enxerga o domínio;
   - **Zone** · **DNS** · **Edit**: para o Caddy criar e apagar o registro temporário.
5. Em **Zone Resources**, escolha **Include** · **Specific zone** · `<domínio>`. Assim o token só mexe nesse
   domínio, nunca nos outros da conta.
6. Deixe **Client IP Address Filtering** vazio. O IP de casa muda, e com o filtro o token pararia de funcionar.
7. Em **TTL**, deixe sem data de fim. Um token que expira faz o cadeado parar de renovar, e uns três meses depois
   os endereços passam a dar erro de certificado.
8. Clique em **Continue to summary** e confira se aparece `<domínio>` com as duas permissões.
9. Clique em **Create Token** e copie o token. **Ele só aparece uma vez**: guarde no seu gerenciador de senhas antes
   de fechar a página.

Cole o token quando o instalador pedir (ele não aparece na tela). O instalador confere na hora, na API da Cloudflare,
se o token está ativo e se enxerga `<domínio>`. Se algo estiver errado, ele diz o quê e pede de novo.

O token fica só no servidor, em `~/.astroverso/network/caddy/caddy.env`, com acesso só do seu usuário. Ele também
entra no backup das configurações.

## Trocar o token

Se o token vazar, for apagado ou você quiser trocá-lo:

1. Crie um token novo, como acima.
2. Rode **Reinstalar** no `network` e responda que **não** quer reaproveitar as respostas salvas: o instalador pede
   o token de novo. Com o reaproveitamento, ele só pede se o token salvo tiver deixado de valer.
3. Apague o token antigo na Cloudflare (**API Tokens** → **⋯** → **Delete**).

## Quando o cadeado demora

O primeiro cadeado costuma sair em menos de um minuto, mas o instalador espera até 3. Se não sair:

| Sintoma | Causa provável |
|---|---|
| Erro `403` ou `Authentication error` no log do Caddy | Token sem a permissão **Zone · DNS · Edit** ou restrito a outra zona |
| Erro de propagação ou `timeout` | O DNS do domínio não está na Cloudflare (confira os nameservers no registro do domínio) |
| Erro `too many certificates` | Limite semanal do Let's Encrypt, depois de muitas reinstalações seguidas. Espere alguns dias |

O Caddy continua tentando sozinho. O **Resumo da rede** mostra a validade do cadeado quando ele sai, e o log
completo aparece com:

```
journalctl --user -u astroverso-network-caddy -n 100
```
