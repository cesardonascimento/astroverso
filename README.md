# astro

Homelab em containers (Podman), versionado para reinstalar tudo em minutos em qualquer máquina
se algo der errado. Domínio, IPs, portas e senhas não ficam no código: são perguntados durante a
instalação.

| Projeto | Para que serve |
|---|---|
| [**adguard**](adguard/) | **Servidor DNS da rede.** Todo aparelho pergunta ao DNS qual é o endereço de cada site antes de acessá-lo. Com o AdGuard nesse papel, anúncios, rastreadores e domínios maliciosos são bloqueados para a casa inteira, sem instalar nada nos aparelhos. Ele também responde os nomes internos dos seus serviços (ex.: `*.<seu-domínio>`) com o IP do servidor. |
| [**arcade**](arcade/) | **Videogame retrô transmitido pela rede.** Um frontend de jogos (ES-DE) mostra a coleção com capas e vídeos, e os emuladores (RetroArch) rodam os jogos de consoles antigos. Um servidor de streaming (Sunshine) transmite a tela, o som e os controles para a TV, o celular ou o notebook pelo app Moonlight, com pouca latência: quem roda o jogo é o servidor. Tudo fica num usuário próprio para jogos, que entra sozinho no boot, separado do usuário que cuida do homelab. |
| [**caddy**](caddy/) | **Proxy reverso com HTTPS.** As aplicações da rede escutam em portas diferentes (`http://<ip>:3000`, `http://<ip>:8080`...). O Caddy recebe os acessos por nome (`https://app.<seu-domínio>`) e encaminha cada um para a aplicação e a porta certas, em qualquer máquina da rede. Assim ninguém precisa decorar IPs e portas, e todo serviço ganha HTTPS com certificado válido do Let's Encrypt, emitido e renovado automaticamente. |
| [**cockpit**](cockpit/) | **Painel de administração do servidor pelo navegador.** Mostra uso de CPU, memória e disco, logs, serviços e atualizações do sistema, abre um terminal, gerencia os containers (ver logs, reiniciar, parar) e os discos (montar, ejetar) e navega pelos arquivos (enviar, baixar, renomear). Serve para cuidar do servidor sem SSH, inclusive pelo celular, e acessar os discos da máquina de longe. |
| [**discord**](discord/) | **Avisos e comandos pelo celular.** Um servidor em casa trabalha sozinho, e ninguém fica olhando os logs: quando algo dá errado (um backup parado, um disco que não montou), o problema passa despercebido. Um bot do Discord manda esses avisos num canal seu, com botões para resolver na hora, e aceita comandos como `/astro machine:status` ou `/astro nextcloud:restart`. Só os comandos de uma lista fixa funcionam, e só para as contas que você autorizar. |
| [**mailserver**](mailserver/) | **Caixa de e-mail para automações.** Algumas tarefas começam por um e-mail (um boleto, uma fatura, um aviso), mas dar a um programa acesso à sua caixa pessoal expõe todo o resto. Aqui, você encaminha só o que interessa para um endereço próprio no seu domínio (ex.: `inbox@<seu-domínio>`). A Cloudflare recebe esses e-mails e os guarda até o servidor buscá-los, sem nenhuma porta aberta em casa, e eles ficam numa caixa local que as automações leem e que você abre no app Mail do Nextcloud. A caixa só recebe: ela não envia e-mails. |
| [**n8n**](n8n/) | **Automações sem programar.** Muitas rotinas são "quando X acontecer, faça Y": quando chegar um e-mail de cobrança, anote numa planilha; todo dia às 8h, mande um resumo no celular. O n8n monta essas rotinas pelo navegador, ligando blocos prontos (e-mail, Discord, Telegram, planilhas, APIs de centenas de serviços), sem escrever código, e guarda o histórico de cada execução. Aqui ele roda isolado: só na rede local e sem enviar nada à empresa que o desenvolve. |
| [**nextcloud**](nextcloud/) | **Nuvem própria.** Faz o papel do Google Drive, do Google Fotos e da agenda e dos contatos do celular, mas com os dados guardados no seu servidor. Os apps do Nextcloud sincronizam pastas do computador, enviam as fotos do celular sozinhos e permitem compartilhar arquivos por link. |
| [**rclone**](rclone/) | **Cópias de segurança.** Um disco só é um ponto único de falha: se ele quebrar, for roubado ou um arquivo for apagado por engano, os dados somem. O backup mantém outras cópias automaticamente: uma em outro disco da máquina, atualizada toda noite e guardando por um tempo o que foi apagado ou alterado, e outra fora de casa, num armazenamento em nuvem (como o Proton Drive), sincronizada nos dois sentidos de 2 em 2 horas durante o dia. |

## Como usar

Numa máquina com Fedora recém-instalado:

```bash
sudo dnf install -y git
git clone <url-deste-repositório> ~/Projects/astro
~/Projects/astro/setup.sh
```

Depois da primeira instalação, o assistente abre com o comando `astro`, de qualquer pasta (num terminal novo ou
numa nova entrada pelo SSH).

Nos menus, as setas escolhem e Enter confirma. **Esc** volta ao menu anterior; no menu inicial, fecha o assistente.

| Opção | O que faz |
|---|---|
| Instalar Astro | Instala tudo, sempre na mesma ordem: atualiza o sistema (só na primeira vez), prepara a máquina (uma vez), os discos da máquina, `caddy`, `adguard`, `cockpit`, `nextcloud`, `mailserver`, `n8n`, `arcade`, `rclone` e `discord`. Cada projeto usa o que os anteriores já deixaram pronto (o domínio do Caddy, os discos) |
| Reinstalar Astro | O mesmo, com algum projeto já instalado. Antes, mostra todas as etapas (a data de cada concluída, ou "pendente") e pergunta quais rodar: as pendentes, interrompidas ou com falha já vêm marcadas. Esc volta sem rodar nada. Cada projeto refeito pergunta se usa a configuração já salva |
| Gerenciar Astro | Os ajustes do dia a dia de cada projeto instalado (ex.: adicionar rotas no Caddy) e a Administração |
| Modo desenvolvimento | Aparece se o Claude Code estiver instalado: abre o Claude na pasta do repositório, continuando a última conversa (ou começando uma), para desenvolver o Astro. Ao sair do Claude, `astro` abre o assistente de novo |
| Gerenciar Astro → Administração → Discos da máquina | Escolhe os discos que a máquina monta no boot e quais são compartilhados com todos os usuários |
| Gerenciar Astro → Administração → Trocar o domínio | Passa todos os serviços para outro domínio (ex.: `app.<domínio-antigo>` → `app.<domínio-novo>`): mostra o que fazer antes na Cloudflare, troca os endereços salvos (guardando uma cópia da configuração), reaplica cada serviço sem refazer as perguntas e, no fim, lista o que mudar fora da máquina (Tailscale, apps do Nextcloud, favoritos) |
| Gerenciar Astro → Administração → Backup: configurações ➡️ local (agora) | Aparece com o rclone instalado: cria na hora uma versão nova do backup das configurações |
| Gerenciar Astro → Administração → Backup: configurações ⬅️ local (restaurar uma versão) | Aparece com o rclone instalado: escolhe uma versão e os serviços (ou "Todos") e volta a configuração deles para aquele momento |
| Gerenciar Astro → Administração → Implodir Astro | Faz um backup das configurações e desfaz tudo o que o Astro criou na máquina (veja abaixo) |

## Operações e comandos do Discord

Os nomes abaixo aparecem iguais nos menus, nos avisos do Discord e nos logs. No Discord, `/astro command:help`
mostra esta lista.

| Nome | O que é | Quando | Comando no Discord |
|---|---|---|---|
| Backup: local ⬅️ nuvem | download inicial: traz tudo da nuvem para o disco, sem apagar nada | uma vez, ao cadastrar a nuvem | `backup:cloud` (roda a fase atual) |
| Backup: local ↔️ nuvem | mesclagem: junta disco e nuvem, sem apagar nada | depois do download inicial, ou se o estado se perder | `backup:cloud` (roda a fase atual) |
| Backup: local 🔄 nuvem | sincronização: o que é criado, alterado ou apagado de um lado vai para o outro | de 2 em 2 horas, das 08:00 às 20:00 (pula durante os streams do Sunshine) | `backup:cloud` |
| Backup: local 🔄 nuvem (teste) | mostra o que a sincronização apagaria, sem efeito | quando chegar um aviso de exclusões | `backup:cloud-check` |
| Backup: local 🔄 nuvem (liberar exclusões) | libera o limite de 5% numa rodada | depois de conferir o teste | `backup:cloud-force` (pede confirmação) |
| Backup: local ➡️ backup diário | cópia do disco no disco de backup, com as versões do dia (sincroniza com a nuvem antes) | 03:00 | `backup:daily` |
| Backup: configurações ➡️ local | arquivo criptografado de cada serviço | 01:00 | `backup:configs` |
| Backup: Arcade ➡️ local | RetroArch e ES-DE na pasta `Arcade` | 01:00, junto com o das configurações | `backup:arcade` |
| Backup: configurações ⬅️ local | restaura uma versão das configurações | pelo assistente (Administração) | — |
| Mailserver: buscar e-mails | traz para a caixa local os e-mails recebidos na Cloudflare | de 5 em 5 minutos, das 08:00 às 20:00, quando chegou e-mail | `mailserver:fetch` (busca na hora) |
| Máquina: estado | containers, discos e próximos agendamentos | quando quiser | `machine:status` |
| Serviço: iniciar | sobe os containers de um projeto | quando quiser | `<projeto>:start` |
| Serviço: parar | para os containers (ficam parados até o start) | quando quiser | `<projeto>:stop` (pede confirmação) |
| Serviço: reiniciar | reinicia os containers | quando quiser | `<projeto>:restart` (pede confirmação) |
| Ajuda | esta lista | quando quiser | `help` |

## Respondendo a instalação

A máquina é preparada para funcionar como servidor: na primeira instalação, o assistente atualiza o sistema
(se vier um kernel novo, ele pede para reiniciar ao final) e ela nunca suspende nem hiberna, nem ao fechar a
tampa de um notebook, para não perder o acesso remoto.

Rode em um terminal normal: o `sudo` pede senha na primeira vez. Enter aceita o valor sugerido entre
`[ ]`, e respostas em formato inválido (porta, IP, endereço) são recusadas e perguntadas de novo. As
respostas e tudo o que a instalação gera (dados, certificados, logins) ficam em `~/.astro/<projeto>`, fora do
repositório: o repositório tem só o código. Serviços que rodam com outro usuário (ex.: o de jogos) guardam a configuração no `~/.astro`
desse usuário.

### Em todos os projetos

- **Usar a configuração já salva?** Reaproveita as respostas da última instalação. Responda **N** para
  mudar alguma.
- **Quais etapas concluídas reinstalar?** Só aparece no "Reinstalar Astro". Uma etapa (Máquina, Discos da
  máquina ou um projeto) só conta como concluída quando termina sem erro; uma instalação interrompida no meio
  continua de onde parou. Antes da lista, uma linha mostra as pendentes, que sempre rodam. Enter sem marcar nada pula todas as concluídas; marque com Espaço as que quer refazer
  (ou "Todos").

### Máquina

Feita uma vez, no início, para todos os projetos: o comando `astro`, suspensão desligada (inclusive na tela de
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

É a primeira etapa da instalação, antes dos projetos, e também fica em Gerenciar Astro → Administração. Os discos
de dados são da máquina, não de um projeto: o seu usuário é sempre o dono, e os projetos (Nextcloud, rclone,
arcade) só escolhem quais usar. Um disco plugado de passagem (pendrive, HD externo) não precisa entrar aqui: o
Fedora o monta para quem está na tela, e de longe ele é acessado pelo Cockpit (Armazenamento e Arquivos, com o
acesso administrativo ligado).

- **Quais discos a máquina monta?** Marque com Espaço os discos que ficam sempre ligados à máquina. Cada um é
  montado sozinho a cada boot em `/srv/<rótulo>`, mesmo sem ninguém logado, e volta sozinho se for desligado e
  religado. Desmarcar um disco o desmonta (os dados continuam nele), depois de confirmar.
- **Senha do LUKS:** só aparece para um disco criptografado. Ela é pedida uma vez para cadastrar o chip de
  segurança da máquina (TPM), que passa a destravar o disco sozinho a cada boot. Assim a máquina nunca
  para no boot pedindo senha e pode ser reiniciada de longe. Levado para outro computador, o disco
  continua travado. Se um dia ele não destravar sozinho (depois de mexer no Secure Boot, por exemplo), rode
  esta opção de novo: ela pede a senha e cadastra o TPM outra vez.
- **Quais são compartilhados com todos os usuários?** Os marcados ficam abertos a todos os usuários da
  máquina e aparecem no Arquivos (ex.: discos de jogos, que o usuário de jogos também usa). Os outros são
  privados: só o seu usuário entra. Use privado para dados pessoais. A criptografia protege o disco desligado
  ou levado embora; com a máquina ligada, quem decide o acesso é essa resposta.

Depois desta etapa, a máquina confere os discos a cada 15 minutos. Se um deles some (desligado, cabo solto) ou
para de responder (a conexão caiu e voltou com ele em uso), chega um aviso no Discord. No segundo caso, o disco
só volta a funcionar depois de reiniciar a máquina.

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

### arcade

O arcade é a única exceção ao "um usuário só": os jogos rodam num usuário próprio, que entra sozinho no boot e
fica com a tela aberta, enquanto o seu usuário (com os dados sensíveis) nunca fica logado.

- **Senha temporária do Secure Boot:** só aparece se a máquina tiver uma placa NVIDIA sem o driver
  proprietário e o Secure Boot estiver ligado. O driver é instalado automaticamente, mas o Secure Boot só
  aceita o driver depois que você confirma a chave dele na tela azul do próximo boot, digitando essa
  senha. Ela é usada uma única vez, pode ser simples. Esse passo exige teclado e tela na máquina.
- **Nome do usuário de jogos:** o usuário cuja tela é transmitida. É nele que ficam o ES-DE, o RetroArch e as
  configurações deles. Ele é criado sem `sudo`, para que quem estiver jogando não tenha acesso ao homelab.
  Por padrão, `ristar`.
- **Entrar sozinho com o usuário de jogos no boot, sem bloqueio de tela?** Com **S** (padrão), a máquina liga
  direto na sessão de jogos, pronta para o Moonlight, e a tela não bloqueia sozinha (dá para bloquear e
  trocar de usuário à mão). Com **N**, é preciso entrar com ele na tela antes de jogar, e a tela bloqueia
  depois de 5 minutos parada.
- **Senha do usuário de jogos:** para entrar na tela, trocar de usuário e desbloquear. Não dá acesso ao
  `sudo`. Na reinstalação, o assistente pergunta se mantém a atual.
- **Endereço do Sunshine no Caddy:** o nome do painel de administração do Sunshine, onde se pareiam os
  aparelhos. Por padrão, `sunshine.<nome-da-máquina>.<domínio>`, para permitir mais de um Sunshine na rede.
- **Onde está a pasta de mídias do ES-DE?** A pasta com as capas, telas e vídeos dos jogos (uma subpasta por
  sistema). Ela é usada onde está, sem cópia. Escolha com as setas, entrando nas pastas dos discos, ou digite o
  caminho.
- **Onde estão as ROMs?** Uma pasta com uma subpasta por sistema (`snes`, `psx`...). Pode escolher mais de uma
  (ex.: uma por disco): a primeira é a principal do ES-DE, e os sistemas das outras aparecem do mesmo jeito.
  As ROMs também ficam onde estão.
- **Guardar o RetroArch e o ES-DE todas as noites?** Copia, toda noite à 01:00, o que é seu no RetroArch
  (configuração, saves, states, BIOS, capturas e gravações) e no ES-DE (configuração, coleções, gamelists e
  temas) para uma pasta comum. Por padrão, **S**.
  - **Pasta do backup do RetroArch e do ES-DE:** por padrão, `Arcade` ao lado do backup das configurações do
    rclone, dentro da pasta da nuvem: assim a cópia segue para a nuvem e para o disco de backup.
- **Restaurar o RetroArch/ES-DE do backup?** Só aparece numa instalação nova, com o backup cheio. Com **S** (padrão),
  tudo volta como estava, inclusive saves e gamelists.
- **Carregar uma configuração existente do RetroArch?** Só aparece na primeira vez. Com **S**, você escolhe a
  pasta de outra instalação (com `retroarch.cfg`, saves, states, BIOS), que é copiada para o usuário de
  jogos. Uma configuração do Windows serve: caminhos e drivers do Windows são limpos.
- **Carregar uma configuração existente do ES-DE?** Igual, para o ES-DE (a pasta `ES-DE` do Windows também
  serve). As pastas de ROMs e mídias passam a ser as respondidas acima.
- **Carregar gamelists existentes?** Igual, para as gamelists (a lista de jogos com nomes e descrições).

Depois, as mesmas cópias podem ser feitas pelas ações do projeto, em Gerenciar Astro → arcade.

Os discos de jogos (ROMs, emuladores) entram em "Discos da máquina" como **compartilhados**: assim o usuário de
jogos os acessa e eles aparecem no Arquivos dele.

Antes de instalar, ligue uma TV, um monitor ou um plugue HDMI fantasma (um adaptador barato que finge
ser um monitor) na porta HDMI e feche a tampa do notebook. A porta HDMI sai pela placa de vídeo dedicada,
e com uma tela nela o Sunshine captura e codifica o vídeo na própria placa (NVENC), com menos latência.
Sem tela nela, o assistente avisa: o Sunshine usa a placa integrada, e só com a tampa aberta. Durante
cada stream, a tela do servidor muda para a resolução pedida pelo aparelho no Moonlight, se ela aceitar
essa resolução, e volta ao final. Com algo plugado no HDMI, o som da máquina sai por ele; sem nada, sai
pelo notebook (o som do stream não é afetado). Com um plugue HDMI fantasma, a máquina fica em silêncio. No Moonlight, aparecem dois apps: **Desktop** e **ES-DE**. Para o ES-DE ter capa, coloque uma imagem PNG em pé (proporção 2:3) em `~/.config/sunshine/covers/es-de.png` do usuário de jogos e reinstale o arcade. Ao terminar, reinicie a máquina.

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

### discord

- **Token do bot:** a senha da conta do bot. Crie em https://discord.com/developers/applications → **New
  Application** → menu **Bot** → **Reset Token**, e deixe **Public Bot** desligado. O assistente confere o token
  no Discord e não o mostra na tela.
- **ID do canal dos avisos:** o canal onde chegam os avisos e onde o comando `/astro` aparece (de preferência
  um só seu, ex.: `#astro`). Ligue o **Modo desenvolvedor** do Discord (Configurações → Avançado) e use
  **botão direito no canal → Copiar ID do canal**. Antes, convide o bot pelo link que o assistente mostra.
- **IDs dos usuários autorizados:** quem pode usar os comandos e os botões (**botão direito no seu nome →
  Copiar ID do usuário**). Os outros recebem "sem permissão".

No fim, chega uma mensagem de teste com um botão "Máquina: estado". No Discord, digite `/astro` e escolha um
comando (comece por `help`, que mostra a lista de operações; os nomes são em inglês, ex.: `backup:cloud`). Comandos que param ou apagam algo pedem confirmação. No celular, deixe as
notificações do canal em "Todas as mensagens".

### mailserver

- **Endereço da caixa:** o endereço para onde você encaminha os e-mails. Por padrão, `inbox@<domínio do Caddy>`.
  O domínio do endereço não pode ter outro e-mail: ativar o Email Routing nele troca os registros MX, e o e-mail
  que já chegava por eles deixaria de chegar. Use um domínio só do astro.
- **Domínios autorizados:** de quais domínios a caixa aceita e-mails, separados por vírgula (ex.: o domínio do
  seu e-mail, de onde você encaminha). E-mails de outros domínios, ou sem a autenticação da Cloudflare (SPF ou
  DMARC), vão para a pasta **Quarentena**, que nenhuma automação lê. Assim, um e-mail falso enviado ao endereço não
  vira uma conta a pagar. Depois, a lista muda em Gerenciar Astro → mailserver → **Domínios autorizados**, que
  também oferece mover para a entrada o que já estava na Quarentena vindo de um domínio recém-autorizado.
- **Usuário do Nextcloud:** aparece com o Nextcloud instalado. A caixa entra no app **Mail** desse usuário como
  "Astro Inbox". Por padrão, o administrador do Nextcloud.
- **Token da Cloudflare:** um token só deste projeto, com as permissões que o assistente lista (Workers, KV,
  regras e configurações do Email Routing e leitura da zona e do DNS). O assistente mostra como criar e valida o
  token na hora.

A instalação ativa sozinha o Email Routing no domínio do endereço. Se esse domínio já recebe e-mail por outro
serviço, ela para sem mudar nada, porque ativar desviaria esse e-mail.

### n8n

- **Endereço do n8n no Caddy:** o nome pelo qual o n8n é aberto no navegador. Por padrão, `n8n.<domínio>`.
- **E-mail, nome e sobrenome do administrador:** a conta com que você entra no n8n. O e-mail é só o login: o n8n
  não manda e-mails, e o endereço não precisa existir. Por padrão, `n8n@<domínio>`. A conta é criada pela própria instalação, para ninguém na rede tomá-la antes de você no
  primeiro acesso. Para trocar esses dados depois, reinstale o n8n (eles ficam travados na tela do n8n).
- **Senha do administrador:** pelo menos 8 caracteres. Fica guardada só como hash. Ao reinstalar, o assistente
  pergunta se quer trocá-la.

O n8n vem isolado: sem telemetria, sem aviso de versão nova e sem a galeria de modelos, que conversam com os
servidores da empresa. Um modelo do site do n8n ainda pode ser copiado e colado no editor. Ele também não roda
comandos na máquina e só é acessível pela rede local.

### nextcloud

- **Endereço do Nextcloud no Caddy:** o nome pelo qual o Nextcloud é aberto no navegador e configurado nos
  apps. Por padrão, `nextcloud.<domínio>`.
- **Usuário administrador:** a conta que administra o Nextcloud e cria as contas das outras pessoas. Por
  padrão, `astro`. Só vale na primeira instalação.
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
  Gerenciar Astro → rclone. Sem nenhum disco da máquina, não aparece: a cópia da nuvem precisa de um disco.
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
  Por padrão, `Astro/Configurações` dentro da pasta do primeiro armazenamento em nuvem: assim ele segue para a
  nuvem e para o disco de backup nas rodadas seguintes. Sem nenhum disco da máquina, o backup das configurações
  fica desligado até um disco ser cadastrado e o Astro reinstalado.
- **Senha do backup das configurações:** criptografa esse arquivo. **Guarde-a fora da máquina** (num gerenciador
  de senhas): sem ela, o backup não abre. Na reinstalação, o assistente pergunta se mantém a atual.

- **Por quantos dias guardar as versões do backup das configurações:** cada backup fica numa pasta com a data e
  a hora (ex.: `2026-11-10_010000/nextcloud/nextcloud.tar.zst.gpg`); as mais antigas que isso são apagadas. Por
  padrão, `90`.

Os horários: sincronização com a nuvem de 2 em 2 horas, das 08:00 às 20:00 (pulada enquanto houver um stream do Sunshine); 01:00 backup das configurações;
03:00 uma última sincronização com a nuvem e o espelho no disco de backup.

**Restaurar uma versão** (Gerenciar Astro → Administração): mostra as versões da mais nova para a mais antiga e os serviços de
cada uma. Antes de trocar qualquer coisa, o assistente para o rclone (se estiver copiando algo, pergunta antes) e
salva a situação atual como uma versão "antes da restauração", para dar para voltar. Depois, para cada serviço
escolhido: para os containers, troca a configuração pela do backup e sobe de novo. Se a senha atual não abrir a
versão escolhida, ele pede a senha daquela época.

Depois da primeira cópia, **o disco e a nuvem ficam iguais**: o que for criado, alterado ou apagado de um lado
(pelo Nextcloud, pelo app da nuvem ou por quem tem uma pasta compartilhada com você) vai para o outro na
sincronização seguinte. Se o mesmo arquivo mudar dos dois lados, fica o mais novo, e o outro é guardado ao
lado com `.conflict1` no nome. Se uma rodada for apagar mais de 5% dos arquivos, ela para sem apagar nada:
"Backup: local 🔄 nuvem (agora)", no menu do rclone, mostra o aviso e pergunta se libera.

### Implodir Astro

Fica em Gerenciar Astro → Administração. Desfaz tudo o que o Astro criou, na ordem inversa da instalação:
containers, imagens, serviços e a configuração de todos os projetos (`~/.astro`), o usuário de jogos com a home
inteira, a pasta local de arquivos do Nextcloud, as montagens dos discos em `/srv` (o TPM dos discos criptografados
é descadastrado e eles voltam a abrir só com a senha) e os ajustes da máquina feitos para o Astro: suspensão,
firewall, DNS, portas baixas, a rede anunciada no Tailscale e o início automático no boot. Ficam os pacotes
instalados (sistema atualizado, Tailscale, driver da NVIDIA, Cockpit, Sunshine, RetroArch, rclone), os dados dos
discos, o SSH ligado (só volta o login por senha) e o repositório.

- **Para confirmar, digite IMPLODIR:** qualquer outra resposta cancela sem mudar nada.
- **Pasta e senha do backup:** antes de desfazer qualquer coisa, a configuração de cada serviço vai para uma
  versão `antes-de-implodir` do backup das configurações. Com o backup do rclone ligado, usa a pasta e a senha
  dele, sem perguntar. Sem ele, pergunta uma pasta (por padrão, `Astro/Configurações` no primeiro disco da máquina)
  e uma senha. **Guarde a senha fora da máquina.** Depois de reinstalar, use essa pasta como "pasta do backup das
  configurações" do rclone e restaure em Gerenciar Astro → Administração. Se o backup falhar, nada é desfeito.

### Depois de instalar

No roteador, configure o IP do servidor como DNS **primário** entregue pelo DHCP, para todos os aparelhos
da casa passarem pelo AdGuard. Um DNS secundário (o do provedor, por exemplo) mantém a internet
funcionando com o servidor desligado; em troca, alguns aparelhos às vezes consultam o secundário e
escapam do bloqueio.

Com o **mailserver**, crie no seu e-mail um encaminhamento para o endereço da caixa. No Proton: Configurações →
Filtros, um filtro por remetente (ex.: as empresas das contas) com a ação de encaminhar. O Proton manda um e-mail
de confirmação para o endereço novo: ele chega na pasta Quarentena do app Mail do Nextcloud, com o link para
confirmar.

Para criar um projeto novo, veja [lib/README.md](lib/README.md).
