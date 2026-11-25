# Encaminhar e-mails para a caixa

A caixa do Astroverso (ex.: `inbox@<domínio>`) é só de entrada: ela recebe o que você **encaminha** do seu e-mail de
sempre. O jeito recomendado é um **filtro** que encaminha só os e-mails que interessam às automações (contas,
boletos, faturas), e não o e-mail inteiro.

Nos exemplos, `<caixa>` é o endereço da caixa. O instalador mostra o valor certo.

## Antes de começar: o domínio autorizado

Só entram na entrada da caixa e-mails com remetente comprovado (SPF ou DMARC) e de um **domínio autorizado**. Num
encaminhamento, o remetente que conta é **quem encaminha**: no Gmail, o seu endereço `@gmail.com`; no Outlook,
`@outlook.com` ou `@hotmail.com`; num e-mail com domínio próprio, o seu domínio. Coloque esse domínio na pergunta
**domínios autorizados** da instalação (ou na ação **Domínios autorizados**). O resto vai para a pasta
**Quarentena** da caixa, sem se perder.

## Gmail

O Gmail exige confirmar o endereço antes de encaminhar para ele.

### 1. Cadastrar a caixa como endereço de encaminhamento

1. No Gmail pelo computador, clique na engrenagem → **Ver todas as configurações**.
2. Aba **Encaminhamento e POP/IMAP** → **Adicionar um endereço de encaminhamento**.
3. Digite `<caixa>` → **Próximo** → **Continuar** → **OK**. O Gmail manda um código de confirmação para a caixa.
4. **Não** marque "Encaminhar uma cópia dos e-mails recebidos": isso mandaria tudo. O encaminhamento fica só no filtro.

### 2. Pegar o código de confirmação (ele cai na Quarentena)

O e-mail de confirmação vem de `forwarding-noreply@google.com`. Como o domínio `google.com` não está na lista de
autorizados, ele vai para a **Quarentena** da caixa:

1. Espere a próxima busca (até 5 minutos, das 08:00 às 20:00) ou rode a ação **Buscar os e-mails agora** do app `mail`.
2. No Nextcloud, abra o app **Mail** → a conta da caixa → pasta **Quarentena**.
3. Abra o e-mail "(#...) Confirmação de encaminhamento do Gmail" e copie o código (ou clique no link).
4. Volte à aba **Encaminhamento e POP/IMAP** do Gmail, cole o código e clique em **Verificar**.

### 3. Criar o filtro

1. Na barra de busca do Gmail, clique no ícone de opções (à direita).
2. Preencha o que identifica os e-mails. Exemplos:
   - **De:** `faturas@empresa.com.br` (um remetente);
   - **Contém as palavras:** `boleto OR fatura OR "segunda via"`.
3. Clique em **Criar filtro**.
4. Marque **Encaminhar para** e escolha `<caixa>`. Se quiser, marque também **Aplicar o filtro às conversas
   correspondentes** (só marca; o Gmail não reencaminha e-mails antigos).
5. Clique em **Criar filtro**.

Para mandar um e-mail antigo à caixa, abra-o e use **Encaminhar** normalmente, para `<caixa>`.

## Outlook (Outlook.com e Hotmail)

1. No Outlook pela web, engrenagem → **Email** → **Regras** → **Adicionar nova regra**.
2. Dê um nome (ex.: `Astroverso contas`).
3. Em **Adicionar uma condição**, escolha, por exemplo, **De** (o remetente) ou **O assunto inclui** (ex.: `fatura`).
4. Em **Adicionar uma ação**, escolha **Encaminhar para** e digite `<caixa>`.
5. Clique em **Salvar**.

O Outlook não pede confirmação do endereço. Algumas contas novas têm o encaminhamento automático bloqueado por um
tempo: se a regra não encaminhar, tente de novo em alguns dias.

## Conferir

1. Mande para você mesmo um e-mail que o filtro pega (ou encaminhe um à mão).
2. Rode **Buscar os e-mails agora** no app `mail` (ou espere até 5 minutos, das 08:00 às 20:00).
3. O e-mail aparece na entrada da caixa, no Nextcloud Mail. Se foi para a **Quarentena**, falta autorizar o domínio
   de quem encaminhou (ação **Domínios autorizados**, que oferece mover os e-mails dele para a entrada).
