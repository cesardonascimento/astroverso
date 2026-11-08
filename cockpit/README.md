# cockpit

Painel web da máquina (CPU, memória, disco, logs, serviços, atualizações, terminal) e dos containers
do astro (logs, reiniciar, parar), acessível em `https://<máquina>.<domínio>` pelo Caddy.

```bash
./project.sh install           # instala, configura e publica a rota no Caddy
./project.sh remove [--purge]  # desativa; --purge apaga também a configuração de proxy
```

Diferente dos outros projetos, o Cockpit não roda em container: são pacotes do sistema
(`cockpit` e `cockpit-podman`), porque ele administra a própria máquina.

## Perguntas da instalação

| Pergunta | Padrão |
|---|---|
| Endereço do Cockpit no Caddy | `<hostname>.<domínio do caddy>` |

## O que a instalação faz

- Instala `cockpit` e `cockpit-podman` (dnf ou apt) e ativa o `cockpit.socket`
- Ativa o `podman.socket` do usuário, para os containers rootless aparecerem no painel
- Configura `/etc/cockpit/cockpit.conf` para funcionar atrás do proxy (`Origins`, `ProtocolHeader`)
- Bloqueia a porta `9090` para a rede local no firewalld: o acesso passa só pelo Caddy
- Declara a rota em `.proxy` e pede ao Caddy para recarregar

O login usa o usuário e a senha do sistema.
