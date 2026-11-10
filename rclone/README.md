# rclone

Espelha os discos de dados em outro disco da máquina e em armazenamentos em nuvem, com o
[rclone](https://rclone.org). Não usa container: são agendamentos (timers) do systemd do usuário, que rodam
mesmo sem ninguém logado.

```bash
./project.sh install           # disco de backup, agendamentos e (opcional) o primeiro armazenamento em nuvem
./project.sh remove [--purge]  # tira os agendamentos e libera o disco; --purge apaga também os logins da nuvem
```

## Perguntas da instalação

| Pergunta | Padrão |
|---|---|
| Qual disco recebe o espelho noturno? | (nenhum marcado: só nuvem) |
| Qual disco copiar para ele toda noite? | o primeiro disco de dados de outro projeto |
| Por quantos dias guardar o que for apagado ou alterado | `30` |
| Adicionar um armazenamento em nuvem agora? | `S` |

Ao adicionar um armazenamento em nuvem (na instalação ou pelo menu):

| Pergunta | Padrão |
|---|---|
| Qual armazenamento em nuvem? | lista de `providers/` |
| Nome do armazenamento | o do serviço (ex.: `proton`) |
| Em qual disco guardar a cópia | o disco copiado toda noite |
| Pasta dentro do disco | o nome do armazenamento (a raiz do disco nunca é aceita) |
| Perguntas do serviço | Proton Drive: e-mail, senha e código da verificação em duas etapas (Enter se não usa) |
| Quando fazer a primeira cópia da nuvem para o disco? | agora, num horário (`HH:MM`) ou depois, pelo menu |

## Agendamentos

| Unidade | Quando | O que faz |
|---|---|---|
| `astro-rclone-tick` | a cada 30 minutos, das 08:00 às 20:00 | Sincroniza cada armazenamento nos dois sentidos (`rclone bisync`). Enquanto a primeira cópia não termina, faz ou retoma essa cópia no lugar da sincronização |
| `astro-rclone-config` | 01:00 | Backup das configurações: cada `~/.astro/<serviço>` (com os ajustes de cada projeto, como dumps de banco) em `<serviço>/<serviço>.tar.zst.gpg`, criptografado (AES-256, senha da instalação), na pasta escolhida |
| `astro-rclone-local` | 03:00 | Uma sincronização com a nuvem e, em seguida (mesmo se ela falhar), o espelho do disco inteiro em `<disco de backup>/atual`, guardando dono e permissões (`podman unshare rclone sync --metadata`). O que for apagado ou alterado vai para `<disco de backup>/versoes/<data>/`, apagado depois do prazo |
| `astro-rclone-import-<nome>` | o horário escolhido | Temporário (`systemd-run`): começa a primeira cópia agendada. Se a máquina reiniciar antes, a primeira cópia começa na sincronização seguinte |

Todos têm `Persistent=true`: se a máquina estava desligada na hora, rodam logo depois de ligar.

## Sincronização nos dois sentidos

Depois da primeira cópia, a pasta no disco (`<disco>/<pasta>`) e a nuvem ficam iguais: o que for criado,
alterado ou apagado de um lado vai para o outro na rodada seguinte. Serve para pastas que outras pessoas
mexem pela nuvem (ex.: uma pasta compartilhada da empresa). O `rclone bisync` guarda a lista de arquivos da
última rodada (em `~/.cache/rclone/bisync`) para saber o que mudou de cada lado.

| Situação | O que acontece |
|---|---|
| Arquivo alterado dos dois lados entre duas rodadas | Fica o mais novo; o outro é guardado ao lado como `<nome>.conflict1` (`--conflict-resolve newer --conflict-loser num`) |
| Rodada interrompida (internet, reboot) | A seguinte continua sozinha (`--resilient --recover`) |
| Primeira rodada, ou estado perdido | Junta os dois lados sem apagar nada (`--resync --resync-mode newer`, o mais novo vence). Arquivos apagados de um lado só voltam a aparecer |
| Mais de 5% dos arquivos para apagar | A rodada para sem apagar nada (`--max-delete 5`) e as seguintes também. "Sincronizar agora" mostra o aviso e pergunta se libera as exclusões naquela rodada (`--force`) |

Renomear ou mover uma pasta grande, para o rclone, é apagar uma e criar outra: pode passar dos 5%.

## Travas

- Nada roda se o disco não estiver montado. Sem o disco, a pasta fica vazia, e espelhar uma pasta vazia
  apagaria a nuvem inteira.
- Nada é enviado nem apagado na nuvem antes de a primeira cópia terminar sem erro.
- O que for apagado ou alterado no disco, venha de onde vier, fica em `<disco de backup>/versoes/<data>/` pelo
  prazo escolhido (só o que existia no espelho das 03:00 anterior).
- A primeira cópia continua de onde parou depois de uma queda de internet, reboot ou falta de luz: o rclone
  pula o que já está igual e grava cada arquivo com nome temporário até terminar.
- Uma rodada por vez (`flock`): a sincronização de 30 minutos pula a vez se outra estiver rodando; a das 03:00
  espera.
- A sincronização para se for apagar mais de 5% dos arquivos (veja acima).

## Avisos no Discord

Com o projeto `discord` instalado, o rclone avisa, no máximo uma vez por dia por problema, e de novo quando ele
se resolve:

| Aviso | Quando |
|---|---|
| Sincronização parada pelo limite de exclusões | Mais de 5% dos arquivos seriam apagados. Botões: "Ver o que seria apagado" e "Liberar exclusões" (com confirmação) |
| Sincronização falhando | 3 falhas seguidas (a contagem fica em `FAILURES` no `targets/<nome>.env`). Botão "Tentar de novo" |
| Estado da sincronização perdido | O rclone vai juntar os dois lados de novo (arquivos apagados podem voltar) |
| Disco não montado | Nada é copiado nem apagado até ele voltar |
| Espelho no disco de backup falhou | Rodada das 03:00 |
| Backup das configurações falhou | Algum serviço não foi salvo. Botão "Tentar de novo" |

Comandos no Discord (`/astro command:rclone:<ação> argument:<armazenamento>`; com um só armazenamento, o
argumento pode ficar de fora):

| Ação | O que faz |
|---|---|
| `sync` | Começa uma sincronização em segundo plano |
| `show-deletes` | Teste sem efeito (`./run.sh preview <nome>`, `bisync --dry-run --force`): quantos arquivos seriam apagados de cada lado, por pasta |
| `allow-deletes` | Com confirmação: libera o limite na próxima sincronização e a começa |
| `backup-configs` | Backup das configurações agora |

## Backup das configurações

À 01:00, antes dos espelhos, o `astro-rclone-config`:

1. pede a cada projeto que tenha o comando `backup` as cópias consistentes (dump do Postgres do Nextcloud,
   cópia do SQLite do Home Assistant) e o que deixar de fora (bancos em uso, código, caches);
2. empacota cada `~/.astro/<serviço>` com `podman unshare tar` (guarda os donos dos arquivos dos containers),
   com caminhos relativos ao serviço, sem o home: dentro do arquivo fica só a pasta `<serviço>/`. O que o projeto
   inclui de fora vai para uma subpasta com nome fixo (ex.: `sunshine/usuario`, com o `~/.astro/sunshine` do usuário
   de jogos, lido por ACL, sem os logs). O `host.env` vira `host/`;
3. compacta (`zstd`), criptografa com `gpg --symmetric` (AES-256) e grava
   `<pasta escolhida>/<AAAA-MM-DD_HHMMSS>/<serviço>/<serviço>.tar.zst.gpg`, uma pasta por backup;
4. apaga as versões com mais de `CONFIG_KEEP_DAYS` dias (padrão 90; só pastas com nome de versão). Na pasta do armazenamento em nuvem, isso segue para a nuvem
   e para o disco de backup nas rodadas seguintes.

```
Astro/Configurações/
  2026-11-10_010000/
    caddy/caddy.tar.zst.gpg
    nextcloud/nextcloud.tar.zst.gpg
    ...
    host/host.tar.zst.gpg
  2026-11-10_154512_antes-da-restauracao/
    ...
```

A parte de outro usuário (ex.: `sunshine/usuario`) é gravada como do usuário que instala (`--owner=0`): a
restauração devolve o dono certo.

Para abrir um serviço: `gpg -d <serviço>.tar.zst.gpg | tar --zstd -xf -` (pede a senha). Para manter os donos dos
arquivos dos containers, extrair com `podman unshare tar --zstd -x --numeric-owner`.

## Ações (Configurar um projeto instalado)

| Ação | O que faz |
|---|---|
| Ver as últimas execuções | Estado de cada armazenamento, próximos agendamentos e as últimas mensagens |
| Sincronizar agora | Roda a sincronização já (ou a primeira cópia pendente). Se a última parou por excesso de exclusões, pergunta se libera |
| Adicionar armazenamento em nuvem | As perguntas acima |
| Reconectar a um armazenamento em nuvem | Refaz o login (ex.: depois de ligar a verificação em duas etapas) |
| Remover armazenamento em nuvem | Tira o login e o agendamento; os arquivos ficam no disco e na nuvem |
| Fazer backup das configurações agora | Também no menu principal: roda o backup das configurações na hora |
| Restaurar uma versão das configurações | Também no menu principal: veja abaixo |

## Restaurar uma versão

1. Lista as versões em `<pasta do backup>` (da mais nova para a mais antiga, com os serviços de cada uma) e
   pede os serviços a restaurar (todos marcados, com a opção "Todos").
2. Confere o rclone: rodadas ativas (`astro-rclone-*`) ou processos `rclone` do usuário. Se houver, pergunta e
   para (a primeira cópia retoma depois). Segura as duas travas (`astro-rclone.lock` e
   `astro-rclone-config.lock`) até o fim: nenhuma rodada começa durante a restauração. Os comandos dos projetos
   rodam sem herdar as travas (`7>&- 8>&-`), senão um container iniciado por eles as seguraria para sempre.
3. Testa a senha guardada na versão escolhida; se não abrir, pede a senha daquela versão.
4. Faz um backup da situação atual, `<data>_antes-da-restauracao`. Se falhar, para sem mexer em nada.
5. Abre os arquivos (`podman unshare tar --numeric-owner`, mantendo os donos) e chama
   `<projeto>/project.sh restore <pasta>` de cada serviço. O `host.env` volta direto; o rclone mantém a pasta do
   backup e a senha atuais.

## Adicionar um serviço de nuvem

Cada serviço é um arquivo em `providers/<serviço>.sh` com quatro funções:

| Função | Responsabilidade |
|---|---|
| `provider_describe` | Nome na lista |
| `provider_default_name` | Nome padrão do armazenamento e da pasta |
| `provider_options` | Opções do rclone para o serviço, uma por linha (ex.: limites de transferências) |
| `provider_configure <nome>` | Perguntas do serviço e a seção `[<nome>]` no `rclone.conf` (com `rclone_section_write`); confere o login. Também é usada para reconectar |

Segredos entram pelo assistente e vão ao rclone pela entrada padrão (`rclone obscure -`) ou por variável de
ambiente (ex.: `RCLONE_PROTONDRIVE_2FA`), nunca como argumento de comando.

## Arquivos gerados

| Caminho | Conteúdo |
|---|---|
| `~/.astro/rclone/.env` | Disco de backup (UUID e onde montou), disco copiado, dias de versões e a pasta do backup das configurações |
| `~/.astro/rclone/data/rclone.conf` | Uma seção por armazenamento, com login e tokens (`600`, pasta `700`) |
| `~/.astro/rclone/data/targets/<nome>.env` | Serviço, disco, pasta, o estado da primeira cópia e o da sincronização (`BISYNC_READY`, `TOO_MANY_DELETES`, `BISYNC_FORCE`) |
| `~/.cache/rclone/bisync/` | Listas de arquivos da última sincronização (fora do backup; se sumirem, a próxima rodada junta os dois lados) |
| `~/.astro/rclone/data/config-backup.key` | Senha do backup das configurações (`600`) |
| `~/.config/systemd/user/astro-rclone-*` | Os três serviços e seus timers (a instalação remove o antigo `astro-rclone-nightly`) |

Para acompanhar ao vivo: `journalctl --user -fu astro-rclone-tick`.
