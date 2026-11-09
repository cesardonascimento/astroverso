# backup

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
| `astro-backup-tick` | a cada 15 minutos | Envia à nuvem os arquivos criados ou alterados desde o último envio bem-sucedido (`find -newerct` + `rclone copy --files-from-raw --no-traverse`). Enquanto a primeira cópia não termina, faz ou retoma essa cópia no lugar do envio |
| `astro-backup-nightly` | 01:30 | Espelho com exclusões de cada armazenamento (`rclone sync --max-delete 1000`) |
| `astro-backup-local` | 02:30 | Espelho do disco inteiro em `<disco de backup>/atual`, guardando dono e permissões (`podman unshare rclone sync --metadata`). O que for apagado ou alterado vai para `<disco de backup>/versoes/<data>/`, apagado depois do prazo |

Todos têm `Persistent=true`: se a máquina estava desligada na hora, rodam logo depois de ligar.

## Quem manda

A cópia local (`<disco>/<pasta>`) é a fonte da verdade. A nuvem recebe as mudanças em até 15 minutos e as
exclusões à noite. Arquivos criados só na nuvem, depois da primeira cópia, são apagados pelo espelho
noturno: mexa nos arquivos pelo Nextcloud (ou direto no disco), não pelo app da nuvem.

## Travas

- Nada roda se o disco não estiver montado. Sem o disco, a pasta fica vazia, e espelhar uma pasta vazia
  apagaria a nuvem inteira.
- Nada é enviado nem apagado na nuvem antes de a primeira cópia terminar sem erro.
- A primeira cópia continua de onde parou depois de uma queda de internet, reboot ou falta de luz: o rclone
  pula o que já está igual e grava cada arquivo com nome temporário até terminar.
- Uma rodada por vez (`flock`): o envio de 15 minutos pula a vez se outra estiver rodando; os noturnos
  esperam.
- O espelho noturno para depois de 1.000 exclusões.

## Ações (Configurar um projeto instalado)

| Ação | O que faz |
|---|---|
| Ver as últimas execuções | Estado de cada armazenamento, próximos agendamentos e as últimas mensagens |
| Sincronizar agora | Roda o envio já, ou a primeira cópia pendente |
| Adicionar armazenamento em nuvem | As perguntas acima |
| Reconectar a um armazenamento em nuvem | Refaz o login (ex.: depois de ligar a verificação em duas etapas) |
| Remover armazenamento em nuvem | Tira o login e o agendamento; os arquivos ficam no disco e na nuvem |

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
| `.env` | Disco de backup (UUID e onde montou), disco copiado e dias de versões |
| `data/rclone.conf` | Uma seção por armazenamento, com login e tokens (`600`, pasta `700`) |
| `data/targets/<nome>.env` | Serviço, disco, pasta e o estado da primeira cópia e do último envio |
| `~/.config/systemd/user/astro-backup-*` | Os três serviços e seus timers |

Para acompanhar ao vivo: `journalctl --user -fu astro-backup-tick`.
