# astro

Meu homelab: os serviços da rede de casa rodando em containers na rigel, versionados para
reinstalar tudo em minutos se algo der errado.

| Projeto | Para que serve |
|---|---|
| [**adguard**](adguard/) | DNS da casa: bloqueia anúncios e rastreadores em todos os aparelhos e resolve os nomes internos (`*.cesardonascimento.com`) |
| [**caddy**](caddy/) | Porta de entrada dos serviços: `https://adguard.cesardonascimento.com` com certificado válido, sem precisar de IP e porta |
| [**cockpit**](cockpit/) | Painel web da máquina e dos containers em `https://rigel.cesardonascimento.com` |

## Como usar

```bash
gh repo clone cesardonascimento/astro ~/Projects/astro
~/Projects/astro/setup.sh
```

| Opção | O que faz |
|---|---|
| Instalar todos | Instala o que ainda não está instalado |
| Escolher quais instalar | Marca os projetos com Espaço; os já instalados são recriados |
| Configurar um projeto instalado | Ajustes do dia a dia, como adicionar rotas no Caddy |
| Reinstalar tudo do zero | Apaga os dados e instala de novo |
| Remover todos os containers | Mantendo os dados ou apagando tudo |

## Respondendo a instalação

Rode em um terminal normal: o `sudo` pede senha na primeira vez. Enter aceita o valor entre `[ ]`.

**Em todos**
- *Usar a configuração já salva?* → **S** para reaproveitar as respostas da última vez
- *Anunciar a rede local no Tailscale?* → **S** para acessar a casa de fora; depois aprove a rota no painel do Tailscale
- *Desativar o login por senha no SSH?* → **S** (só aparece se houver chave em `~/.ssh/authorized_keys`)

**adguard**
- *Usuário* e *senha do painel* → os do seu login no AdGuard
- *Porta*, *IP*, *fuso* e *idioma* → Enter
- *Adicionar domínios de reescrita?* → **S** → IP: Enter → domínio: `cesardonascimento.com` → Enter vazio
- *Usar só o AdGuard como DNS desta máquina?* → **S**
- Se avisar do *Split DNS do Tailscale*, aponte `cesardonascimento.com` para o IP da rigel no painel do Tailscale

**caddy**
- *Domínio base* → `cesardonascimento.com`
- *Portas HTTP/HTTPS* → Enter
- *Token da Cloudflare* → o token salvo no Proton Pass (o assistente mostra como criar um, se precisar)

**cockpit**
- *Endereço no Caddy* → Enter (`rigel.cesardonascimento.com`)

No roteador, use o IP da rigel (`192.168.3.43`) como único DNS.

Para criar um projeto novo, veja [lib/README.md](lib/README.md).
