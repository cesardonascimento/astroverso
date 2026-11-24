# kit

Pacote base dos apps do Astroverso. Só a biblioteca padrão do Python.

```python
from kit import ui
```

Testes: `python3 -m unittest discover -s packages/kit`.

## ui

Logs, perguntas e menus, sempre com o prefixo do app (`[astroverso]` se `ui.set_app` não for chamado). As cores
seguem a paleta da marca e mudam conforme o contexto. Saem sem cor quando a saída não é um terminal (systemd,
journal, redirecionamento) ou com `NO_COLOR`. Elas usam 24 bits com `COLORTERM=truecolor`, 256 cores com
`TERM=*256*` e as 16 básicas no resto.

| Função | O que faz |
|---|---|
| `set_app(nome)` | Troca o prefixo, também no `SUDO_PROMPT` herdado pelo `sudo` |
| `banner()` | Mostra o logo do Astroverso: ao lado do nome, em cima dele ou só o nome, conforme a largura do terminal. Sem terminal, não mostra nada |
| `step`, `info`, `ok`, `warn` | Etapa e mensagens (saída padrão) |
| `error(texto)` / `fail(texto)` | Erro na saída de erro; `fail` também encerra com código 1 |
| `prefixed(texto)` | Saída de um comando, linha a linha, com o prefixo e em cinza |
| `ask(rótulo, default=, validate=)` | Pergunta e devolve o texto, repetindo enquanto o validador recusar |
| `secret(rótulo, confirm=True)` | Pergunta sem eco, com confirmação (ou sem, com `confirm=False`) |
| `ask_list(rótulo, validate=)` | Lista de valores, um por pergunta, até um Enter vazio |
| `confirm(pergunta, default=False)` | Sim ou não (`s`, `sim`, `n`, `não`...) |
| `menu(título, itens)` | Devolve o índice escolhido |
| `checklist(título, itens, selected=, all_option=, cancel=)` | Devolve os índices marcados, ou `None` se cancelado com Esc |

- **Validadores** recebem o texto e devolvem o valor normalizado, ou levantam `ValueError("motivo")`. O motivo
  aparece na tela.
- **Perguntas e menus** usam `/dev/tty`. Sem terminal, terminam com "sem terminal para perguntar". Depois da
  resposta, a pergunta vira uma linha com o valor escolhido (segredos aparecem como `••••••••`).
- **Teclas:** ↑/↓ (ou `k`/`j`), Home, End, PgUp, PgDn, 1 a 9 no menu, Espaço e `a` (todos) no checklist. Esc
  escolhe o último item do menu quando ele é "Voltar" ou "Sair". No checklist, Esc só cancela com `cancel=True`.
  Nos outros casos, é ignorado.
- Listas maiores que o terminal rolam, com o contador "N de M".
- O terminal é restaurado (eco, cursor, quebra de linha) mesmo com Ctrl+C, que chega ao chamador como
  `KeyboardInterrupt`.

## logo

Os pixels do símbolo (`SYMBOL`, convertido de `simbolo.png`: `#` lavanda, `o` arco em degradê do violeta ao
magenta) e a fonte do nome (`FONT`), desenhados pelo `ui.banner()` com meio-blocos (`▀▄█`).
