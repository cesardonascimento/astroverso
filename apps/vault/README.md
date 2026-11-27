# vault

Os backups dos apps desta máquina. Cada app guarda todo dia a própria configuração (respostas, senhas, bancos) num
arquivo criptografado e o envia para **uma pasta dentro do Nextcloud**, pelo WebDAV, com uma senha de app: o Nextcloud
recebe cada arquivo como se você o enviasse (dono certo, lixeira, versões), e a pasta entra em tudo o que já protege os
arquivos dele (a fotografia do disco, uma sincronização com a nuvem). **Quem manda é cada app** (`kit.vault`): o app
`vault` só guarda a ligação com o Nextcloud e a senha dos backups. O aviso sai no canal `#vault` do Discord.

```
app (timer astroverso-<app>-backup, 01:MM)
  └─ backup(pasta) em ~/.astroverso/.backups/<app>/
       └─ tar --zstd + gpg (senha dos backups) ──WebDAV──▶ Nextcloud: <pasta>/<máquina>/<AAAA-MM-DD>/<app>.tar.zst.gpg
```

- Um arquivo por app por dia (o "Fazer backup agora" do mesmo dia substitui o anterior), guardados por 90 dias.
- Os arquivos dos usuários do Nextcloud e os discos não entram aqui: ficam com a fotografia do disco (app `disks`).
- Outras máquinas mandam para a mesma pasta, cada uma na subpasta com o nome dela.
- Passo a passo da senha de app e das perguntas: [nextcloud.md](docs/nextcloud.md).

## Instalação

| Etapa | O que faz |
|---|---|
| Pacotes | `gnupg2` e `zstd` (pela camada `kit.distro`) |
| Nextcloud | Endereço (padrão `https://nextcloud.<domínio>`), usuário, pasta dos backups (padrão `/Backups`, criada se faltar) e a senha de app, conferida antes de gravar (três tentativas) |
| Senha dos backups | Criptografa cada arquivo; guarde no gerenciador de senhas. Na reinstalação, fica a mesma |
| Mudanças no sistema | O backup diário do próprio app |

## Mudanças

| Mudança | Por quê |
|---|---|
| Pacotes `gnupg2` e `zstd` | Criptografar e compactar os backups |
| `~/.astroverso/vault.env` (`600`: endereço, usuário, senha de app, pasta, senha dos backups) | A ligação usada por todos os apps desta máquina (`kit.vault`) |
| `~/.astroverso/vault/` (`.env` vazio) | A marca de instalado e as respostas das mudanças |
| Unidades do usuário `astroverso-vault-backup.timer` e `.service` (perguntada) | O backup do próprio app |

| Fora da máquina | Por quê |
|---|---|
| Senha de app no Nextcloud (uma por máquina) | O envio pelo WebDAV sem a sua senha de login |
| A senha dos backups no seu gerenciador de senhas | Sem ela, ninguém abre os backups |

## Ações

| Ação | O que faz |
|---|---|
| Resumo dos backups | Nextcloud, usuário, a pasta desta máquina e se ele responde. Também no Discord |
| Mudanças no sistema | O backup diário do próprio app |
| Testar o envio | Confere a ligação e envia um backup de teste (`vault-teste.tar.zst.gpg`). Também no Discord |
| Trocar a senha dos backups | Vale a partir do próximo backup; os antigos continuam abrindo só com a senha antiga |
| Fazer backup agora / Restaurar uma versão | O backup do próprio app |

Em cada app: **Fazer backup agora** e **Restaurar uma versão** (escolhe a data; guarda antes um backup
"antes-da-restauracao").

## Remover

Desfaz as mudanças e apaga a ligação (`vault.env`). Os backups que já estão no Nextcloud **ficam**.

## Backup do próprio app

Só o `.env` vazio: a senha de app e a senha dos backups ficam de fora de propósito.
