# Nextcloud: a pasta dos backups

O app `vault` envia os backups dos apps para uma pasta dentro do Nextcloud pelo WebDAV, com uma **senha de app** só para
ele, como o app do celular envia uma foto. Assim, o Nextcloud vê cada backup que chega na hora, com o dono certo, com
lixeira e versões, e a pasta entra em tudo o que já protege os arquivos do Nextcloud (a fotografia do disco, uma
sincronização com a nuvem).

## Criar a senha de app

1. Abra o Nextcloud (`https://nextcloud.<domínio>`) com o seu usuário.
2. Clique na sua foto (no alto, à direita) → **Configurações pessoais** → **Segurança**.
3. Em **Dispositivos e sessões**, escreva um nome (ex.: `astroverso-vault-<nome-da-máquina>`) e clique em **Criar nova
   senha de app**.
4. Copie a senha mostrada (ela aparece uma vez só) e cole na pergunta "senha de app do Nextcloud" do app vault.

A senha de app não abre a tela de login e pode ser revogada na mesma página, sem trocar a sua senha. Use uma por máquina.

## As perguntas

| Pergunta | O que responder |
|---|---|
| Endereço do Nextcloud | `https://nextcloud.<domínio>` (o padrão) |
| Usuário do Nextcloud | O seu usuário (o mesmo da tela de login) |
| Senha de app do Nextcloud | A senha criada acima |
| Pasta dos backups no Nextcloud | Ex.: `/Backups`; criada se não existir. Todas as máquinas podem usar a mesma: cada uma fica numa subpasta com o nome dela |
| Senha dos backups | Criptografa cada arquivo. Guarde no seu gerenciador de senhas: sem ela, ninguém abre os backups (nem você) |

## Restaurar do zero

Numa máquina nova (ou reinstalada): instale o app `vault` com a mesma pasta e a **mesma senha dos backups**, depois o app
que quer recuperar e, nele, **Restaurar uma versão**. Os backups ficam em `<pasta>/<nome-da-máquina>/<AAAA-MM-DD>/`: use
o mesmo nome de máquina.
