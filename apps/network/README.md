# network

A rede da casa: acesso de fora pelo **Tailscale**, e em breve o **AdGuard** (DNS) e o **Caddy** (endereços com
HTTPS), sempre instalados juntos. Hoje só o Tailscale existe.

## O que a instalação faz

Uma explicação curta aparece antes de cada etapa, para quem não conhece o projeto:

1. Instala o Tailscale, liga o serviço e libera a porta dele no firewall.
2. Conecta esta máquina à sua conta do Tailscale (um endereço de login aparece para abrir no navegador).
3. Anuncia o IP desta máquina na rede de casa e acompanha a aprovação no painel do Tailscale.
4. Pergunta se o redirecionamento da porta UDP já foi feito no roteador (opcional, mas recomendado).
5. Avisa para liberar a mesma porta no firewall dos outros computadores que têm o Tailscale.
6. Mostra o Resumo da rede.

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
| `~/.astroverso/network/.env` (`ROUTER_FORWARD`) | Guarda se o redirecionamento no roteador já foi feito, para o Resumo e o Reinstalar |

## Fora da máquina (passos seus)

| Passo | Por quê |
|---|---|
| Aprovar o anúncio `<ip>/32` no painel do Tailscale (Machines → `<nome-da-máquina>` → Edit route settings) | O Tailscale só usa um anúncio depois de aprovado pelo dono da conta |
| No roteador, redirecionar UDP `41641` para `<ip>`, porta `41641` | Garante a conexão direta vinda de fora de casa (4G, outra rede); a porta só aceita aparelhos da sua conta |
| Nos outros computadores com Tailscale, liberar a entrada UDP `41641` no firewall | Sem isso, até dentro de casa a conexão com esta máquina passa por relay |

Comandos para o último passo:

```
Windows (PowerShell como administrador):
New-NetFirewallRule -DisplayName "Tailscale" -Direction Inbound -Protocol UDP -LocalPort 41641 -Action Allow

Linux com firewalld:
sudo firewall-cmd --permanent --add-port=41641/udp && sudo firewall-cmd --reload
```

## Ações

| Ação | O que faz |
|---|---|
| Resumo da rede | Tabelas com esta máquina, a situação do Tailscale e do anúncio, os aparelhos (online, conexão direta ou por relay) e as portas. Aponta quem está por relay |
| Reconectar ao Tailscale | Novo login na conta (ex.: depois de a máquina sair da conta) |
| Marcar o redirecionamento no roteador como feito | Para quando ele for feito depois da instalação |

## Remover

Desfaz tudo da tabela de mudanças: tira a máquina da conta (`tailscale logout`), desliga o serviço, fecha a porta,
desinstala o pacote, apaga `/var/lib/tailscale` e `~/.astroverso/network`. Os passos fora da máquina ficam: a
máquina some do painel, mas a regra no roteador e nos outros computadores continua até você tirá-la.

## Backup

Só o `~/.astroverso/network/.env`. Ao restaurar, a instalação roda com as respostas salvas e o login no Tailscale
é feito de novo.

Testes: `python3 -m unittest discover -s apps/network/tests`.
