# samba

Pasta de rede: a pasta `~/Public` de quem instala, aberta pelo [Samba](https://www.samba.org) (SMB, o protocolo
das pastas compartilhadas do Windows) para a rede local, só com o usuário e a senha dele.

```bash
./project.sh install           # instala o Samba, compartilha a ~/Public e libera a rede local
./project.sh remove           # desfaz tudo o que o projeto criou (usado pelo Implodir Astro)
```

Como o cockpit, não roda em container: o Samba do sistema já entende os usuários, as permissões e o SELinux da
máquina, e a pasta compartilhada é do usuário que instala.

## Perguntas da instalação

| Pergunta | Padrão |
|---|---|
| Manter a senha atual do Samba de `<usuário>`? | `S` (só se ele já estiver cadastrado) |
| Senha do Samba de `<usuário>` | (sem padrão) |

## O que a instalação faz

- Instala o pacote `samba` (Fedora ou Debian/Ubuntu).
- Acrescenta ao fim do `/etc/samba/smb.conf`, entre `# astro samba: inicio` e `# astro samba: fim`, o
  compartilhamento `[Public]`: `path = ~/Public`, `valid users = <usuário>`, gravação liberada. O resto do arquivo
  fica como veio do sistema (cópia em `smb.conf.astro-bak` antes da primeira mudança). A configuração é conferida
  pelo `testparm`; se falhar, o arquivo volta ao que era.
- **SELinux:** marca `~/Public` com `samba_share_t` (`semanage fcontext` + `restorecon`), o único lugar do home
  que o Samba lê e grava. O compartilhamento `[homes]` que vem no Fedora continua bloqueado
  (`samba_enable_home_dirs` desligado): o resto do home não aparece na rede. Arquivos criados dentro da pasta
  herdam o rótulo; um arquivo **movido** de outro lugar do home mantém o rótulo antigo e não aparece pela rede até
  a instalação rodar de novo (ou `restorecon -R ~/Public`).
- **Senha:** cadastra quem instala no banco de senhas do Samba (`smbpasswd -s -a`, senha pela entrada padrão). Ela
  é separada da senha do login e vale só para a pasta de rede.
- **Avahi só na rede local:** acrescenta `deny-interfaces=tailscale0` na seção `[server]` do
  `/etc/avahi/avahi-daemon.conf`. O Samba se anuncia pelo Avahi (mDNS) e aparece sozinho em "Rede" nos outros
  computadores da casa; sem isso, o anúncio saía também pelo Tailscale, o nome `<máquina>.local` apontava para o IP
  do Tailscale e o Nautilus de outra máquina não listava o compartilhamento.
- Habilita e reinicia o `smb.service` (`smbd` no Debian).
- Libera o serviço `samba` no firewalld (porta 445 e as do NetBIOS) para a rede local.

## Acesso

- Windows: `\\<ip>\Public` no Explorador de Arquivos (ou "Mapear unidade de rede").
- macOS, Linux (Arquivos → Outros locais) e iPhone (app Arquivos → Conectar ao Servidor): `smb://<ip>/Public`.

Entre com o usuário que instalou e a senha do Samba.

## Remoção

Tira o bloco do `smb.conf`, a linha do Avahi, o usuário do Samba, o rótulo do SELinux e a liberação no firewall, e desliga o
`smb.service`. Ficam o pacote e os arquivos da `~/Public`.

## Arquivos

| Caminho | O que é |
|---|---|
| `~/.astro/samba/.env` | `SHARE_DIR` (a pasta compartilhada) |
| `/etc/samba/smb.conf` | bloco `[Public]` entre as marcas do astro |
| `/etc/avahi/avahi-daemon.conf` | `deny-interfaces=tailscale0` na seção `[server]` |
| `/var/lib/samba/private/passdb.tdb` | senha do Samba (do sistema, fora do backup) |
