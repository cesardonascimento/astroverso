# Discord: o bot do Astroverso

O app `discord` usa um bot próprio, uma conta do Discord que só o Astroverso usa, num servidor do Discord dedicado
ao Astroverso. Os passos abaixo são feitos uma vez, no site do Discord. O resto (categoria, canais, permissões,
foto do bot) fica com o instalador.

## Criar o bot

1. Abra <https://discord.com/developers/applications> e entre com a sua conta do Discord.
2. Clique em **New Application**, dê um nome (é o nome que aparece no Discord, por exemplo `astro`), aceite os
   termos e clique em **Create**.
3. No menu da esquerda, abra **Installation** e, em **Install Link**, escolha **None**. Assim ninguém mais consegue
   instalar o bot pelo link público da aplicação.
4. Abra **Bot** no menu da esquerda e:
   - desligue **Public Bot**, para só você poder convidar o bot para um servidor (se o Discord reclamar, faça
     antes o passo 3);
   - ligue **Message Content Intent**, em **Privileged Gateway Intents** (veja abaixo);
   - clique em **Save Changes**.
5. Ainda em **Bot**, clique em **Reset Token**, confirme e copie o token. **Ele só aparece uma vez**: guarde no seu
   gerenciador de senhas.

Cole o token quando o instalador pedir. Ele não aparece na tela, o instalador o confere no Discord na hora e o
guarda só nesta máquina, em `~/.astroverso/discord/.env`, com acesso só do seu usuário.

O token é a senha do bot. Se vazar, volte em **Bot** → **Reset Token** e rode **Reinstalar** no `discord`
respondendo que não quer reaproveitar as respostas salvas.

## Ligar a leitura de mensagens

O **Message Content Intent** deixa o bot ler o texto das mensagens nos canais em que um cliente pediu para
escutar (por exemplo, um app que recebe pedidos escritos no canal dele). Sem ele, os avisos, o comando `/astro` e os
botões funcionam normalmente, mas o bot não lê as mensagens.

Para ligar depois da instalação: portal do Discord → sua aplicação → **Bot** → **Message Content Intent** →
**Save Changes**. Depois rode **Reinstalar** no `discord` para o bot passar a usar a permissão.

## Convidar o bot

O bot precisa estar no servidor do Discord que vai ser do Astroverso. Vale criar um servidor novo, só seu: no
Discord, o botão **+** na lista de servidores → **Criar o meu** → **Para mim e meus amigos**.

1. Abra o **convite do bot** que o instalador mostra. Ele já traz as permissões necessárias: ver e mandar
   mensagens, anexar arquivos, reagir, ler o histórico e gerenciar canais e permissões (para criar a categoria
   e os canais).
2. Em **Adicionar ao servidor**, escolha o servidor do Astroverso e clique em **Continuar** e **Autorizar**.
3. Volte ao instalador e responda que já convidou. Se o bot estiver em mais de um servidor, o instalador pergunta
   qual usar.

Na primeira vez que o bot conecta, ele cria no servidor:

| Canal | Para quê |
|---|---|
| Categoria **Astroverso** | Agrupa todos os canais do Astroverso |
| `#astro` | O comando `/astro` (ajuda, painel e as ações dos apps) |
| `#sistema` | Avisos gerais, sem um app específico |
| `#<app>` | Um por app, criado no primeiro aviso dele (`#network`, `#discord`...). Só o bot escreve |

Se você já tiver uma categoria chamada **Astroverso** ou canais com esses nomes, o bot usa os que existem e só
ajusta as permissões.

## Copiar IDs

Só quem estiver autorizado usa os comandos, os botões e as mensagens do bot. O dono do servidor sempre entra. Para
autorizar mais alguém, o instalador pede o **ID** da pessoa:

1. No Discord, abra **Configurações de usuário** → **Avançado** e ligue o **Modo desenvolvedor**.
2. Clique com o botão direito no nome da pessoa (na lista de membros ou numa mensagem) → **Copiar ID do usuário**.

O ID é um número de 17 a 20 dígitos.
