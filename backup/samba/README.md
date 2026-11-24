# samba

Pasta de rede: a pasta `~/Public` de quem instala, aberta pelo [Samba](https://www.samba.org) (SMB, o protocolo
das pastas compartilhadas do Windows) para a rede local, só com o usuário e a senha dele.

```bash
./project.sh install           # instala o Samba, compartilha a ~/Public e libera a rede local
./project.sh remove           # desfaz tudo o que o projeto criou (usado pelo Implodir Astroverso)
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
- Acrescenta ao fim do `/etc/samba/smb.conf`, entre `# astroverso samba: inicio` e `# astroverso samba: fim`, o
  compartilhamento `[Public]` e, num `[global]` próprio, `multicast dns register = no`: `path = ~/Public`, `valid users = <usuário>`, gravação liberada. O resto do arquivo
  fica como veio do sistema (cópia em `smb.conf.astroverso-bak` antes da primeira mudança). A configuração é conferida
  pelo `testparm`; se falhar, o arquivo volta ao que era.
- **Só a `Public` na rede:** no mesmo bloco, desliga os compartilhamentos que vêm prontos no Fedora (`[homes]`,
  o home inteiro; `[printers]` e `[print$]`, impressoras e drivers para Windows) com `available = no`, e o suporte
  a impressoras (`load printers = no`, `disable spoolss = yes`). O Samba aceita repetir uma seção, e o valor do
  Astroverso, no fim do arquivo, vale.
- **SELinux:** marca `~/Public` com `samba_share_t` (`semanage fcontext` + `restorecon`), o único lugar do home
  que o Samba lê e grava. Arquivos criados dentro da pasta
  herdam o rótulo; um arquivo **movido** de outro lugar do home mantém o rótulo antigo e não aparece pela rede até
  a instalação rodar de novo (ou `restorecon -R ~/Public`).
- **Senha:** cadastra quem instala no banco de senhas do Samba (`smbpasswd -s -a`, senha pela entrada padrão). Ela
  é separada da senha do login e vale só para a pasta de rede.
- **Sem anúncio na rede:** o Samba não se anuncia pelo Avahi (mDNS). Esse anúncio só funciona dentro de casa;
  o acesso é sempre pelo endereço, com o nome do domínio (abaixo), igual em casa e pelo Tailscale.
- Habilita e reinicia o `smb.service` (`smbd` no Debian).
- Libera o serviço `samba` no firewalld (porta 445 e as do NetBIOS) para a rede local.

## Acesso

- Windows: `\\<nome-da-máquina>.<domínio>\Public` no Explorador de Arquivos (ou "Mapear unidade de rede").
- macOS, Linux (Arquivos → Outros locais) e iPhone (app Arquivos → Conectar ao Servidor):
  `smb://<nome-da-máquina>.<domínio>/Public`.

O AdGuard responde todo `*.<domínio>` com o IP da máquina, em casa e pelo Tailscale (Split DNS), então qualquer
nome do domínio serve. Sem o Caddy instalado, use o IP (`\\<ip>\Public`).

Entre com o usuário que instalou e a senha do Samba.

## Remoção

Tira o bloco do `smb.conf`, o usuário do Samba, o rótulo do SELinux e a liberação no firewall, e desliga o
`smb.service`. Ficam o pacote e os arquivos da `~/Public`.

## Arquivos

| Caminho | O que é |
|---|---|
| `~/.astroverso/samba/.env` | `SHARE_DIR` (a pasta compartilhada) |
| `/etc/samba/smb.conf` | bloco `[global]` (sem mDNS e sem impressoras), `[homes]`/`[printers]`/`[print$]` desligados e `[Public]` entre as marcas do Astroverso |
| `/var/lib/samba/private/passdb.tdb` | senha do Samba (do sistema, fora do backup) |
