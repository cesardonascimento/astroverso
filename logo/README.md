# logo

Identidade visual do Astroverso: o símbolo (a cabeça de gato com a estrela e o arco orbital) e o nome
**ASTROVERSO**.

## Paleta

Cores medidas nas imagens originais (são a referência; os projetos as usam por `lib/brand.sh`):

| Cor | Hex | Uso |
|---|---|---|
| 🌌 Azul espacial | `#010214` | Fundo da versão escura, fundo dos ícones |
| ✨ Creme estelar | `#FFF8EE` | Símbolo e texto na versão escura |
| 🌑 Azul-marinho | `#001436` | Símbolo e texto na versão clara (`-alt`) |
| 🔴 Vermelho orbital | `#E51B13` | Início do arco orbital |
| 🟠 Laranja solar | `#F27206` | Final do arco orbital; cor de destaque (botões, links) |

O arco orbital é um degradê do vermelho orbital (à esquerda, embaixo) para o laranja solar (à direita, em cima).
Na versão clara, o arco sai um pouco mais vivo (por volta de `#FB2C0B` → `#FB7134`). Os valores da primeira proposta
(`#020617`, `#FFF8E8`, `#FF3B30`, `#FF8A00`) foram trocados pelos medidos.

## Arquivos

Todas as variantes são PNG com fundo transparente, recortadas das imagens originais. Sem sufixo, para fundo escuro
(símbolo e texto em creme estelar); com `-alt`, para fundo claro (símbolo e texto em azul-marinho).

| Variante | Fundo escuro | Fundo claro |
|---|---|---|
| Só o símbolo | `simbolo.png` | `simbolo-alt.png` |
| Símbolo e texto lado a lado | `horizontal.png` | `horizontal-alt.png` |
| Só o texto | `texto.png` | `texto-alt.png` |
| Símbolo sobre o texto | `vertical.png` | `vertical-alt.png` |
| Imagem original, com fundo | `original.png` | `original-alt.png` |

Derivados, com fundo (sem transparência):

| Arquivo | O que é | Onde o astro usa |
|---|---|---|
| `icone.png` | símbolo num quadrado de 512×512 | ícone do Nextcloud, foto do bot do Discord |
| `favicon.ico` | o mesmo ícone em 16 a 256 px | ícone de aba de navegador |
| `quadrado.png` | símbolo centralizado em 256×256, fundo azul espacial (o da `original.png`) | ícones e avatares fora do astro |
| `quadrado-alt.png` | o mesmo em fundo claro (o da `original-alt.png`), com o símbolo azul-marinho | ícones e avatares fora do astro |
| `capa-moonlight.png` | logo vertical numa capa em pé, 600×900 (2:3) | capa do app Desktop no Moonlight (sunshine) |

O Nextcloud usa também o `simbolo.png` como logo (login e barra de cima).

Na horizontal, o símbolo tem 3 vezes a altura das letras, com um espaço de 18% da altura dele até o texto, e os
dois ficam centralizados na altura.

As originais têm 1536×1024 e um pouco de ruído de compressão: as variantes servem bem para telas (painéis, ícones,
avatar). Para impressão ou tamanhos muito grandes, o ideal é uma versão vetorial (SVG).
