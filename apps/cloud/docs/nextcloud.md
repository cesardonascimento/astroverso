# Nextcloud: a conta no app cloud

O app `cloud` entra no Nextcloud pelo WebDAV, com uma **senha de app** só para ele. Assim, uma sincronização como
"pasta do Nextcloud ⇄ Proton Drive" passa toda pelo Nextcloud: ele vê cada arquivo que chega na hora (sem varredura),
os arquivos ficam com o dono certo, e o que a nuvem apagar vai para a lixeira e as versões do Nextcloud.

## Criar a senha de app

1. Abra o Nextcloud (`https://nextcloud.<domínio>`) com o seu usuário.
2. Clique na sua foto (no alto, à direita) → **Configurações pessoais** → **Segurança**.
3. Em **Dispositivos e sessões**, escreva um nome (ex.: `astroverso-cloud`) e clique em **Criar nova senha de app**.
4. Copie a senha mostrada (ela aparece uma vez só) e cole na pergunta "senha de app do Nextcloud" do app cloud.

A senha de app não abre a tela de login e pode ser revogada na mesma página, sem trocar a sua senha.

## As perguntas do login

| Pergunta | O que responder |
|---|---|
| Endereço do Nextcloud | `https://nextcloud.<domínio>` (o padrão) |
| Usuário do Nextcloud | O seu usuário (o mesmo da tela de login) |
| Senha de app do Nextcloud | A senha criada acima |

O app guarda a senha ofuscada no `rclone.conf` do app (`600`), nunca no backup: numa restauração, a conta pede o login
de novo.
