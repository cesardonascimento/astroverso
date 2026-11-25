# Proton Drive: a conta no app cloud

O app `cloud` entra na sua conta do Proton Drive pelo [rclone](https://rclone.org/protondrive/). A senha fica só na
máquina, ofuscada em `~/.astroverso/cloud/rclone.conf` (`600`), e nunca entra no backup do app.

## Antes de começar

- Entre uma vez pelo site <https://drive.proton.me> antes: o rclone não conclui o primeiro acesso de uma conta nova.
- Tenha o aplicativo autenticador à mão, se a conta usa verificação em duas etapas.

## As perguntas do login

| Pergunta | O que responder |
|---|---|
| E-mail da conta Proton | O e-mail principal da conta |
| Senha da conta Proton | A senha com que você entra no site |
| A conta usa duas senhas? | **Sim** só se você ligou o modo de duas senhas nas configurações da conta: aí ele pede também a senha da caixa de e-mail |
| A conta usa verificação em duas etapas? | Sim, se o site pede um código de 6 dígitos ao entrar. O código vale por alguns segundos: digite o que está na tela do autenticador |

O código das duas etapas só é pedido nesse login. Depois, o rclone guarda a sessão no `rclone.conf` e segue sozinho.

## Quando entrar de novo

A sessão acaba, por exemplo, quando você troca a senha ou encerra as outras sessões pelo site. As rodadas passam a falhar e a verificação avisa no `#cloud`. Para voltar, no
gerenciador: **cloud → Contas na nuvem → Entrar de novo numa conta**. Numa restauração do app, cada conta pede o login
de novo.

## Velocidade

O Proton Drive criptografa cada arquivo no envio: milhares de arquivos pequenos demoram bem mais do que poucos
grandes. O app usa 2 envios e 4 conferências por vez, para não ser barrado por excesso de pedidos.
