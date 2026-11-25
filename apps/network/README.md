# network

A rede da casa: acesso de fora pelo **Tailscale**, DNS com bloqueio de propaganda pelo **AdGuard** e endereços
com HTTPS pelo **Caddy** (`<serviço>.<domínio>`, iguais dentro e fora de casa), sempre instalados juntos.

## O que a instalação faz

Uma explicação curta aparece antes de cada etapa, para quem não conhece o projeto. Os passos em sites de terceiros
(Tailscale, Cloudflare, roteador) aparecem como link para os docs em [`docs/`](docs/):

1. Instala o Tailscale, liga o serviço e libera a porta dele no firewall.
2. Conecta esta máquina à sua conta do Tailscale (um endereço de login aparece para abrir no navegador).
3. Anuncia o IP desta máquina na rede de casa e acompanha a aprovação no painel do Tailscale (link para o passo a
   passo).
4. Pergunta se o redirecionamento da porta UDP já foi feito no roteador (opcional, mas recomendado; link para o
   passo a passo).
5. Avisa para liberar a mesma porta no firewall dos outros computadores que têm o Tailscale (link para o passo a
   passo).
6. AdGuard: pergunta o domínio (só na primeira vez de qualquer app), o usuário e a senha do painel; sobe o AdGuard
   com a reescrita `*.<domínio>` → IP desta máquina e confere se os nomes respondem.
7. Confere o Split DNS do Tailscale e, se faltar, mostra o link para o passo a passo.
8. Pede para apontar o DNS do roteador para esta máquina (com um secundário), com o link para o passo a passo, e
   pergunta se já foi feito.
9. Caddy: pede o token da Cloudflare (com o link para o passo a passo) e o confere na API; oferece criar endereços
   para aparelhos da rede (opcional); monta a imagem, sobe o Caddy e espera o cadeado do Let's Encrypt.
10. Liga a verificação de hora em hora (avisos no Discord) e mostra os endereços e o Resumo da rede.

O "Reinstalar" pode reaproveitar as respostas salvas.

## Mudanças na máquina

| Mudança | Por quê |
|---|---|
| Pacote `tailscale` instalado (repositórios da distribuição) | É o programa do Tailscale: a rede privada entre os seus aparelhos e esta máquina |
| Serviço `tailscaled` ligado agora e no boot | Mantém a máquina na rede do Tailscale o tempo todo, inclusive depois de reiniciar |
| Porta `41641/udp` liberada no firewall | Por ela os seus aparelhos se ligam **direto** a esta máquina; fechada, a conexão passa por um servidor intermediário (relay), bem mais lento |
| Máquina conectada à sua conta do Tailscale, com o nome da máquina | Para ela aparecer entre os seus aparelhos e ser alcançada por eles |
| Usuário que instala como operador do Tailscale (`--operator`) | Permite consultar o Tailscale sem `sudo`, como no Resumo da rede |
| Não aceita rotas de outros aparelhos (`--accept-routes=false`) | Uma rota da rede de casa anunciada por outro aparelho desviaria pelo Tailscale o tráfego da própria rede local desta máquina |
| Anúncio do próprio IP da rede de casa (`<ip>/32`) | O domínio aponta para esse IP: fora de casa, é o que faz os endereços do Astroverso abrirem. Só esta máquina fica alcançável, não a rede inteira |
| Podman instalado e *linger* ligado para o usuário | O AdGuard roda em container, como serviço do usuário, e precisa subir no boot sem ninguém logado |
| Container `astroverso-network-adguard` (imagem oficial `adguard/adguardhome`, versão fixada), unidade Quadlet em `~/.config/containers/systemd/` | O DNS da casa, com bloqueio de propaganda e rastreadores; reinicia sozinho e sobe no boot |
| Rede do host para o AdGuard, escutando no IP da rede e no `127.0.0.1` | As respostas UDP voltam certas para quem pergunta pelo Tailscale, o registro mostra o IP real de cada aparelho, e o DNS interno do Fedora (`systemd-resolved`) continua funcionando |
| `/etc/sysctl.d/99-astroverso-network.conf` (`net.ipv4.ip_unprivileged_port_start = 53`) | Containers sem root só podem abrir portas a partir de 1024; o DNS usa a 53 (e o Caddy usará a 80 e a 443) |
| Serviço `dns` (porta 53 TCP/UDP) liberado no firewall | Para os aparelhos da casa e do Tailscale perguntarem ao AdGuard |
| `/etc/systemd/resolved.conf.d/99-astroverso-network.conf` (`DNS=127.0.0.1`, `Domains=~<domínio>`) | Esta máquina pergunta ao AdGuard só pelos nomes do domínio e usa o DNS do roteador para o resto: ela nunca fica sem DNS, mesmo com o AdGuard parado |
| `~/.astroverso/astroverso.env` (`DOMAIN`) | O domínio dos endereços, perguntado uma vez e usado por todos os apps |
| `~/.astroverso/network/adguard/` (`conf/AdGuardHome.yaml`, `work/`) | A configuração do AdGuard (gerada uma vez; as mudanças feitas no painel ficam) e os dados dele |
| `~/.astroverso/network/.env` (`SERVER_IP`, `ROUTER_FORWARD`, `ROUTER_DNS`, `ADGUARD_USER`, `ADGUARD_PASSWORD_HASH`) | As respostas da instalação, para o Resumo e o Reinstalar; a senha só como hash (bcrypt, calculado pela imagem do Caddy) |
| Imagem local `localhost/astroverso-network-caddy:<versão>` (Caddy oficial + módulo `caddy-dns/cloudflare`, versões fixadas), montada na instalação; a imagem de montagem é apagada depois | O Caddy oficial não fala com a Cloudflare; o módulo permite o cadeado curinga `*.<domínio>` sem abrir nenhuma porta para a internet |
| Container `astroverso-network-caddy` na rede `astroverso`, portas 80 e 443 (TCP e UDP), unidade Quadlet | Recebe os acessos a `https://<serviço>.<domínio>` e repassa a cada serviço: containers pelo nome, serviços desta máquina por `host.containers.internal`, aparelhos da rede pelo IP |
| Serviços `http` e `https` e a porta `443/udp` liberados no firewall | Para os aparelhos abrirem os endereços (a 80 só redireciona para a 443; a 443/udp é o HTTP/3) |
| `~/.astroverso/network/caddy/caddy.env` (`600`) | O token da Cloudflare, lido pelo container sem aparecer no arquivo da unidade nem nos argumentos |
| `~/.astroverso/network/caddy/etc/Caddyfile` | A configuração do Caddy, gerada a partir dos endereços (nunca editada à mão) |
| `~/.astroverso/network/caddy/data/` e `config/` | O cadeado do Let's Encrypt e o estado do Caddy (o cadeado renova sozinho) |
| `~/.astroverso/network/caddy/devices.json` | Os endereços de aparelhos da rede (nome, IP, porta, HTTP ou HTTPS) |
| Unidades do usuário `astroverso-network-routes.path` e `.service` em `~/.config/systemd/user/` | Quando um app publica ou retira um endereço em `~/.astroverso/routes/`, o Caddy recarrega sozinho, sem reiniciar (`astroverso network action reload`) |
| Unidades do usuário `astroverso-network-watch.timer` e `.service` | A cada hora (a primeira 10 min depois de ligar), confere a rede e avisa no Discord pelo `kit.discord` quando algo quebra e quando volta ao normal (`astroverso network action watch`) |
| `~/.astroverso/network/watch.json` | Os avisos em aberto, para não repetir o mesmo aviso a cada hora |
| Pasta `~/.astroverso/routes/` (`700`), se ainda não existir | Onde os apps publicam os endereços deles (`kit.routes`); não é de nenhum app e fica no `remove` |
| Painel do AdGuard só por `https://adguard.<domínio>` (a porta 8080 não é aberta na rede) | Com login e cadeado; a 8080 só é alcançada pelo Caddy |

## Fora da máquina (passos seus)

O passo a passo de cada um fica em [`docs/`](docs/). Na instalação, a etapa que precisa de um deles mostra só uma
frase e o link para o doc no GitHub, para abrir no navegador.

| Passo | Por quê | Como fazer |
|---|---|---|
| Aprovar o anúncio `<ip>/32` no painel do Tailscale | O Tailscale só usa um anúncio depois de aprovado pelo dono da conta | [tailscale.md](docs/tailscale.md#aprovar-a-rota-do-servidor) |
| No painel do Tailscale, Split DNS `<domínio>` → `<ip>` | Fora de casa, os aparelhos perguntam ao AdGuard pelos endereços do domínio | [tailscale.md](docs/tailscale.md#split-dns) |
| No roteador, reservar o IP `<ip>` para esta máquina | O DNS e o anúncio do Tailscale dependem desse IP não mudar | [roteador.md](docs/roteador.md#reservar-o-ip-e-apontar-o-dns) |
| No roteador, DNS primário `<ip>` e um público (como `1.1.1.1`) como secundário | Os aparelhos da casa passam a usar o AdGuard; o secundário os mantém navegando se esta máquina estiver desligada (sem bloqueio e sem os endereços da casa) | [roteador.md](docs/roteador.md#reservar-o-ip-e-apontar-o-dns) |
| No roteador, redirecionar UDP `41641` para `<ip>`, porta `41641` (opcional, recomendado) | Garante a conexão direta vinda de fora de casa (4G, outra rede); a porta só aceita aparelhos da sua conta | [roteador.md](docs/roteador.md#redirecionar-a-porta-do-tailscale) |
| Nos outros computadores com Tailscale, liberar a entrada UDP `41641` no firewall | Sem isso, até dentro de casa a conexão com esta máquina passa por relay | [outros-computadores.md](docs/outros-computadores.md) |
| Na Cloudflare, criar um token só para a zona do domínio, sem expiração | O Caddy prova ao Let's Encrypt que o domínio é seu criando um registro temporário no DNS; se o token expirar, o cadeado para de renovar | [cloudflare.md](docs/cloudflare.md#criar-o-token) |

## Ações

| Ação | O que faz |
|---|---|
| Resumo da rede | Tabelas com esta máquina, a situação do Tailscale e do anúncio, os aparelhos (online, conexão direta ou por relay), o DNS (AdGuard no ar, reescrita, teste de nome, Split DNS, roteador, painel), o Caddy (no ar, validade do cadeado, token), todos os endereços com destino e origem, e as portas. Aponta quem está por relay |
| Reconectar ao Tailscale | Novo login na conta (ex.: depois de a máquina sair da conta) |
| Marcar o redirecionamento no roteador como feito | Para quando ele for feito depois da instalação |
| Marcar o DNS no roteador como feito | Idem, para o DNS do roteador |
| Endereços de aparelhos da rede | Lista, cria e remove endereços `https://<nome>.<domínio>` para painéis de aparelhos da casa (IP, porta, HTTP ou HTTPS); o Caddy recarrega sem reiniciar |
| Verificar a rede agora (e avisar no Discord) | Roda na hora a verificação de hora em hora (abaixo) |
| Recarregar os endereços do Caddy | Regera o Caddyfile (inclusive com os endereços publicados por outros apps em `~/.astroverso/routes/`) e recarrega. Normalmente não é preciso: a unidade `astroverso-network-routes.path` faz isso sozinha |

## Verificação de hora em hora

Avisa no canal `#network` do Discord (pelo `kit.discord`, se o app `discord` estiver ligado nesta máquina) **só
quando algo muda**: quando um problema aparece, quando ele piora (de aviso para erro) e quando volta ao normal
(✅ resolvido). Um aviso que não foi entregue é tentado de novo na hora seguinte.

| O que confere | Nível |
|---|---|
| AdGuard parado (a casa fica no DNS secundário) | erro |
| Caddy parado (os endereços não abrem) | erro |
| Cadeado vence em menos de 14 dias / menos de 3 / inválido ou vencido | aviso / erro / erro |
| Token da Cloudflare recusado (sem internet não conta) | erro |
| IP desta máquina diferente do da instalação (reserva no roteador falhou) | erro |
| Máquina fora do Tailscale, ou o anúncio `<ip>/32` sem aprovação | erro |
| Chave desta máquina no Tailscale vence em menos de 14 dias | aviso |
| Aparelho com conexão ativa passando por relay | info |

Cada aviso traz o link para o doc que resolve e os botões **Resumo da rede** e **Verificar de novo**, que rodam
essas ações pelo Discord. Sem o Discord, a verificação só escreve no log
(`journalctl --user -u astroverso-network-watch`). Com esta máquina desligada ou sem internet, não há aviso.

## Remover

Desfaz tudo da tabela de mudanças: remove as unidades da verificação e da recarga automática, os containers e as imagens do Caddy e do AdGuard, tira o ajuste de DNS
desta máquina, fecha as portas, apaga o ajuste de portas baixas, tira a máquina da conta do Tailscale
(`tailscale logout`), desliga o serviço, desinstala o pacote e apaga `/var/lib/tailscale` e `~/.astroverso/network`.
O Podman, o *linger* e o `astroverso.env` ficam (são de todos os apps). Os passos fora da máquina ficam: a
máquina some do painel, mas a regra no roteador e nos outros computadores continua até você tirá-la.

## Backup

O `~/.astroverso/network/.env`, o `AdGuardHome.yaml` (com as mudanças feitas no painel), o token da Cloudflare e os
endereços de aparelhos. O cadeado não entra: é emitido de novo. Ao restaurar, a
instalação roda com as respostas salvas e o login no Tailscale é feito de novo.

Testes: `python3 -m unittest discover -s apps/network/tests`.
