# disks

Os discos de dados da máquina: montados no boot em `/srv/<nome>`, só do seu usuário, com os criptografados (LUKS)
destravados pelo TPM, sem pedir senha. Os discos são **da máquina**, de nenhum app: os apps encontram os discos pelo
`kit.disks`, que lê o `/etc/fstab`.

## O que a instalação faz

1. Instala o `cryptsetup`, o `tpm2-tss` e o `rsync` (se faltarem).
2. **Discos da máquina:** lista os discos que não são do sistema (a partir de 1 GiB: ext4, xfs, btrfs, NTFS, exFAT,
   FAT ou LUKS), com nome, tamanho, tipo e modelo, e monta os escolhidos:
   - **LUKS:** pede a senha uma vez para cadastrar o TPM (PCR 7, Secure Boot conferido). Depois, o disco destrava
     sozinho no boot. A senha continua valendo como reserva. Máquina sem TPM 2.0: o disco criptografado fica de fora
     (nada pode pedir senha no boot, porque a máquina reinicia de longe).
   - O nome vem do rótulo do disco (ou `disco-<uuid>`); no LUKS, o rótulo de dentro é copiado para o cabeçalho, para
     aparecer mesmo com o disco travado.
3. Pergunta a verificação de hora em hora, a fotografia noturna e o backup diário da configuração.
4. Mostra o Resumo dos discos.

Na reinstalação com a configuração salva, monta de novo os discos cadastrados, sem perguntar.

## Mudanças na máquina

| Mudança | Por quê | ⚠ |
|---|---|---|
| Pacotes `cryptsetup`, `tpm2-tss` e `rsync` | Destravar os discos LUKS pelo TPM; tirar as fotografias | |
| Por disco (perguntada pela escolha em **Discos da máquina**): linha em `/etc/fstab` depois de `# astroverso <uuid>`, montada em `/srv/<nome>` (`nofail`, `nosuid`, `nodev`, `context=container_file_t`, antes do `user@<uid>.service`; NTFS/exFAT/FAT com `uid`/`gid` e `umask=077`) | O disco monta no boot, só do seu usuário, e os containers o enxergam | ⚠ |
| Por disco LUKS: linha em `/etc/crypttab` (`tpm2-device=auto`, `headless=true`, `nofail`) e o TPM cadastrado no disco (`systemd-cryptenroll`, PCR 7) | O disco destrava no boot sem senha | ⚠ |
| Por disco: links em `/etc/systemd/system/<dispositivo>.device.wants/` (e no `.wants` do `systemd-cryptsetup@`) | O disco monta de novo sozinho quando é religado (gaveta USB) | ⚠ |
| `/srv/<nome>` (`770`, seu usuário; imutável quando desmontado) | O ponto de montagem; desmontado, ninguém grava no disco do sistema por engano | |
| `/etc/fstab.astroverso-bak` e `/etc/crypttab.astroverso-bak` | Cópia de antes da primeira mudança | |
| `~/.astroverso/disks/` (`.env` com as respostas, `disks.json` com os discos cadastrados, `photos.json` com as fotografias, `photos-state.json` com a última de cada uma, `watch.json`) | A configuração | |
| Unidades do usuário `astroverso-disks-watch.timer` e `.service` (perguntada, padrão sim) | A verificação de hora em hora | |
| Unidades do usuário `astroverso-disks-photos.timer` e `.service` (perguntada, padrão sim) | A fotografia de cada disco às 03:00 (abaixo); a instalação tira o antigo `astroverso-disks-backup-folders` | |
| Por fotografia: `astroverso-fotografia.json` na raiz do disco de fotografias (origem: nome e UUID) | Marca o disco como de fotografias (some dos seletores de pasta) e diz ao Resgatar um disco de onde ele veio | |
| Unidades do usuário `astroverso-disks-backup.timer` e `.service` (perguntada, padrão sim) | Backup diário da configuração do app no vault (`kit.vault`), com aviso no `#vault` | |

## Ações

| Ação | O que faz |
|---|---|
| Resumo dos discos | Cada disco (caminho, sistema de arquivos, situação, espaço usado), as mudanças e a verificação. Também no Discord: `/astro disks:summary` |
| Discos da máquina | Checklist com os discos encontrados (e os cadastrados que estão desligados): marcar monta, desmarcar desmonta (com confirmação), tira do `fstab` e descadastra o TPM. Os dados continuam no disco |
| Mudanças no sistema | Desmonta e monta de novo cada disco cadastrado (sem descadastrar o TPM), liga e desliga a verificação e os backups |
| Verificar agora | A verificação de hora em hora na hora (também no Discord) |
| Fotografias dos discos | Fotografar um disco (disco de origem e disco de fotografias, com confirmação) e Parar de fotografar um disco. As fotografias que já estão nos discos ficam |
| Fotografar agora | Todas as fotografias na hora (também no Discord, com confirmação) |
| Resgatar um disco | Recria um disco que morreu a partir da fotografia (abaixo) |
| Liberar a fotografia | Uma fotografia parada pela trava de exclusões: mostra quantos e quais arquivos sairiam do `atual/` e roda sem a trava |
| Fazer backup agora / Restaurar uma versão | Backup da configuração na hora (também no Discord) e restauração de uma versão do vault. Numa máquina nova, o TPM pede a senha do LUKS de novo |

## Fotografias

Toda noite às 03:00, cada disco de origem é copiado inteiro (`podman unshare rsync -aH --numeric-ids --delete`, que guarda
donos, permissões e links) para o disco de fotografias:

```
/srv/<disco de fotografias>/
├── astroverso-fotografia.json   de qual disco ele é
├── atual/                       igual à origem (o espelho)
└── versoes/<AAAA-MM-DD>/        o que mudou ou foi apagado naquela noite, por 30 dias
```

- **Nada grava no disco de fotografias:** ele some dos seletores de pasta (`kit.folders`) e um caminho digitado nele é
  recusado.
- Não roda com um dos discos desligado ou travado (uma origem sumida esvaziaria o `atual/`).
- **Trava de exclusões:** se fosse tirar do `atual/` mais de 10% dos arquivos de uma vez, para sem mexer em nada e avisa
  no `#disks`; **Liberar a fotografia** mostra a lista e roda.
- Com o disco de fotografias a partir de 90% ocupado, as `versoes/` mais antigas saem antes do prazo.
- Um `atual/` que já existe (do sistema antigo) é aproveitado: a primeira rodada só copia o que mudou.

## Resgatar um disco

O disco de origem queimou: troque-o por um novo e use **Resgatar um disco**.

1. Escolha o disco de fotografias (ele diz de qual disco é, pelo `astroverso-fotografia.json`; numa máquina reinstalada,
   cadastre-o antes em Discos da máquina).
2. Escolha o disco novo: só aparecem discos que não estão montados nem cadastrados.
3. Confirme digitando o nome do disco antigo e escolha a senha do LUKS do disco novo (guarde no gerenciador de senhas).
4. O resgate tira o disco antigo do cadastro, **formata o disco novo** (`wipefs`, LUKS2 com o nome antigo, ext4),
   cadastra o TPM, monta em `/srv/<nome>` e copia de volta o `atual/` (`podman unshare rsync -aH --numeric-ids`, com os
   donos). A fotografia noturna passa a ser do disco novo.
5. Depois, reinicie a máquina ou os apps que usam o disco (no Nextcloud, rode também o Reparar).

Volta tudo até a última fotografia: o que mudou depois dela não volta. Pelo `versoes/`, dá para recuperar arquivos soltos
de outros dias. É a única ação do Astroverso que formata um disco (decisão do usuário); o resto fica no Cockpit.

## Verificação de hora em hora

Avisa no canal `#disks` do Discord só quando algo muda, com os botões **Resumo dos discos** e **Verificar de novo**:

| O que confere | Nível |
|---|---|
| Disco cadastrado não montado (desligado, desconectado, não destravou) | erro |
| Disco montado que parou de responder (a conexão caiu e voltou: fica inacessível até reiniciar) | erro |
| Disco com 90% ou mais ocupado | aviso |
| Fotografia parada pela trava de exclusões | erro |
| Fotografia sem rodar há mais de 36 h | erro |

## Para os outros apps (`kit.disks`)

```python
from kit import disks

disks.mounts()                 # [Disk(uuid, path, fstype, line)], dos discos montados por este app
disks.available(Path(pasta))   # falso se a pasta fica num disco que não está montado ou não responde
```

Um app que grava num disco confere `available` antes: sem o disco, a pasta `/srv/<nome>` fica vazia (e imutável), e
um backup dela viraria uma versão vazia.

## Remover

Desmonta os discos, tira as linhas do `fstab` e do `crypttab`, descadastra o TPM (os discos voltam a abrir só com a
senha), desliga a verificação e o backup e apaga `~/.astroverso/disks`. Os dados continuam nos discos.

Testes: `python3 -m unittest discover -s apps/disks/tests`.
