# astro

Homelab em containers (Podman), versionado para reinstalar tudo em minutos em qualquer máquina
se algo der errado. Domínio, IPs, portas e senhas não ficam no código: são perguntados durante a
instalação.

| Projeto | Para que serve |
|---|---|
| [**adguard**](adguard/) | **Servidor DNS da rede.** Todo aparelho pergunta ao DNS qual é o endereço de cada site antes de acessá-lo. Com o AdGuard nesse papel, anúncios, rastreadores e domínios maliciosos são bloqueados para a casa inteira, sem instalar nada nos aparelhos. Ele também responde os nomes internos dos seus serviços (ex.: `*.<seu-domínio>`) com o IP do servidor. |
| [**caddy**](caddy/) | **Proxy reverso com HTTPS.** As aplicações da rede escutam em portas diferentes (`http://<ip>:3000`, `http://<ip>:8080`...). O Caddy recebe os acessos por nome (`https://app.<seu-domínio>`) e encaminha cada um para a aplicação e a porta certas, em qualquer máquina da rede. Assim ninguém precisa decorar IPs e portas, e todo serviço ganha HTTPS com certificado válido do Let's Encrypt, emitido e renovado automaticamente. |
| [**cockpit**](cockpit/) | **Painel de administração do servidor pelo navegador.** Mostra uso de CPU, memória e disco, logs, serviços e atualizações do sistema, abre um terminal e gerencia os containers (ver logs, reiniciar, parar). Serve para cuidar do servidor sem SSH, inclusive pelo celular. |
| [**sunshine**](sunshine/) | **Servidor de jogos remoto.** Transmite a tela, o áudio e os controles de um computador para outro aparelho pela rede, com pouca latência: você joga na TV, no celular ou no notebook, mas quem roda o jogo (ou o emulador) é o servidor. Funciona com o app Moonlight. Os jogos ficam em um usuário próprio, que entra sozinho no boot, separado do usuário que cuida do homelab. |

## Como usar

```bash
git clone <url-deste-repositório> ~/Projects/astro
~/Projects/astro/setup.sh
```

| Opção | O que faz |
|---|---|
| Instalar todos | Instala o que ainda não está instalado |
| Escolher quais instalar | Marca os projetos com Espaço; os já instalados são recriados |
| Configurar um projeto instalado | Ajustes do dia a dia, como adicionar rotas no Caddy |
| Reinstalar tudo do zero | Apaga os dados e instala de novo |
| Remover todos os containers | Mantendo os dados ou apagando tudo |

## Respondendo a instalação

A máquina é preparada para funcionar como servidor: o sistema é atualizado a cada instalação (se vier um
kernel novo, o assistente pede para reiniciar ao final) e ela nunca suspende nem hiberna, nem ao fechar a
tampa de um notebook, para não perder o acesso remoto.

Rode em um terminal normal: o `sudo` pede senha na primeira vez. Enter aceita o valor sugerido entre
`[ ]`, e respostas em formato inválido (porta, IP, endereço) são recusadas e perguntadas de novo. As
respostas ficam em `<projeto>/.env`, fora do git.

### Em todos os projetos

- **Usar a configuração já salva?** Reaproveita as respostas da última instalação. Responda **N** para
  mudar alguma.
- **Anunciar a rede local no Tailscale?** Transforma o servidor em ponte para a rede de casa: de fora,
  qualquer aparelho seu conectado ao Tailscale passa a acessar todos os aparelhos da casa (impressora,
  roteador, outros serviços) sem instalar nada neles. A rede é detectada automaticamente. Depois, aprove
  a rota no painel do Tailscale. Responda **N** se não precisa de acesso remoto.
- **Já fez esse redirecionamento no roteador?** Sem uma porta aberta, o Tailscale às vezes não consegue
  ligar seus aparelhos direto à máquina quando você está fora de casa (por exemplo, no 4G/5G) e passa o
  tráfego por um servidor intermediário (relay), lento demais para coisas como streaming de jogos. O
  assistente mostra a porta UDP e o IP a redirecionar no roteador; a porta só aceita aparelhos
  autenticados na sua rede Tailscale. Só continua com **S**, e a resposta fica guardada nesta máquina.
- **Desativar o login por senha no SSH?** Deixa o acesso remoto ao terminal só por chave, bem mais
  difícil de invadir que uma senha. Só aparece se já houver uma chave em `~/.ssh/authorized_keys`.

### adguard

- **Usuário e senha do painel:** as credenciais de administração do AdGuard, usadas para entrar no painel
  web onde se veem as consultas, as listas de bloqueio e as configurações. A senha é guardada só como
  hash.
- **Porta do painel no host:** a porta em que o painel escuta na máquina. Se o painel for publicado no
  Caddy (pergunta abaixo), essa porta é bloqueada para a rede e o acesso passa a ser só pelo endereço
  HTTPS, para a senha nunca trafegar sem criptografia. Sem o Caddy, o painel abre em `http://<ip>:<porta>`.
- **IP onde o DNS escuta:** `0.0.0.0` atende em todas as redes da máquina. Um IP específico restringe o
  DNS a uma rede só.
- **Fuso horário:** usado nos horários dos logs e das estatísticas e nos agendamentos de bloqueio. Por
  padrão, o fuso da máquina.
- **Idioma do painel.**
- **Adicionar domínios de reescrita?** Faz o AdGuard responder localmente um domínio inteiro: todo
  `*.<domínio>` passa a apontar para o IP informado. É o que faz os endereços do Caddy funcionarem dentro
  de casa, então use o mesmo domínio base do Caddy.
  - **IP de destino:** para onde os nomes apontam. Por padrão, o IP do servidor.
  - **Domínios:** um por vez; Enter vazio termina.
- **Endereço do painel no Caddy:** o nome pelo qual o painel do AdGuard é aberto com HTTPS. Por padrão,
  `adguard.<domínio>`.
- **Usar só o AdGuard como DNS desta máquina?** Define o DNS do próprio servidor. Com **S**, ele sempre
  resolve os nomes internos, mas fica sem DNS nenhum quando o AdGuard está parado (por exemplo, durante
  um "Reinstalar tudo do zero", o que impede baixar as imagens). Com **N** (padrão), ele usa também o DNS
  secundário do roteador e nunca fica sem DNS. Nesse caso, a cada conexão de rede (inclusive no boot) o
  servidor confere se o roteador entregou o AdGuard como DNS primário (pede de novo até 3 vezes), espera
  o AdGuard responder e volta a usá-lo se tiver ficado preso no secundário.
- **Aviso de Split DNS do Tailscale:** aparece se o Tailscale estiver mandando o seu domínio para outro
  servidor DNS. Corrija no painel do Tailscale apontando o domínio para o IP local do servidor.

### caddy

- **Domínio base:** um domínio seu, com o DNS gerenciado pela Cloudflare. Os serviços ficam em
  `<nome>.<domínio>`.
- **Portas HTTP e HTTPS:** `80` e `443`. Mude só se estiverem ocupadas: com outras portas, ela precisa ser
  digitada no endereço.
- **Token da Cloudflare:** permite ao Caddy criar um registro DNS temporário para provar ao Let's Encrypt
  que o domínio é seu, que é o que libera o certificado HTTPS. Precisa das permissões Zone → Read e
  DNS → Edit na zona. O assistente mostra como criar e valida o token na hora.

### cockpit

- **Endereço no Caddy:** o nome pelo qual o painel é acessado. Por padrão,
  `<nome-da-máquina>.<domínio do Caddy>`.

### sunshine

- **Senha temporária do Secure Boot:** só aparece se a máquina tiver uma placa NVIDIA sem o driver
  proprietário e o Secure Boot estiver ligado. O driver é instalado automaticamente, mas o Secure Boot só
  aceita o driver depois que você confirma a chave dele na tela azul do próximo boot, digitando essa
  senha. Ela é usada uma única vez, pode ser simples. Esse passo exige teclado e tela na máquina.
- **Nome do usuário de jogos:** o usuário que entra sozinho no boot e cuja tela é transmitida. É nele que
  ficam os emuladores, os jogos e as configurações. Ele é criado sem senha e sem `sudo`, para que quem
  estiver jogando não tenha acesso ao homelab. Por padrão, `jogos`.
- **Endereço do Sunshine no Caddy:** o nome do painel de administração do Sunshine, onde se pareiam os
  aparelhos. Por padrão, `sunshine.<domínio>`.

Antes de instalar, ligue uma TV, um monitor ou um plugue HDMI fantasma (um adaptador barato que finge
ser um monitor) na porta HDMI e feche a tampa do notebook. A porta HDMI sai pela placa de vídeo dedicada,
e com uma tela nela o Sunshine captura e codifica o vídeo na própria placa (NVENC), com menos latência.
Sem tela nela, o assistente avisa: o Sunshine usa a placa integrada, e só com a tampa aberta. Durante
cada stream, a tela do servidor muda para a resolução pedida pelo aparelho no Moonlight, se ela aceitar
essa resolução, e volta ao final. Ao terminar, reinicie a máquina.

### Depois de instalar

No roteador, configure o IP do servidor como DNS **primário** entregue pelo DHCP, para todos os aparelhos
da casa passarem pelo AdGuard. Um DNS secundário (o do provedor, por exemplo) mantém a internet
funcionando com o servidor desligado; em troca, alguns aparelhos às vezes consultam o secundário e
escapam do bloqueio.

Para criar um projeto novo, veja [lib/README.md](lib/README.md).
