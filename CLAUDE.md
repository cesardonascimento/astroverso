# CLAUDE.md

Regras para desenvolver o Astroverso. O contexto da instalação atual (máquina, IPs, domínio, contas) fica em
`CLAUDE.local.md`, fora do git.

## Situação

O Astroverso está sendo refeito como monorepo. O código antigo (o antigo Astroverso Homelab) fica em `backup/`,
só como referência: nada roda de lá e nada novo depende dele. Cada parte é migrada para `apps/` ou `packages/`,
um pedaço por vez. As regras e armadilhas antigas ficam em `backup/CLAUDE.md` e voltam para este arquivo quando
o app ou pacote delas for migrado.

## Nomes

- O projeto é o **Astroverso**. O codinome técnico é `astroverso` em tudo que identifica o sistema: comando,
  `~/.astroverso`, containers, imagens, rede, unidades systemd, variáveis `ASTROVERSO_*`, marcas em arquivos do
  sistema, sufixo `.astroverso-bak`, recursos da Cloudflare, prefixo `[astroverso]` dos logs e rótulos dos menus.
- **`astro` é só o bot do Discord**: o nome do bot, o comando `/astro`, o `custom_id` `astro|...` e o canal do bot.
  Todo o resto é `astroverso`, inclusive o usuário padrão dos apps.

## Como trabalhar

- Responder sempre em **português do Brasil**, de forma direta.
- **Micro commits.** Desenvolver um pedaço pequeno por vez: primeiro descrever a arquitetura daquele pedaço e
  esperar a aprovação do usuário, depois implementar. Depois de aprovado, fazer commit e push sem perguntar.
  Mensagens em português, terminando com a linha `Co-Authored-By` da sessão.
- **Sem comentários no código.** Mensagens de log, sim, bem formatadas.
- Toda mensagem na tela usa o prefixo do projeto ou do app (`[astroverso]`, `[adguard]`...), inclusive prompts,
  o prompt do `sudo` e os logs de dentro dos containers. Usar as funções do pacote `kit`, nunca `echo` solto.
- Preferir o caminho simples e remover etapas desnecessárias.
- **Tudo funciona pela rede local**, mesmo com o Tailscale conectado. Não sugerir o IP do Tailscale como
  caminho de acesso.

## Alvo

- **Fedora Server**, sem interface gráfica. Acesso remoto só pelo Cockpit e pelo SSH.
- Outras distribuições virão depois: nenhum app chama o gerenciador de pacotes, o firewall ou o systemd do
  sistema diretamente. Tudo passa pela camada `os` do pacote `kit` (`os_install`, `os_firewall_open`,
  `os_service_enable`...), com um arquivo por distribuição (`packages/kit/os/fedora.sh`). Distribuição sem
  arquivo: a instalação para no início com "distribuição não suportada".
- O Astroverso não depende de uma máquina específica: qualquer máquina instala só os apps que quiser.

## Arquitetura

```
apps/<app>/       serviços autônomos (adguard, nextcloud...)
packages/<pacote>/ código compartilhado pelos apps (kit, backup...)
backup/           código antigo, só referência
```

### Apps

- **Autônomos.** Um app não conhece nenhum outro app: não cita `apps/<outro>`, não lê `~/.astroverso/<outro>`
  e não depende de ordem de instalação nem de uma etapa prévia da máquina. Depende só de `packages/`.
- Cada app instala as próprias dependências, pela camada `os` do `kit`.
- **Endereço.** Todo app com interface na rede tem uma etapa de endereço: `<serviço>.<domínio>`. O domínio é
  perguntado pelo `kit` na primeira instalação e gravado em `~/.astroverso/astroverso.env`; os apps seguintes já
  trazem esse domínio como padrão.
- **Guarda-chuva.** Todo container fica no projeto compose `astroverso` (`name: astroverso`), na rede
  `astroverso` e com o nome `astroverso-<app>` (`astroverso-<app>-<parte>` quando houver mais de um).
- **Estado fora do repositório:** tudo o que a instalação gera fica em `~/.astroverso/<app>`; o repositório só
  tem código.
- **Backup das configurações.** Cada app implementa `backup <pasta>` e `restore <pasta>`. Se o pacote `backup`
  estiver instalado, o app entra na rotina sozinho; se não, a instalação avisa e segue.

### Configurações do sistema

Toda mudança que o Astroverso faz no sistema (energia, portas, serviços, DNS...) é um módulo que pode ser
ligado e desligado, num app especial de configurações do sistema. O desenho dele terá a própria etapa.

### Pacotes previstos

- `kit`: interface (logs, prompts, menus), configuração (`.env`, validadores), camada `os`, domínio padrão.
- `backup`: rotina de backup das configurações; instalado uma vez, descobre os apps instalados.
- Cliente do Discord (avisos), quando chegar a vez. O servidor do bot fica no repositório `astroverso-discord`.

Cada pacote e cada app tem a própria etapa de arquitetura antes de ser escrito.

## Nada pessoal no código nem na documentação

- Domínio, IPs, nomes de máquina, fuso, contas e e-mails **não podem aparecer** no código, nos READMEs nem neste
  arquivo. Vêm das perguntas da instalação (gravadas em `~/.astroverso/`) ou são detectados.
- Exemplos usam marcadores: `<seu-domínio>`, `<domínio>`, `<ip>`, `<rede>`, `<nome-da-máquina>`.
- Valores padrão neutros quando nada é detectado (ex.: fuso `UTC`).
- Antes de cada commit, conferir com `git grep -nE '<domínio real>|<IP real>|<nome da máquina>'` usando os
  valores do `CLAUDE.local.md`.

## Regras de segurança ao testar

- **Nunca testar no container real nem no estado real.** Copiar para o scratchpad e trocar o nome do projeto
  compose, `container_name`, imagem e portas. Um teste antigo recriou um container real e apagou um `.env` real.
- Nunca apagar nada em `~/.astroverso`: contém segredos e não está no git. Para testar, usar outro `HOME`,
  mantendo `XDG_DATA_HOME`, `XDG_CONFIG_HOME` e `XDG_RUNTIME_DIR` reais (senão o Podman usa outro armazenamento).
- A instalação antiga roda a partir de `~/Projects/astroverso-homelab`: não mexer naquela pasta.
- `sudo` não funciona na sessão do Claude (sem TTY). Instalações que pedem `sudo` rodam em um terminal normal.
- Para testar menus e prompts, usar um pseudo-terminal em Python (`pty.fork`) enviando as teclas.
- Não pedir nem aceitar segredos (tokens, senhas) no chat: eles entram pela instalação.
- Segredos nunca em argumentos de comando (aparecem no `ps`): vão pela entrada padrão ou por arquivo temporário.
