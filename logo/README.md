# logo

Identidade visual do Astroverso: o símbolo (a cabeça de gato com a estrela e o arco orbital) e o nome
**ASTROVERSO**.

## Paleta

A referência fica em `lib/brand.sh` (`BRAND_*`), usada pelos projetos:

| Cor | Hex | Uso |
|---|---|---|
| Violeta noturno | `#0F071E` | Fundo da versão escura (`BRAND_BACKGROUND`) |
| Lavanda clara | `#F1EBFA` | Símbolo e texto na versão escura (`BRAND_LIGHT`) |
| Roxo | `#2E1760` | Símbolo e texto na versão clara, `-alt` (`BRAND_PURPLE`) |
| Violeta | `#8A4DFF` | Início do arco orbital (`BRAND_VIOLET`) |
| Magenta | `#F0479B` | Final do arco orbital; cor de destaque, botões e links (`BRAND_ACCENT`) |

O arco orbital é um degradê do violeta (à esquerda, embaixo) para o magenta (à direita, em cima), igual nas duas
versões. O fundo da versão clara é branco (`#FFFFFF`).

## Arquivos

Todas as variantes são PNG com fundo transparente, recortadas das imagens originais. Sem sufixo, para fundo escuro
(símbolo e texto em lavanda clara); com `-alt`, para fundo claro (símbolo e texto em roxo).

| Variante | Fundo escuro | Fundo claro |
|---|---|---|
| Só o símbolo | `simbolo.png` | `simbolo-alt.png` |
| Símbolo e texto lado a lado | `horizontal.png` | `horizontal-alt.png` |
| Só o texto | `texto.png` | `texto-alt.png` |
| Símbolo sobre o texto | `vertical.png` | `vertical-alt.png` |
| Imagem original, com fundo | `original.png` | `original-alt.png` |

Derivados, com fundo (sem transparência):

| Arquivo | O que é | Onde o Astroverso usa |
|---|---|---|
| `icone.png` | símbolo num quadrado de 512×512 | ícone do Nextcloud, foto do bot do Discord |
| `favicon.ico` | o mesmo ícone em 16 a 256 px | ícone de aba de navegador |
| `quadrado.png` | símbolo centralizado em 256×256, fundo violeta noturno (o da `original.png`) | ícones e avatares fora do Astroverso |
| `quadrado-alt.png` | o mesmo em fundo claro (o da `original-alt.png`), com o símbolo roxo | ícones e avatares fora do Astroverso |
| `capa-moonlight.png` | logo vertical numa capa em pé, 600×900 (2:3) | capa do app Desktop no Moonlight (sunshine) |

O Nextcloud usa também o `simbolo.png` como logo (login e barra de cima).

Na horizontal, o símbolo tem 3 vezes a altura das letras, com um espaço de 18% da altura dele até o texto, e os
dois ficam centralizados na altura.

As originais têm 1536×1024: as variantes servem bem para telas (painéis, ícones, avatar). Para impressão ou
tamanhos muito grandes, o ideal é uma versão vetorial (SVG).
