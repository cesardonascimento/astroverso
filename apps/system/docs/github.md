# GitHub: chave desta máquina

O app `system` pode criar uma chave SSH própria desta máquina (`~/.ssh/id_ed25519`, sem senha). Cadastrada na sua
conta do GitHub, ela deixa a máquina baixar e atualizar repositórios por SSH (`git@github.com:...`), inclusive os
privados, sem pedir senha a ninguém. Isso vale também para rotinas automáticas, como um timer que faz `git pull`.

A chave é **da máquina**: cada PC tem a sua, e você cadastra uma por PC. Se um PC for perdido ou formatado, basta
apagar a chave dele no GitHub.

## Cadastrar a chave

1. Copie a linha que o instalador mostra. Ela começa com `ssh-ed25519` e termina com `<usuário>@<nome-da-máquina>`.
   Para ver de novo depois: `cat ~/.ssh/id_ed25519.pub`, ou a ação **Chave desta máquina para o GitHub**.
2. Abra <https://github.com/settings/keys> (foto da conta → **Settings** → **SSH and GPG keys**).
3. Clique em **New SSH key**.
4. Em **Title**, coloque o nome desta máquina. Em **Key type**, deixe **Authentication Key**.
5. Em **Key**, cole a linha inteira e clique em **Add SSH key**. O GitHub pode pedir a sua senha ou o segundo
   fator.
6. Volte ao instalador e responda que já cadastrou. Ele confere com `ssh -T git@github.com`.

## Remover a chave

Em <https://github.com/settings/keys>, clique em **Delete** na chave da máquina. Faça isso quando um PC for
perdido, vendido ou formatado: quem estiver com ele não consegue mais usar os seus repositórios.

## Só um repositório (opcional)

Se preferir que a máquina enxergue um único repositório, cadastre a mesma linha como **Deploy key** do repositório
(**Settings** do repositório → **Deploy keys** → **Add deploy key**), em vez de na sua conta. O GitHub não aceita a
mesma chave como chave da conta e como deploy key ao mesmo tempo.
