# Astroverso

Serviços de casa (DNS, nuvem pessoal, automações, backup) instalados em qualquer máquina com Fedora Server, cada
um de forma independente.

## Estado

Em reconstrução como monorepo. O código antigo fica em `legacy/` até cada parte ser migrada.

| Pasta | O que tem |
|---|---|
| `apps/` | serviços autônomos: cada um instala, configura e remove a si mesmo |
| `packages/` | código compartilhado pelos apps |
| `legacy/` | versão anterior, só como referência |

## Como usar

```
git clone <repositório> && cd astroverso && ./astroverso
```

Precisa só do Python 3.11 ou mais novo, que já vem no Fedora. Depois da primeira vez, basta digitar `astroverso`.
