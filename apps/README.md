# apps

Cada pasta é um serviço autônomo do Astroverso.

- Não conhece nenhum outro app e não depende de ordem de instalação.
- Usa só o código de `packages/`.
- Instala as próprias dependências pela camada `os` do pacote `kit`.
- Guarda o que gera em `~/.astroverso/<app>`.
- Containers no projeto compose `astroverso`, na rede `astroverso`, com o nome `astroverso-<app>`.
- Implementa `backup <pasta>` e `restore <pasta>`, usados pelo pacote `backup` quando ele estiver instalado.
