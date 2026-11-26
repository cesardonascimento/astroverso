# manager

O gerenciador, chamado pelo script `astroverso` da raiz. Descobre os apps em `apps/` (pastas com `app.py`, ver
`apps/README.md`) sem conhecer nenhum pelo nome, na ordem recomendada que cada app declara no `ORDER` (os sem `ORDER` no fim, por
nome). Menus e instalação seguem essa ordem.

**Sem argumentos**, abre o logo e o menu: "Instalar apps" (checklist dos que ainda não estão instalados, com a
descrição de cada um e a linha "Todos" no topo, e um resumo no fim) e "Gerenciar apps" (cada app instalado: as ações dele, "Reinstalar" e
"Remover", com confirmação). Na primeira vez, cria o atalho `~/.local/bin/astroverso`.

**Uso direto**, sem menus, para serviços do systemd e para o pacote `backup` (o código de saída diz se deu certo):

```
astroverso <app> install | remove | status | backup <pasta> | restore <pasta> | action <id>
```

`status` sai com 0 se o app está instalado e 1 se não. Ctrl+C sai com 130.

Testes: `python3 -m unittest discover -s packages -t packages` (todos os pacotes).
