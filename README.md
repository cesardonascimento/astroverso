# Astroverso

Serviços de casa (DNS, nuvem pessoal, automações, backup) instalados em qualquer máquina com Fedora Server, cada
um de forma independente.

## Estado

Em reconstrução como monorepo. O código antigo fica em `backup/` até cada parte ser migrada.

| Pasta | O que tem |
|---|---|
| `apps/` | serviços autônomos: cada um instala, configura e remove a si mesmo |
| `packages/` | código compartilhado pelos apps |
| `backup/` | versão anterior, só como referência |
