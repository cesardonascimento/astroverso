# disks

Os discos de dados da máquina: montados no boot em `/srv/<nome>`, só do seu usuário, com os criptografados (LUKS)
destravados pelo TPM, sem pedir senha. Os discos são **da máquina**, de nenhum app: os apps encontram os discos pelo
`kit.disks`, que lê o `/etc/fstab`.

## O que a instalação faz

1. Instala o `cryptsetup` e o `tpm2-tss` (se faltarem).
2. **Discos da máquina:** lista os discos que não são do sistema (a partir de 1 GiB: ext4, xfs, btrfs, NTFS, exFAT,
   FAT ou LUKS), com nome, tamanho, tipo e modelo, e monta os escolhidos:
   - **LUKS:** pede a senha uma vez para cadastrar o TPM (PCR 7, Secure Boot conferido). Depois, o disco destrava
     sozinho no boot. A senha continua valendo como reserva. Máquina sem TPM 2.0: o disco criptografado fica de fora
     (nada pode pedir senha no boot, porque a máquina reinicia de longe).
   - O nome vem do rótulo do disco (ou `disco-<uuid>`); no LUKS, o rótulo de dentro é copiado para o cabeçalho, para
     aparecer mesmo com o disco travado.
3. Pergunta a verificação de hora em hora, o backup diário da configuração e o das pastas dos discos.
4. Mostra o Resumo dos discos.

Na reinstalação com a configuração salva, monta de novo os discos cadastrados, sem perguntar.

## Mudanças na máquina

| Mudança | Por quê | ⚠ |
|---|---|---|
| Pacotes `cryptsetup` e `tpm2-tss` | Destravar os discos LUKS pelo TPM | |
| Por disco (perguntada pela escolha em **Discos da máquina**): linha em `/etc/fstab` depois de `# astroverso <uuid>`, montada em `/srv/<nome>` (`nofail`, `nosuid`, `nodev`, `context=container_file_t`, antes do `user@<uid>.service`; NTFS/exFAT/FAT com `uid`/`gid` e `umask=077`) | O disco monta no boot, só do seu usuário, e os containers o enxergam | ⚠ |
| Por disco LUKS: linha em `/etc/crypttab` (`tpm2-device=auto`, `headless=true`, `nofail`) e o TPM cadastrado no disco (`systemd-cryptenroll`, PCR 7) | O disco destrava no boot sem senha | ⚠ |
| Por disco: links em `/etc/systemd/system/<dispositivo>.device.wants/` (e no `.wants` do `systemd-cryptsetup@`) | O disco monta de novo sozinho quando é religado (gaveta USB) | ⚠ |
| `/srv/<nome>` (`770`, seu usuário; imutável quando desmontado) | O ponto de montagem; desmontado, ninguém grava no disco do sistema por engano | |
| `/etc/fstab.astroverso-bak` e `/etc/crypttab.astroverso-bak` | Cópia de antes da primeira mudança | |
| `~/.astroverso/disks/` (`.env` com as respostas, `disks.json` com os discos cadastrados, `backups.json` com as pastas com backup e as pastas de destino de cada uma, `watch.json`) | A configuração | |
| Unidades do usuário `astroverso-disks-watch.timer` e `.service` (perguntada, padrão sim) | A verificação de hora em hora | |
| Unidades do usuário `astroverso-disks-backup.timer` e `.service` (perguntada, padrão sim, com as pastas de destino) | Backup diário da configuração do app no vault (`kit.vault`), com aviso no `#vault` | |
| Unidades do usuário `astroverso-disks-backup-folders.timer` e `.service` (perguntada, padrão sim) | Backup diário das pastas escolhidas em **Backup das pastas dos discos**, cada uma nas próprias pastas de destino (`kit.vault.run_data`, marca `dados:<disco>/<pasta>`, por `podman unshare`). Disco desligado ou travado: aquela pasta fica de fora e avisa no `#vault` | |

## Ações

| Ação | O que faz |
|---|---|
| Resumo dos discos | Cada disco (caminho, sistema de arquivos, situação, espaço usado), as mudanças e a verificação. Também no Discord: `/astro disks:summary` |
| Discos da máquina | Checklist com os discos encontrados (e os cadastrados que estão desligados): marcar monta, desmarcar desmonta (com confirmação), tira do `fstab` e descadastra o TPM. Os dados continuam no disco |
| Mudanças no sistema | Desmonta e monta de novo cada disco cadastrado (sem descadastrar o TPM), liga e desliga a verificação e os backups |
| Verificar agora | A verificação de hora em hora na hora (também no Discord) |
| Backup das pastas dos discos | Os dados que não são de nenhum app: adicionar uma pasta (ou o disco inteiro) pelo seletor de pastas e escolher as pastas de destino dela, trocar as pastas de destino, tirar pastas do backup (as versões guardadas continuam no servidor) |
| Fazer backup das pastas agora / Restaurar uma pasta de uma versão | O backup das pastas na hora (também no Discord) e a restauração de uma versão numa pasta nova, sem mexer na original |
| Fazer backup agora / Restaurar uma versão | Backup da configuração na hora (também no Discord) e restauração de uma versão do vault. Numa máquina nova, o TPM pede a senha do LUKS de novo |

## Verificação de hora em hora

Avisa no canal `#disks` do Discord só quando algo muda, com os botões **Resumo dos discos** e **Verificar de novo**:

| O que confere | Nível |
|---|---|
| Disco cadastrado não montado (desligado, desconectado, não destravou) | erro |
| Disco montado que parou de responder (a conexão caiu e voltou: fica inacessível até reiniciar) | erro |
| Disco com 90% ou mais ocupado | aviso |

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
