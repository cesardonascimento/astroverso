# cockpit

Painel web da máquina (CPU, memória, disco, logs, serviços, atualizações, terminal), dos discos e dos
arquivos, e dos containers do astro (logs, reiniciar, parar), acessível em `https://<máquina>.<domínio>` pelo Caddy.

```bash
./project.sh install           # instala, configura e publica a rota no Caddy
./project.sh remove           # desfaz tudo o que o projeto criou (usado pelo Implodir Astro)
```

Diferente dos outros projetos, o Cockpit não roda em container: são pacotes do sistema
(`cockpit`, `cockpit-podman`, `cockpit-storaged` e `cockpit-files`), porque ele administra a própria máquina.

## Perguntas da instalação

| Pergunta | Padrão |
|---|---|
| Endereço do Cockpit no Caddy | `<hostname>.<domínio do caddy>` |

## O que a instalação faz

- Instala `cockpit`, `cockpit-podman`, `cockpit-storaged` (página Armazenamento: montar, destravar e ejetar
  discos) e `cockpit-files` (página Arquivos: navegar, enviar e baixar arquivos) pelo dnf ou apt, e ativa o
  `cockpit.socket`
- Ativa o `podman.socket` do usuário, para os containers rootless aparecerem no painel
- Configura `/etc/cockpit/cockpit.conf` para funcionar atrás do proxy (`Origins`, `ProtocolHeader`)
- Bloqueia a porta `9090` para a rede local no firewalld: o acesso passa só pelo Caddy
- Declara a rota em `~/.astro/cockpit/.proxy` e pede ao Caddy para recarregar

O login usa o usuário e a senha do sistema. A página Arquivos mostra o que esse usuário pode ler (ex.: os
discos em `/srv`); com "Acesso administrativo" ligado no topo do painel, ela mexe em qualquer arquivo, inclusive
num disco plugado e montado pela sessão de outro usuário.

## Remoção

`remove` desativa o Cockpit e o `podman.socket`, apaga o `cockpit.conf`, tira o bloqueio da porta 9090 e a rota do
Caddy, e apaga `~/.astro/cockpit`. Os pacotes ficam instalados.
