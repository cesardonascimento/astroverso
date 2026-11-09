# astro

Homelab em containers (Podman), versionado para reinstalar tudo em minutos em qualquer máquina
se algo der errado. Domínio, IPs, portas e senhas não ficam no código: são perguntados durante a
instalação.

| Projeto | Para que serve |
|---|---|
| [**adguard**](adguard/) | **Servidor DNS da rede.** Todo aparelho pergunta ao DNS qual é o endereço de cada site antes de acessá-lo. Com o AdGuard nesse papel, anúncios, rastreadores e domínios maliciosos são bloqueados para a casa inteira, sem instalar nada nos aparelhos. Ele também responde os nomes internos dos seus serviços (ex.: `*.<seu-domínio>`) com o IP do servidor. |
| [**caddy**](caddy/) | **Proxy reverso com HTTPS.** As aplicações da rede escutam em portas diferentes (`http://<ip>:3000`, `http://<ip>:8080`...). O Caddy recebe os acessos por nome (`https://app.<seu-domínio>`) e encaminha cada um para a aplicação e a porta certas, em qualquer máquina da rede. Assim ninguém precisa decorar IPs e portas, e todo serviço ganha HTTPS com certificado válido do Let's Encrypt, emitido e renovado automaticamente. |
| [**cockpit**](cockpit/) | **Painel de administração do servidor pelo navegador.** Mostra uso de CPU, memória e disco, logs, serviços e atualizações do sistema, abre um terminal e gerencia os containers (ver logs, reiniciar, parar). Serve para cuidar do servidor sem SSH, inclusive pelo celular. |
| [**nextcloud**](nextcloud/) | **Nuvem própria.** Faz o papel do Google Drive, do Google Fotos e da agenda e dos contatos do celular, mas com os dados guardados no seu servidor. Os apps do Nextcloud sincronizam pastas do computador, enviam as fotos do celular sozinhos e permitem compartilhar arquivos por link. |
| [**rclone**](rclone/) | **Cópias de segurança.** Um disco só é um ponto único de falha: se ele quebrar, for roubado ou um arquivo for apagado por engano, os dados somem. O backup mantém outras cópias automaticamente: uma em outro disco da máquina, atualizada toda noite e guardando por um tempo o que foi apagado ou alterado, e outra fora de casa, num armazenamento em nuvem (como o Proton Drive), atualizada a cada 15 minutos. |
| [**sunshine**](sunshine/) | **Servidor de jogos remoto.** Transmite a tela, o áudio e os controles de um computador para outro aparelho pela rede, com pouca latência: você joga na TV, no celular ou no notebook, mas quem roda o jogo (ou o emulador) é o servidor. Funciona com o app Moonlight. Os jogos ficam em um usuário próprio, que pode entrar sozinho no boot, separado do usuário que cuida do homelab. |

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

A máquina é preparada para funcionar como servidor: antes de instalar, o assistente atualiza o sistema uma vez
(se vier um kernel novo, ele pede para reiniciar ao final) e ela nunca suspende nem hiberna, nem ao fechar a
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

### nextcloud

- **Endereço do Nextcloud no Caddy:** o nome pelo qual o Nextcloud é aberto no navegador e configurado nos
  apps. Por padrão, `nextcloud.<domínio>`.
- **Usuário administrador:** a conta que administra o Nextcloud e cria as contas das outras pessoas. Por
  padrão, `astro`. Só vale na primeira instalação.
- **Pasta dos arquivos:** onde ficam os arquivos enviados ao Nextcloud. Por padrão, a pasta oculta `.nextcloud`
  no home do seu usuário, fora do projeto. Se ela mudar depois de instalado, o assistente pergunta se pode **mover os arquivos** para a
  pasta nova.
- **Quais discos guardam arquivos do Nextcloud?** Marque com Espaço os discos de dados que o Nextcloud vai usar.
  Ao reconfigurar, os discos atuais já vêm marcados: marque um novo para adicionar, desmarque para tirar.
  Cada um é montado sozinho a cada boot, só o seu usuário e o Nextcloud acessam, e ele aparece no Nextcloud
  como uma pasta com o nome do disco. Arquivos copiados para o disco por fora também aparecem lá. A escolha
  fica gravada pelo identificador do disco, então numa máquina nova os mesmos discos são reconhecidos.
- **Senha do LUKS:** só aparece para um disco criptografado. Ela é pedida uma vez para cadastrar o chip de
  segurança da máquina (TPM), que passa a destravar o disco sozinho a cada boot. Assim a máquina nunca
  para no boot pedindo senha e pode ser reiniciada de longe. Levado para outro computador, o disco
  continua travado. Se um dia ele não destravar sozinho (depois de mexer no Secure Boot, por exemplo), rode
  a instalação de novo: ela pede a senha e cadastra o TPM outra vez.
- **Senha do administrador:** só aparece na primeira instalação, depois que o Nextcloud termina de instalar
  (alguns minutos). Se o Nextcloud a recusar, por ser curta ou já ter vazado em algum site, ele pede outra.

### rclone

- **Qual disco recebe o espelho noturno?** Marque com Espaço o disco que guarda a cópia local (um só). Ele é
  montado sozinho a cada boot e só o seu usuário acessa. Deixe vazio para fazer só a cópia na nuvem.
- **Qual disco copiar para ele toda noite?** O disco de dados que vai ser protegido, por exemplo o do
  Nextcloud.
- **Por quantos dias guardar o que for apagado ou alterado:** cada noite, o que mudou ou sumiu vai para uma
  pasta com a data, em vez de ser perdido. Passado esse prazo, a pasta é apagada. Por padrão, `30`.
- **Adicionar um armazenamento em nuvem agora?** Liga a cópia fora de casa. Dá para adicionar depois, em
  "Configurar um projeto instalado".
  - **Qual armazenamento em nuvem?** O serviço. Hoje, o Proton Drive.
  - **Nome do armazenamento** e **pasta dentro do disco:** onde a cópia da nuvem fica no disco. Por padrão,
    uma pasta com o nome do serviço (ex.: `proton`). A raiz do disco não é aceita, para caber mais de um
    serviço.
  - **E-mail, senha e código da verificação em duas etapas:** o login no serviço. Se você ligar a verificação
    em duas etapas depois, use "Reconectar a um armazenamento em nuvem".
  - **Quando fazer a primeira cópia?** Traz tudo o que já está na nuvem para o disco. Pode levar horas: escolha
    agora, um horário (por exemplo de madrugada) ou depois, pelo menu. Se ela for interrompida (internet,
    reboot, falta de luz), continua sozinha de onde parou.

Depois da primeira cópia, **o disco manda**: o que você criar ou mudar chega à nuvem em até 15 minutos, e o
que apagar é apagado lá à noite. Mexa nos arquivos pelo Nextcloud, não pelo app da nuvem: o que for criado
só na nuvem é apagado no espelho noturno.

### sunshine

- **Senha temporária do Secure Boot:** só aparece se a máquina tiver uma placa NVIDIA sem o driver
  proprietário e o Secure Boot estiver ligado. O driver é instalado automaticamente, mas o Secure Boot só
  aceita o driver depois que você confirma a chave dele na tela azul do próximo boot, digitando essa
  senha. Ela é usada uma única vez, pode ser simples. Esse passo exige teclado e tela na máquina.
- **Nome do usuário de jogos:** o usuário cuja tela é transmitida. É nele que ficam os emuladores, os jogos
  e as configurações. Ele é criado sem `sudo`, para que quem estiver jogando não tenha acesso ao homelab.
  Por padrão, `jogos`.
- **Entrar sozinho com o usuário de jogos no boot, sem bloqueio de tela?** Com **S** (padrão), a máquina liga
  direto na sessão de jogos, pronta para o Moonlight, e a tela não bloqueia sozinha (dá para bloquear e
  trocar de usuário à mão). Com **N**, é preciso entrar com ele na tela antes de jogar, e a tela bloqueia
  depois de 5 minutos parada.
- **Senha do usuário de jogos:** para entrar na tela, trocar de usuário e desbloquear. Não dá acesso ao
  `sudo`. Na reinstalação, o assistente pergunta se mantém a atual.
- **Endereço do Sunshine no Caddy:** o nome do painel de administração do Sunshine, onde se pareiam os
  aparelhos. Por padrão, `sunshine.<nome-da-máquina>.<domínio>`, para permitir mais de um Sunshine na rede.
- **Quais discos são de jogos?** Marque com Espaço os discos com jogos, ROMs e emuladores (ao reconfigurar, os
  atuais já vêm marcados). Eles são montados
  sozinhos a cada boot e ficam acessíveis ao seu usuário e ao usuário de jogos, e a nenhum outro. Os discos
  já escolhidos pelo Nextcloud não aparecem na lista.

Antes de instalar, ligue uma TV, um monitor ou um plugue HDMI fantasma (um adaptador barato que finge
ser um monitor) na porta HDMI e feche a tampa do notebook. A porta HDMI sai pela placa de vídeo dedicada,
e com uma tela nela o Sunshine captura e codifica o vídeo na própria placa (NVENC), com menos latência.
Sem tela nela, o assistente avisa: o Sunshine usa a placa integrada, e só com a tampa aberta. Durante
cada stream, a tela do servidor muda para a resolução pedida pelo aparelho no Moonlight, se ela aceitar
essa resolução, e volta ao final. Os alto-falantes do notebook ficam mudos para o usuário de jogos, para a
máquina não fazer barulho ligada o dia todo (o som do stream não é afetado). Ao terminar, reinicie a máquina.

### Depois de instalar

No roteador, configure o IP do servidor como DNS **primário** entregue pelo DHCP, para todos os aparelhos
da casa passarem pelo AdGuard. Um DNS secundário (o do provedor, por exemplo) mantém a internet
funcionando com o servidor desligado; em troca, alguns aparelhos às vezes consultam o secundário e
escapam do bloqueio.

Para criar um projeto novo, veja [lib/README.md](lib/README.md).
