# Backup: as senhas e como restaurar do zero

Cada máquina manda os backups dos apps dela para o servidor de backup do Astroverso, num repositório só dela. Ela
tem **três** dados de acesso, mostrados pela ação **Adicionar uma máquina** (e pela **Mostrar os dados de uma
máquina**):

| Dado | Para que serve | Se perder |
|---|---|---|
| Usuário | O nome da máquina no servidor | Está no nome da máquina |
| Senha de acesso | Deixa a máquina entrar no servidor e **acrescentar** versões (nunca apagar) | O servidor gera outra (descadastrar e cadastrar de novo) |
| **Senha do repositório** | **Criptografa os backups.** Sem ela, ninguém abre as versões: nem você, nem o servidor | **Os backups daquela máquina viram lixo.** Não há como recuperar |

## Guarde a senha do repositório no seu gerenciador de senhas

Crie uma entrada por máquina (ex.: "Astroverso backup — <nome-da-máquina>") com o endereço, o usuário e as duas
senhas. O servidor também guarda as senhas (para a manutenção semanal), mas, se a máquina do servidor for perdida, é
o gerenciador de senhas que salva os backups.

## Restaurar um app

Em qualquer app, **Gerenciar → <app> → Restaurar uma versão**:

1. Escolha a data da versão.
2. Antes de trocar, o app guarda a situação atual como uma versão "antes-da-restauracao" (dá para voltar atrás).
3. O app traz a configuração daquela data e se reinstala com as respostas salvas.

## Restaurar uma máquina do zero

Uma máquina nova (ou formatada), com o mesmo nome da antiga:

1. Instale o Astroverso (clone o repositório e rode `./astroverso`).
2. Instale o app **backup** e escolha **Só manda os backups dos apps dela para o servidor de outra máquina**. Cole o
   endereço, o usuário e as duas senhas do gerenciador de senhas.
3. Para cada app que existia na máquina: instale o app e use **Restaurar uma versão**.

Se a máquina perdida era a do **servidor**, restaure primeiro o app `backup` no modo servidor apontando para a mesma
pasta dos repositórios (o disco de backup) e cadastre as máquinas de novo com **Adicionar uma máquina**. Os
repositórios continuam lá; as senhas novas de acesso não mudam as senhas dos repositórios, que vêm do gerenciador.

## Abrir um backup à mão (sem o Astroverso)

Os repositórios são do [restic](https://restic.net), um programa livre. Com ele instalado, na máquina do servidor:

```sh
restic -r <pasta dos backups>/<nome-da-máquina> snapshots
restic -r <pasta dos backups>/<nome-da-máquina> restore <id> --target /tmp/restaurado
```

O restic pede a senha do repositório.
