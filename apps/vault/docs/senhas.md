# Backup: as senhas e como restaurar do zero

Cada máquina manda os backups dos apps dela para o vault do Astroverso, num repositório só dela em cada
pasta do vault. Ela tem **três** dados de acesso, mostrados pela ação **Adicionar uma máquina** (e pela **Mostrar os
dados de uma máquina**), junto com o código de ligação (endereço, usuário e pastas do vault, sem segredos):

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

Em qualquer app, **Gerenciar → <app> → Restaurar uma fotografia**:

1. Escolha a pasta do vault (se houver mais de uma) e a data da versão.
2. Antes de trocar, o app guarda a situação atual como uma versão "antes-da-restauracao" (dá para voltar atrás).
3. O app traz a configuração daquela data e se reinstala com as respostas salvas.

## Restaurar uma máquina do zero

Uma máquina nova (ou formatada), com o mesmo nome da antiga:

1. Instale o Astroverso (clone o repositório e rode `./astroverso`).
2. No servidor, se a máquina continua cadastrada, use **Mostrar os dados de uma máquina**. Se foi descadastrada, use
   **Adicionar uma máquina** com o mesmo nome, escolha **Está voltando** e digite a senha do repositório antiga: o
   servidor confere que ela abre os backups que já existem e só gera uma senha de acesso nova.
3. Na máquina, instale o app **backup** e escolha **Só manda os backups dos apps dela para o servidor de outra
   máquina**. Cole o código de ligação, a senha de acesso e a senha do repositório antiga.
4. Para cada app que existia na máquina: instale o app e use **Restaurar uma fotografia**.

Se a máquina perdida era a do **servidor**, instale o app `vault` no modo servidor com as mesmas pastas do vault:
ao achar backups da própria máquina nelas, ele pede a senha do repositório antiga em vez de gerar outra. Depois,
cadastre as outras máquinas com **Adicionar uma máquina → Está voltando**, cada uma com a senha antiga dela. Sem a
senha antiga, a máquina recomeça do zero (os backups antigos ficam na pasta, mas ninguém os abre).

## Abrir um backup à mão (sem o Astroverso)

Os repositórios são do [restic](https://restic.net), um programa livre. Com ele instalado, na máquina do servidor:

```sh
restic -r <pasta do vault>/<nome-da-máquina> snapshots
restic -r <pasta do vault>/<nome-da-máquina> restore <id> --target /tmp/restaurado
```

O restic pede a senha do repositório.
