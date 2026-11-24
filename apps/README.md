# apps

Cada pasta é um serviço autônomo do Astroverso, reconhecido pelo gerenciador (`astroverso`) quando tem um `app.py`.

- Não conhece nenhum outro app e não depende de ordem de instalação.
- Usa só o código de `packages/`.
- Instala as próprias dependências pela camada `kit.distro`.
- Guarda o que gera em `~/.astroverso/<app>`.
- Containers no projeto compose `astroverso`, na rede `astroverso`, com o nome `astroverso-<app>`.

## Contrato do `app.py`

Funções simples no módulo (o `Protocol` `kit.app.App` documenta os tipos):

| Nome | Obrigatório | O que faz |
|---|---|---|
| `DESCRIPTION` | sim | Uma linha, mostrada ao lado do nome nos menus |
| `status() -> bool` | sim | Diz se o app está instalado |
| `install()` | sim | Pergunta, instala e sobe o app; também é o "Reinstalar" |
| `remove()` | sim | Desfaz tudo o que o app criou, sem falhar no que já não existe |
| `backup(pasta)` / `restore(pasta)` | sim | Copia a configuração para a pasta e a traz de volta (usados pelo pacote `backup`) |
| `actions() -> list[Action]` | não | Ações de pós-configuração: `Action(id, rótulo, função)` do `kit.app` |

O nome do app é o da pasta. O gerenciador troca o prefixo das mensagens para `[<app>]` enquanto roda o app.
Um `ui.fail` ou uma exceção encerram só aquela operação: o erro aparece e o gerenciador segue. Um app sem
alguma função obrigatória aparece como "app inválido" e fica de fora.
