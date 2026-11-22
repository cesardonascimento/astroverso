<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="logo/horizontal.png">
    <img alt="Astroverso" src="logo/horizontal-alt.png" width="480">
  </picture>
</p>

# Astroverso Homelab

Homelab em containers (Podman), versionado para reinstalar tudo em minutos em qualquer máquina
se algo der errado. Domínio, IPs, portas e senhas não ficam no código: são perguntados durante a
instalação.

| Projeto | Para que serve |
|---|---|
| [**adguard**](adguard/) | **Servidor DNS da rede.** Todo aparelho pergunta ao DNS qual é o endereço de cada site antes de acessá-lo. Com o AdGuard nesse papel, anúncios, rastreadores e domínios maliciosos são bloqueados para a casa inteira, sem instalar nada nos aparelhos. Ele também responde os nomes internos dos seus serviços (ex.: `*.<seu-domínio>`) com o IP do servidor. |
| [**caddy**](caddy/) | **Proxy reverso com HTTPS.** As aplicações da rede escutam em portas diferentes (`http://<ip>:3000`, `http://<ip>:8080`...). O Caddy recebe os acessos por nome (`https://app.<seu-domínio>`) e encaminha cada um para a aplicação e a porta certas, em qualquer máquina da rede. Assim ninguém precisa decorar IPs e portas, e todo serviço ganha HTTPS com certificado válido do Let's Encrypt, emitido e renovado automaticamente. |
| [**cockpit**](cockpit/) | **Painel de administração do servidor pelo navegador.** Mostra uso de CPU, memória e disco, logs, serviços e atualizações do sistema, abre um terminal, gerencia os containers (ver logs, reiniciar, parar) e os discos (montar, ejetar) e navega pelos arquivos (enviar, baixar, renomear). Serve para cuidar do servidor sem SSH, inclusive pelo celular, e acessar os discos da máquina de longe. |
| [**mailserver**](mailserver/) | **Caixa de e-mail para automações.** Algumas tarefas começam por um e-mail (um boleto, uma fatura, um aviso), mas dar a um programa acesso à sua caixa pessoal expõe todo o resto. Aqui, você encaminha só o que interessa para um endereço próprio no seu domínio (ex.: `inbox@<seu-domínio>`). A Cloudflare recebe esses e-mails e os guarda até o servidor buscá-los, sem nenhuma porta aberta em casa, e eles ficam numa caixa local que as automações leem e que você abre no app Mail do Nextcloud. Para avisar alguém por e-mail (ex.: o resumo das contas do mês), as automações enviam pela própria Cloudflare, só para endereços que você cadastrou e que confirmaram o cadastro. |
| [**n8n**](n8n/) | **Automações sem programar.** Muitas rotinas são "quando X acontecer, faça Y": quando chegar um e-mail de cobrança, anote numa planilha; todo dia às 8h, mande um resumo no celular. O n8n monta essas rotinas pelo navegador, ligando blocos prontos (e-mail, Discord, Telegram, planilhas, APIs de centenas de serviços), sem escrever código, e guarda o histórico de cada execução. Aqui ele roda isolado: só na rede local e sem enviar nada à empresa que o desenvolve. |
| [**nextcloud**](nextcloud/) | **Nuvem própria.** Faz o papel do Google Drive, do Google Fotos e da agenda e dos contatos do celular, mas com os dados guardados no seu servidor. Os apps do Nextcloud sincronizam pastas do computador, enviam as fotos do celular sozinhos e permitem compartilhar arquivos por link. |
| [**rclone**](rclone/) | **Cópias de segurança.** Um disco só é um ponto único de falha: se ele quebrar, for roubado ou um arquivo for apagado por engano, os dados somem. O backup mantém outras cópias automaticamente: uma em outro disco da máquina, atualizada toda noite e guardando por um tempo o que foi apagado ou alterado, e outra fora de casa, num armazenamento em nuvem (como o Proton Drive), sincronizada nos dois sentidos de 2 em 2 horas durante o dia. Também traz, uma vez por dia, um disco de um computador Windows da rede para um disco da máquina, com todos os arquivos, até os abertos por algum programa. |
| [**samba**](samba/) | **Pasta de rede.** Uma pasta compartilhada aparece nos outros computadores como se fosse um disco deles: no Windows, no Explorador de Arquivos; no Mac, no iPhone e no Linux, no app de arquivos. Serve para passar arquivos entre os aparelhos da casa sem pendrive nem nuvem. Aqui, só a pasta `Public` do seu usuário fica na rede, e só você entra, com usuário e senha. |
| [**sunshine**](sunshine/) | **Acesso remoto à tela da máquina.** Um servidor de streaming (Sunshine) transmite a tela, o som, o teclado, o mouse e os controles para o celular, o notebook ou a TV pelo app Moonlight, com pouca latência e a imagem codificada pela placa de vídeo. Serve para usar a área de trabalho da máquina de qualquer lugar, como se estivesse na frente dela. A máquina entra sozinha no boot com a tela bloqueada: pelo Moonlight, você destrava com a sua senha. |

## Como usar

Numa máquina com Fedora recém-instalado:

```bash
sudo dnf install -y git
git clone <url-deste-repositório> ~/Projects/astroverso-homelab
~/Projects/astroverso-homelab/setup.sh
```

Depois da primeira instalação, o assistente abre com o comando `astroverso`, de qualquer pasta (num terminal novo ou
numa nova entrada pelo SSH).

Nos menus, as setas escolhem e Enter confirma. **Esc** volta ao menu anterior; no menu inicial, fecha o assistente.

| Opção | O que faz |
|---|---|
| Instalar Astroverso | Instala tudo, sempre na mesma ordem: atualiza o sistema (só na primeira vez), prepara a máquina (uma vez), os discos da máquina, `caddy`, `adguard`, `cockpit`, `nextcloud`, `mailserver`, `n8n`, `sunshine`, `samba` e `rclone`. Cada projeto usa o que os anteriores já deixaram pronto (o domínio do Caddy, os discos) |
| Reinstalar Astroverso | O mesmo, com algum projeto já instalado. Antes, mostra todas as etapas (a data de cada concluída, ou "pendente") e pergunta quais rodar: as pendentes, interrompidas ou com falha já vêm marcadas. Esc volta sem rodar nada. Cada projeto refeito pergunta se usa a configuração já salva |
| Gerenciar Astroverso | Os ajustes do dia a dia de cada projeto instalado (ex.: adicionar rotas no Caddy) e a Administração |
| Modo desenvolvimento | Aparece se o Claude Code estiver instalado: abre o Claude na pasta do repositório, continuando a última conversa (ou começando uma), para desenvolver o Astroverso. Ao sair do Claude, `astroverso` abre o assistente de novo |
| Gerenciar Astroverso → Administração → Discos da máquina | Escolhe os discos que a máquina monta no boot e quais são compartilhados com todos os usuários |
| Gerenciar Astroverso → Administração → Máquinas da rede | Cadastra os computadores da rede que podem ser ligados de longe (Wake-on-LAN) e liga um deles na hora; pelo Discord, `machine:wake` (com botões) ou `machine:wake <nome>` |
| Gerenciar Astroverso → Administração → Trocar o domínio | Passa todos os serviços para outro domínio (ex.: `app.<domínio-antigo>` → `app.<domínio-novo>`): mostra o que fazer antes na Cloudflare, troca os endereços salvos (guardando uma cópia da configuração), reaplica cada serviço sem refazer as perguntas e, no fim, lista o que mudar fora da máquina (Tailscale, apps do Nextcloud, favoritos) |
| Gerenciar Astroverso → Administração → Backup: configurações ➡️ local (agora) | Aparece com o rclone instalado: cria na hora uma versão nova do backup das configurações |
| Gerenciar Astroverso → Administração → Backup: configurações ⬅️ local (restaurar uma versão) | Aparece com o rclone instalado: escolhe uma versão e os serviços (ou "Todos") e volta a configuração deles para aquele momento |
| Gerenciar Astroverso → Administração → Implodir Astroverso | Faz um backup das configurações e desfaz tudo o que o Astroverso criou na máquina (veja abaixo) |

## Operações e comandos do Discord

Os nomes abaixo aparecem iguais nos menus, nos avisos do Discord e nos logs. No Discord, `/astro command:help`
mostra esta lista.

O `/astro command:panel` mostra o **Painel do Astroverso**: um botão para cada comando e um menu para iniciar,
parar ou reiniciar os serviços. Os botões continuam funcionando na mensagem, mesmo depois de o bot reiniciar.

| Nome | O que é | Quando | Comando no Discord |
|---|---|---|---|
| Backup: local ⬅️ nuvem | download inicial: traz tudo da nuvem para o disco, sem apagar nada | uma vez, ao cadastrar a nuvem | `backup:cloud` (roda a fase atual) |
| Backup: local ↔️ nuvem | mesclagem: junta disco e nuvem, sem apagar nada | depois do download inicial, ou se o estado se perder | `backup:cloud` (roda a fase atual) |
| Backup: local 🔄 nuvem | sincronização: o que é criado, alterado ou apagado de um lado vai para o outro | de 2 em 2 horas, das 08:00 às 20:00 | `backup:cloud` |
| Backup: local 🔄 nuvem (teste) | mostra o que a sincronização apagaria, sem efeito | quando chegar um aviso de exclusões | `backup:cloud-check` |
| Backup: local 🔄 nuvem (liberar exclusões) | libera o limite de 5% numa rodada | depois de conferir o teste | `backup:cloud-force` (pede confirmação) |
| Backup: local ➡️ backup diário | cópia do disco no disco de backup, com as versões do dia (sincroniza com a nuvem antes) | 03:00 | `backup:daily` |
| Backup: configurações ➡️ local | arquivo criptografado de cada serviço | 01:00 | `backup:configs` |
| Backup: rede ➡️ local | cópia de um disco de um Windows da rede, lida num snapshot (entram até os arquivos abertos); o destino fica igual a ele | uma vez por dia, na primeira vez em que a máquina responder (testa a cada 15 min) | `backup:network` (argumento opcional: a cópia) |
| Backup: configurações ⬅️ local | restaura uma versão das configurações | pelo assistente (Administração) | — |
| Contas: e-mail do mês | manda aos destinatários as contas que vencem no mês, com o QR Code do Pix ou o código de barras | dia 5 de cada mês, às 08:00 (rotina Contas: notificação mensal ligada) | `contas:email` (envia na hora; argumento opcional `AAAA-MM` para outro mês) |
| Mailserver: buscar e-mails | traz para a caixa local os e-mails recebidos na Cloudflare | de 5 em 5 minutos, das 08:00 às 20:00, quando chegou e-mail | `mailserver:fetch` (busca na hora) |
| Mailserver: reprocessar e-mails | entrega de novo na entrada os e-mails dos últimos 30 dias, para as rotinas do n8n lerem outra vez (uma conta já gravada no arquivo do mês é pulada: apague o bloco dela antes) | quando quiser refazer a leitura (no assistente, escolhendo os e-mails) | `mailserver:reprocess` (pede confirmação) |
| Máquina: estado | containers, discos e próximos agendamentos | quando quiser | `machine:status` |
| Máquina: ligar | liga pelo Wake-on-LAN um computador cadastrado em Máquinas da rede e espera até 3 minutos ele responder | quando quiser | `machine:wake [nome]` (sem o nome, um botão por máquina; aparece com alguma máquina cadastrada) |
| Serviço: iniciar | sobe os containers de um projeto | quando quiser | `<projeto>:start` |
| Serviço: parar | para os containers (ficam parados até o start) | quando quiser | `<projeto>:stop` (pede confirmação) |
| Serviço: reiniciar | reinicia os containers | quando quiser | `<projeto>:restart` (pede confirmação) |
| Painel | um botão para cada comando e um menu para os serviços | quando quiser | `panel` |
| Ajuda | esta lista | quando quiser | `help` |

## Respondendo a instalação

A máquina é preparada para funcionar como servidor: na primeira instalação, o assistente atualiza o sistema
(se vier um kernel novo, ele pede para reiniciar ao final) e ela nunca suspende nem hiberna, nem ao fechar a
tampa de um notebook, para não perder o acesso remoto.

Rode em um terminal normal: o `sudo` pede senha na primeira vez. Enter aceita o valor sugerido entre
`[ ]`, e respostas em formato inválido (porta, IP, endereço) são recusadas e perguntadas de novo. As
respostas e tudo o que a instalação gera (dados, certificados, logins) ficam em `~/.astroverso/<projeto>`, fora do
repositório: o repositório tem só o código.

### Em todos os projetos

- **Usar a configuração já salva?** Reaproveita as respostas da última instalação. Responda **N** para
  mudar alguma.
- **Quais etapas concluídas reinstalar?** Só aparece no "Reinstalar Astroverso". Uma etapa (Máquina, Discos da
  máquina ou um projeto) só conta como concluída quando termina sem erro; uma instalação interrompida no meio
  continua de onde parou. Antes da lista, uma linha mostra as pendentes, que sempre rodam. Enter sem marcar nada pula todas as concluídas; marque com Espaço as que quer refazer
  (ou "Todos").

### Máquina

Feita uma vez, no início, para todos os projetos: o comando `astroverso`, suspensão desligada (inclusive na tela de
login), podman-compose, início dos containers no boot, SSH e Tailscale.

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

### Discos da máquina

É a primeira etapa da instalação, antes dos projetos, e também fica em Gerenciar Astroverso → Administração. Os discos
de dados são da máquina, não de um projeto: o seu usuário é sempre o dono, e os projetos (Nextcloud, rclone)
só escolhem quais usar. Um disco plugado de passagem (pendrive, HD externo) não precisa entrar aqui: o
Fedora o monta para quem está na tela, e de longe ele é acessado pelo Cockpit (Armazenamento e Arquivos, com o
acesso administrativo ligado).

- **Quais discos a máquina monta?** Marque com Espaço os discos que ficam sempre ligados à máquina. Cada um é
  montado sozinho a cada boot em `/srv/<rótulo>`, mesmo sem ninguém logado, e volta sozinho se for desligado e
  religado. Desmarcar um disco o desmonta (os dados continuam nele), depois de confirmar. Um disco configurado que
  não está ligado aparece como "desligado": desmarque-o para a máquina esquecê-lo.

- **Senha do LUKS:** só aparece para um disco criptografado. Ela é pedida uma vez para cadastrar o chip de
  segurança da máquina (TPM), que passa a destravar o disco sozinho a cada boot. Assim a máquina nunca
  para no boot pedindo senha e pode ser reiniciada de longe. Levado para outro computador, o disco
  continua travado. Se um dia ele não destravar sozinho (depois de mexer no Secure Boot, por exemplo), rode
  esta opção de novo: ela pede a senha e cadastra o TPM outra vez.
- **Quais são compartilhados com todos os usuários?** Os marcados ficam abertos a todos os usuários da
  máquina e aparecem no Arquivos de qualquer usuário. Os outros são
  privados: só o seu usuário entra. Use privado para dados pessoais. A criptografia protege o disco desligado
  ou levado embora; com a máquina ligada, quem decide o acesso é essa resposta.

Depois desta etapa, a máquina confere os discos a cada 15 minutos. Se um deles some (desligado, cabo solto) ou
para de responder (a conexão caiu e voltou com ele em uso), chega um aviso no Discord. No segundo caso, o disco
só volta a funcionar depois de reiniciar a máquina.

### Máquinas da rede

Fica em Gerenciar Astroverso → Administração. Cadastra outros computadores da casa para ligá-los de longe pelo
Wake-on-LAN: no assistente ("Ligar uma máquina") ou no Discord, com `/astro command:machine:wake` (responde com um botão por máquina) ou `/astro command:machine:wake argument:<nome>`.
O cadastro vai para `~/.astroverso/host.env`, que entra no backup das configurações.

- **Nome da máquina:** o nome usado no Discord (letras minúsculas, números e hífen).
- **IP fixo da máquina na rede local:** serve para saber se ela já está ligada e se ligou. Reserve esse IP no
  DHCP do roteador, pelo MAC.
- **MAC:** só é perguntado se a máquina estiver desligada no cadastro. Ligada, ele é detectado sozinho. No
  Windows, aparece em `ipconfig /all`, como "Endereço Físico" da placa de rede com cabo.

Na máquina que vai ser ligada:

- **BIOS:** desligue o ErP (ou "Deep Sleep"), que corta a energia da placa de rede com o computador desligado, e
  ligue o "Power On By PCI-E" (ou "Wake on LAN"). Na ASUS, ficam em Advanced → APM Configuration.
- **Windows:** no Gerenciador de Dispositivos, na placa de rede com cabo, ligue "Wake on Magic Packet" na aba
  Avançado e, em Gerenciamento de Energia, "Permitir que este dispositivo ative o computador" e "Permitir que apenas
  um pacote mágico ative o computador". Desligue a Inicialização Rápida (Opções de Energia → "Escolher a função
  dos botões de energia").
- Só funciona pelo cabo. Depois de faltar luz, o Windows precisa iniciar e desligar uma vez para a placa voltar a
  esperar o pacote.

### adguard

- **Usuário e senha do painel:** as credenciais de administração do AdGuard, usadas para entrar no painel
  web onde se veem as consultas, as listas de bloqueio e as configurações. O usuário padrão é `astroverso`.
  A senha é guardada só como hash.
- **Porta do painel no host:** a porta em que o painel escuta na máquina. Se o painel for publicado no
  Caddy (pergunta abaixo), essa porta é bloqueada para a rede e o acesso passa a ser só pelo endereço
  HTTPS, para a senha nunca trafegar sem criptografia. Sem o Caddy, o painel abre em `http://<ip>:<porta>`.
- **IP onde o DNS escuta:** `0.0.0.0` atende em todas as redes da máquina. Um IP específico restringe o
  DNS a uma rede só.
- **Fuso horário:** usado nos horários dos logs e das estatísticas e nos agendamentos de bloqueio. Por
  padrão, o fuso da máquina.
- **Idioma do painel.**
- **Responder \*.\<domínio do Caddy\> com o IP desta máquina?** Faz o AdGuard responder localmente o domínio
  inteiro do Caddy: todo `*.<domínio>` passa a apontar para o servidor. É o que faz os endereços do Caddy
  funcionarem dentro de casa. Por padrão, **S**.
- **Adicionar outros domínios?** Outros domínios inteiros para o mesmo IP. Digite um por vez, sem o `*.`
  (ex.: `casa.com`); Enter vazio termina. Sem o Caddy configurado, a pergunta é "Adicionar domínios de reescrita?".
- **IP de destino das reescritas:** para onde os nomes apontam. Por padrão, o IP do servidor.
- **Endereço do painel no Caddy:** o nome pelo qual o painel do AdGuard é aberto com HTTPS. Por padrão,
  `adguard.<domínio>`.
- **Usar só o AdGuard como DNS desta máquina?** Define o DNS do próprio servidor. Com **S**, ele sempre
  resolve os nomes internos, mas fica sem DNS nenhum quando o AdGuard está parado (por exemplo, durante
  a implosão, o que impede baixar as imagens). Com **N** (padrão), ele usa também o DNS
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

### Discord

Os avisos e os comandos pelo celular vêm do **astroverso-discord**, um projeto à parte que roda o bot e atende
vários projetos ao mesmo tempo (este homelab, o studio...). Instale-o pelo próprio repositório dele: lá ficam as
perguntas do token, do canal principal e dos usuários autorizados.

Depois, este homelab se conecta sozinho como o cliente `homelab`, pelo serviço `astroverso-discord-cliente` que
a etapa "Máquina" instala: ele publica os comandos (`/astro`), os canais de avisos (`#financeiro`, `#dados` e
`#sistema`, só de leitura) e atende os pedidos. Com o bot na mesma máquina, nada é perguntado. Com o bot noutra
máquina, grave em `~/.astroverso/host.env` o endereço (`DISCORD_URL='https://discord.<domínio>'`) e a chave do
cliente (`DISCORD_KEY`, mostrada no assistente do astroverso-discord). Avisos feitos com o bot fora do ar
esperam numa fila e são entregues quando ele volta.

No Discord, digite `/astro` e escolha um comando (comece por `help`, que mostra a lista de operações; os nomes
são em inglês, ex.: `backup:cloud`). Comandos que param ou apagam algo pedem confirmação. No celular, deixe as
notificações dos canais de avisos em "Todas as mensagens".

### mailserver

- **Endereço da caixa:** o endereço para onde você encaminha os e-mails. Por padrão, `inbox@<domínio do Caddy>`.
  O domínio do endereço não pode ter outro e-mail: ativar o Email Routing nele troca os registros MX, e o e-mail
  que já chegava por eles deixaria de chegar. Use um domínio só do Astroverso.
- **Domínios autorizados:** de quais domínios a caixa aceita e-mails, separados por vírgula (ex.: o domínio do
  seu e-mail, de onde você encaminha). E-mails de outros domínios, ou sem a autenticação da Cloudflare (SPF ou
  DMARC), vão para a pasta **Quarentena**, que nenhuma automação lê. Assim, um e-mail falso enviado ao endereço não
  vira uma conta a pagar. Depois, a lista muda em Gerenciar Astroverso → mailserver → **Domínios autorizados**, que
  também oferece mover para a entrada o que já estava na Quarentena vindo de um domínio recém-autorizado.
- **Usuário do Nextcloud:** aparece com o Nextcloud instalado. A caixa entra no app **Mail** desse usuário como
  "Astroverso Inbox". Por padrão, o administrador do Nextcloud.
- **Token da Cloudflare:** um token só deste projeto, com as permissões que o assistente lista (Workers, KV,
  regras, endereços de destino e configurações do Email Routing e leitura da zona e do DNS). O assistente mostra como criar e valida o
  token na hora.

A instalação ativa sozinha o Email Routing no domínio do endereço. Se esse domínio já recebe e-mail por outro
serviço, ela para sem mudar nada, porque ativar desviaria esse e-mail.

Quem recebe os e-mails das automações é cadastrado em Gerenciar Astroverso → mailserver → **Destinatários de e-mail**.
A Cloudflare manda a cada endereço novo um e-mail com um link de confirmação; até a pessoa clicar, nada é enviado
para ele.

### n8n

- **Endereço do n8n no Caddy:** o nome pelo qual o n8n é aberto no navegador. Por padrão, `n8n.<domínio>`.
- **E-mail, nome e sobrenome do administrador:** a conta com que você entra no n8n. O e-mail é só o login: o n8n
  não manda e-mails, e o endereço não precisa existir. Por padrão, `n8n@<domínio>`. A conta é criada pela própria instalação, para ninguém na rede tomá-la antes de você no
  primeiro acesso. Para trocar esses dados depois, reinstale o n8n (eles ficam travados na tela do n8n).
- **Senha do administrador:** pelo menos 8 caracteres. Fica guardada só como hash. Ao reinstalar, o assistente
  pergunta se quer trocá-la.
- **Chave da API da Anthropic:** usada pelas rotinas de contas para o Claude ler os e-mails de cobrança. Crie em
  https://console.anthropic.com → API Keys. Enter vazio deixa para depois (em Gerenciar Astroverso → n8n →
  Trocar a chave da API da Anthropic). O conteúdo dos e-mails de cobrança vai para a API da Anthropic.

As **rotinas** ficam no banco do próprio n8n: você as cria, muda e liga pelo editor, e cada versão salva entra no
histórico do n8n (ícone de relógio no editor). O backup das configurações (01:00) leva o banco inteiro, com rotinas,
parâmetros e credenciais. Numa instalação do zero, instale o n8n e use Administração → **Restaurar uma versão** →
n8n para trazer tudo de volta. As credenciais que as rotinas usam (caixa do mailserver, bot do Discord, Nextcloud,
Anthropic, envio de e-mail) são montadas a partir dos outros projetos na instalação do n8n: se a senha de um deles
mudar (ex.: token novo do bot), reinstale o n8n.

As rotinas de contas a pagar usadas hoje:

| Rotina | O que faz |
|---|---|
| Contas: leitura | A cada e-mail na entrada do mailserver, o Claude extrai o tipo da conta (Internet, Energia, Água: o tipo da despesa, não o nome da empresa), titular, valor, vencimento, código (boleto ou Pix) e quem enviou o e-mail original (num encaminhamento); o Astroverso confere os dígitos do código e grava a conta no arquivo `AAAA-MM.md` do **mês de vencimento**, numa pasta do cofre do Obsidian, com aviso no Discord. Confia em todo e-mail da caixa e lê o corpo e **todos os anexos**: PDFs (inclusive com senha, guardadas no nó ⚙️ Configuração, e escaneados) e fotos ou imagens de boletos. O Pix é lido direto do QR Code dos anexos, sem IA; o Claude só procura códigos quando não há QR Code e preenche nome, valor e vencimento. Cada código de pagamento vira uma conta, então um e-mail pode trazer várias. Anexo que não deu para ler e mês que não foi gravado (arquivo aberto no Nextcloud) aparecem no aviso do Discord; e-mail sem nenhuma conta vira um item "⚠️ revisar". Sem PDF anexo, baixa o boleto pelo link do e-mail (escolhido pelo texto do link, como "Visualizar boleto" ou "2ª via"). Cada conta ganha a imagem do código para pagar com a câmera do celular: QR Code do Pix ou, sem Pix, código de barras do boleto. |
| Contas: notificação mensal | No dia 5 de cada mês, às 08:00, manda por e-mail as contas que vencem no mês, no mesmo formato do arquivo, aos destinatários do ⚙️ Configuração e avisa no Discord. Pelo Discord, `contas:email` envia na hora |

O n8n vem isolado: sem telemetria, sem aviso de versão nova e sem a galeria de modelos, que conversam com os
servidores da empresa. Um modelo do site do n8n ainda pode ser copiado e colado no editor. Ele também não roda
comandos na máquina e só é acessível pela rede local.

### nextcloud

- **Endereço do Nextcloud no Caddy:** o nome pelo qual o Nextcloud é aberto no navegador e configurado nos
  apps. Por padrão, `nextcloud.<domínio>`.
- **Usuário administrador:** a conta que administra o Nextcloud e cria as contas das outras pessoas. Por
  padrão, `astroverso`. Só vale na primeira instalação.
- **Pasta dos arquivos:** onde ficam os arquivos enviados ao Nextcloud. Por padrão, a pasta oculta `.nextcloud`
  no home do seu usuário, fora do projeto. Se ela mudar depois de instalado, o assistente pergunta se pode **mover os arquivos** para a
  pasta nova.
- **Quais discos aparecem no Nextcloud?** Marque com Espaço, entre os discos da máquina (veja "Discos da
  máquina"), os que o Nextcloud vai mostrar. Ao reconfigurar, os atuais já vêm marcados: marque um novo para
  adicionar, desmarque para tirar. Cada um aparece no Nextcloud como uma pasta com o nome do disco, e arquivos
  copiados para o disco por fora também aparecem lá. Num disco privado, a primeira vez libera o acesso do
  Nextcloud arquivo por arquivo e pode demorar uns minutos.
- **Senha do administrador:** só aparece na primeira instalação, depois que o Nextcloud termina de instalar
  (alguns minutos). Se o Nextcloud a recusar, por ser curta ou já ter vazado em algum site, ele pede outra.

### rclone

O espelho noturno copia um disco inteiro para outro disco da máquina, toda noite às 03:00.

- **ORIGEM: qual disco proteger?** O disco que será copiado, por exemplo o do Nextcloud. Escolha "Nenhum" para
  fazer só a cópia na nuvem.
- **DESTINO: em qual disco guardar a cópia?** O disco que recebe a cópia (de preferência um disco privado). A
  origem não aparece nesta lista. No fim, o assistente mostra `origem → destino/atual` para conferir.
- **Por quantos dias guardar o que for apagado ou alterado:** cada noite, o que mudou ou sumiu vai para uma
  pasta com a data, em vez de ser perdido. Passado esse prazo, a pasta é apagada. Por padrão, `30`.
- **Adicionar um armazenamento em nuvem agora?** Liga a cópia fora de casa. Dá para adicionar depois, em
  Gerenciar Astroverso → rclone. Sem nenhum disco da máquina, não aparece: a cópia da nuvem precisa de um disco.
  - **Qual armazenamento em nuvem?** O serviço. Hoje, o Proton Drive.
  - **Nome do armazenamento** e **pasta dentro do disco:** onde a cópia da nuvem fica no disco. Por padrão,
    uma pasta com o nome do serviço (ex.: `proton`). A raiz do disco não é aceita, para caber mais de um
    serviço.
  - **E-mail, senha e código da verificação em duas etapas:** o login no serviço. Se você ligar a verificação
    em duas etapas depois, use "Reconectar a um armazenamento em nuvem".
  - **Quando fazer a primeira cópia?** Traz tudo o que já está na nuvem para o disco. Pode levar horas: escolha
    agora, um horário (por exemplo de madrugada) ou depois, pelo menu. Se ela for interrompida (internet,
    reboot, falta de luz), continua sozinha de onde parou.

- **Pasta do backup das configurações:** toda noite, à 01:00, a configuração de cada serviço (respostas,
  certificados, logins, bancos de dados) vira um arquivo criptografado numa subpasta com o nome do serviço
  (ex.: `nextcloud/nextcloud.tar.zst.gpg`). Dentro dele fica só a pasta do serviço, sem o nome do usuário: dá para
  restaurar em outra máquina, com outro usuário.
  Por padrão, `Astroverso/Configurações` dentro da pasta do primeiro armazenamento em nuvem: assim ele segue para a
  nuvem e para o disco de backup nas rodadas seguintes. Sem nenhum disco da máquina, o backup das configurações
  fica desligado até um disco ser cadastrado e o Astroverso reinstalado.
- **Senha do backup das configurações:** criptografa esse arquivo. **Guarde-a fora da máquina** (num gerenciador
  de senhas): sem ela, o backup não abre. Na reinstalação, o assistente pergunta se mantém a atual.

- **Por quantos dias guardar as versões do backup das configurações:** cada backup fica numa pasta com a data e
  a hora (ex.: `2026-11-10_010000/nextcloud/nextcloud.tar.zst.gpg`); as mais antigas que isso são apagadas. Por
  padrão, `90`.

Os horários: sincronização com a nuvem de 2 em 2 horas, das 08:00 às 20:00; 01:00 backup das configurações;
03:00 uma última sincronização com a nuvem e o espelho no disco de backup.

**Restaurar uma versão** (Gerenciar Astroverso → Administração): mostra as versões da mais nova para a mais antiga e os serviços de
cada uma. Antes de trocar qualquer coisa, o assistente para o rclone (se estiver copiando algo, pergunta antes) e
salva a situação atual como uma versão "antes da restauração", para dar para voltar. Depois, para cada serviço
escolhido: para os containers, troca a configuração pela do backup e sobe de novo. Se a senha atual não abrir a
versão escolhida, ele pede a senha daquela época.

Depois da primeira cópia, **o disco e a nuvem ficam iguais**: o que for criado, alterado ou apagado de um lado
(pelo Nextcloud, pelo app da nuvem ou por quem tem uma pasta compartilhada com você) vai para o outro na
sincronização seguinte. Se o mesmo arquivo mudar dos dois lados, fica o mais novo, e o outro é guardado ao
lado com `.conflict1` no nome. Se uma rodada for apagar mais de 5% dos arquivos, ela para sem apagar nada:
"Backup: local 🔄 nuvem (agora)", no menu do rclone, mostra o aviso e pergunta se libera.

**Adicionar cópia da rede** (Gerenciar Astroverso → rclone): copia todo dia um disco (ou uma pasta dele) de um
computador Windows da rede para um disco da máquina. O outro computador é a fonte de verdade: o destino fica igual a
ele, inclusive no que for apagado lá. Ele não precisa ficar ligado num horário certo: a cada 15 minutos o rclone vê se
ele responde e faz a cópia do dia na primeira vez em que responder. A leitura é feita num snapshot do Windows (uma
foto do disco naquele instante, apagada no fim da cópia): entram até os arquivos que algum programa mantém abertos,
como a biblioteca do Playnite. No destino, cada arquivo fica separado, como no disco de origem.

- **Nome da cópia:** identifica a cópia nos menus e avisos (ex.: o nome da outra máquina).
- **Endereço da outra máquina:** o IP ou o nome dela na rede local.
- **Usuário do Windows:** a conta que entra pelo SSH, o nome que o `whoami` mostra depois da barra. Precisa ser
  administradora, porque o snapshot exige.
- **Letra do disco no Windows** e **pasta dentro do disco:** o que será copiado. `/` copia o disco inteiro.
- **Em qual disco guardar** e **pasta dentro do disco:** o destino. O disco de backup não aparece, e a pasta não pode
  se sobrepor à de um armazenamento em nuvem ou de outra cópia. Se ela já tiver arquivos, o assistente avisa que o
  que não existir na origem será apagado e pede confirmação. Os arquivos iguais aos da origem (mesmo caminho e
  tamanho) são aproveitados na primeira cópia, sem transferir de novo.
- **Na outra máquina, uma vez só:** o assistente mostra os passos. Instalar o "Servidor OpenSSH" (Configurações →
  Sistema → Recursos opcionais) e rodar no PowerShell, como administrador, a linha que cadastra a chave desta máquina.
  Não há senha: o acesso é só por essa chave. Com a outra máquina ligada, o assistente testa na hora (entra, cria um
  snapshot, lê e apaga). Para refazer o acesso depois, use "Reconectar a uma cópia da rede".
- **Avisar no Discord depois de quantos dias sem cópia:** se a máquina ficar esse tempo sem responder, chega um aviso
  por dia até ela voltar. Por padrão, `7`.

### samba

- **Senha do Samba:** a senha para abrir a pasta de rede, com o seu usuário. É separada da senha de login da
  máquina (pode ser a mesma) e vale só para a pasta. Na reinstalação, o assistente pergunta se mantém a atual.

No Windows, abra `\\<nome-da-máquina>.<domínio>\Public` no Explorador de Arquivos (ou use "Mapear unidade de
rede" para ela virar uma letra de disco). No Mac, no Linux e no iPhone, conecte ao servidor
`smb://<nome-da-máquina>.<domínio>/Public`. O endereço é o mesmo em casa e fora, pelo Tailscale: o AdGuard responde
o nome. A máquina não se anuncia sozinha em "Rede": salve o endereço como favorito. Só a pasta `Public` fica na
rede: o resto do seu home não aparece. Um arquivo movido para a pasta de outro lugar do home pode não aparecer
pela rede até a instalação do `samba` rodar de novo.

### sunshine

O Sunshine roda na sessão do seu usuário. Para ele estar no ar depois de um reinício feito de longe, a máquina
entra sozinha com o seu usuário no boot e bloqueia a tela logo em seguida: na tela da máquina e no Moonlight,
aparece a tela de bloqueio, e só a sua senha destrava. Parada por 5 minutos, a tela bloqueia de novo. Com o login
automático, o chaveiro do GNOME não abre no boot: programas que guardam senhas nele pedem a senha na primeira vez.

- **Senha temporária do Secure Boot:** só aparece se a máquina tiver uma placa NVIDIA sem o driver
  proprietário e o Secure Boot estiver ligado. O driver é instalado automaticamente, mas o Secure Boot só
  aceita o driver depois que você confirma a chave dele na tela azul do próximo boot, digitando essa
  senha. Ela é usada uma única vez, pode ser simples. Esse passo exige teclado e tela na máquina.
- **Endereço do Sunshine no Caddy:** o nome do painel de administração do Sunshine, onde se pareiam os
  aparelhos. Por padrão, `sunshine.<nome-da-máquina>.<domínio>`, para permitir mais de um Sunshine na rede.

Antes de instalar, ligue um monitor ou um plugue HDMI fantasma (um adaptador barato que finge ser um monitor) na
porta HDMI e feche a tampa do notebook. A porta HDMI sai pela placa de vídeo dedicada, e com uma tela nela o
Sunshine captura e codifica o vídeo na própria placa (NVENC), com menos latência. Sem tela nela, o assistente
avisa: o Sunshine usa a placa integrada, e só com a tampa aberta. Durante cada stream, a tela do servidor muda
para a resolução pedida pelo aparelho no Moonlight, se ela aceitar essa resolução, e volta ao final. No Moonlight,
aparece o app **Desktop**. A tela do HDMI fica sempre acesa (mostrando a tela de bloqueio), porque o Sunshine não
transmite uma tela apagada; a do notebook, com a tampa fechada, fica desligada. Ao terminar, reinicie a máquina e
pareie cada aparelho pelo painel do Sunshine (PIN).

### Implodir Astroverso

Fica em Gerenciar Astroverso → Administração. Desfaz tudo o que o Astroverso criou, na ordem inversa da instalação:
containers, imagens, serviços e a configuração de todos os projetos (`~/.astroverso`), a pasta local de arquivos do Nextcloud, as montagens dos discos em `/srv` (o TPM dos discos criptografados
é descadastrado e eles voltam a abrir só com a senha) e os ajustes da máquina feitos para o Astroverso: suspensão,
firewall, DNS, portas baixas, a rede anunciada no Tailscale e o início automático no boot. Ficam os pacotes
instalados (sistema atualizado, Tailscale, driver da NVIDIA, Cockpit, Sunshine, rclone), os dados dos
discos, o SSH ligado (só volta o login por senha) e o repositório.

- **Para confirmar, digite IMPLODIR:** qualquer outra resposta cancela sem mudar nada.
- **Pasta e senha do backup:** antes de desfazer qualquer coisa, a configuração de cada serviço vai para uma
  versão `antes-de-implodir` do backup das configurações. Com o backup do rclone ligado, usa a pasta e a senha
  dele, sem perguntar. Sem ele, pergunta uma pasta (por padrão, `Astroverso/Configurações` no primeiro disco da máquina)
  e uma senha. **Guarde a senha fora da máquina.** Depois de reinstalar, use essa pasta como "pasta do backup das
  configurações" do rclone e restaure em Gerenciar Astroverso → Administração. Se o backup falhar, nada é desfeito.

### Depois de instalar

No roteador, configure o IP do servidor como DNS **primário** entregue pelo DHCP, para todos os aparelhos
da casa passarem pelo AdGuard. Um DNS secundário (o do provedor, por exemplo) mantém a internet
funcionando com o servidor desligado; em troca, alguns aparelhos às vezes consultam o secundário e
escapam do bloqueio.

Com o **mailserver**, crie no seu e-mail um encaminhamento para o endereço da caixa. No Proton: Configurações →
Filtros, um filtro por remetente (ex.: as empresas das contas) com a ação de encaminhar. O Proton manda um e-mail
de confirmação para o endereço novo: ele chega na pasta Quarentena do app Mail do Nextcloud, com o link para
confirmar.

Para o **Contas: notificação mensal**: cadastre os destinatários em Gerenciar Astroverso → mailserver → Destinatários de
e-mail (cada um confirma pelo link que recebe) e escreva os mesmos endereços em `destinatarios` no ⚙️ Configuração
da rotina, separados por vírgula.

Para criar um projeto novo, veja [lib/README.md](lib/README.md).
