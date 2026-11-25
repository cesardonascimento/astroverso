# Nextcloud: conectar os aparelhos

O Nextcloud abre em `https://nextcloud.<domínio>`, igual em casa e fora de casa (pelo Tailscale). Nos exemplos,
use o endereço que você escolheu na instalação.

## Senha de app

Para cada aparelho, crie uma **senha de app** em vez de usar a sua senha de login: se o aparelho for perdido, você
apaga só a senha dele.

1. Entre no Nextcloud pelo navegador.
2. Foto da conta (canto de cima) → **Configurações pessoais** → **Segurança**.
3. Em **Dispositivos e sessões**, dê um nome ao aparelho (ex.: `celular`) e clique em **Criar nova senha de app**.
4. Copie o usuário e a senha que aparecem. A senha só aparece uma vez.

Os apps oficiais do celular e do computador fazem isso sozinhos pelo login no navegador. A senha de app manual é para
agenda e contatos e para programas de terceiros.

## Celular (arquivos e fotos)

1. Instale o app **Nextcloud** (Android: Play Store ou F-Droid; iPhone: App Store).
2. **Entrar** → endereço `https://nextcloud.<domínio>` → faça o login no navegador que abrir e autorize.
3. Para mandar as fotos sozinho: Android, em **Configurações** → **Envio automático**; iPhone, em **Mais** →
   **Envio automático**. Escolha a pasta de destino no Nextcloud.

## Computador (sincronizar uma pasta)

1. Baixe o **Nextcloud Desktop** em <https://nextcloud.com/install/#install-clients> (Windows, macOS e Linux; no
   Fedora, também pelo pacote `nextcloud-client`).
2. **Entrar no seu Nextcloud** → endereço `https://nextcloud.<domínio>` → login no navegador.
3. Escolha a pasta local e o que sincronizar. No Windows, os arquivos podem ficar só na nuvem até serem abertos
   (arquivos virtuais).

## Agenda e contatos

O Nextcloud fala CalDAV (agenda) e CardDAV (contatos), padrões que quase todo aparelho entende.

| Aparelho | Como |
|---|---|
| Android | Instale o **DAVx⁵** (Play Store ou F-Droid) → **+** → **Entrar com URL e usuário** → `https://nextcloud.<domínio>`, usuário e senha de app → marque as agendas e listas de contatos. Elas aparecem nos apps de agenda e contatos do celular |
| iPhone | **Ajustes** → **Calendário** → **Contas** → **Adicionar conta** → **Outra** → **Adicionar conta CalDAV**: servidor `nextcloud.<domínio>`, usuário e senha de app. Para contatos, o mesmo em **Contatos** → **Adicionar conta CardDAV** |
| Thunderbird | **Nova agenda** → **Na rede** → usuário e `https://nextcloud.<domínio>`; ele acha as agendas sozinho. Contatos: **Novo catálogo** → **CardDAV** |

Se um programa pedir o endereço completo: `https://nextcloud.<domínio>/remote.php/dav`.

## Problemas comuns

| Sintoma | O que conferir |
|---|---|
| O endereço não abre fora de casa | O Tailscale ligado no aparelho e o Split DNS do app `network` (Resumo da rede) |
| "Certificado inválido" | O cadeado do Caddy (Resumo da rede): o Nextcloud só abre com HTTPS |
| Login recusado em agenda ou contatos | Use uma senha de app, não a de login (com a verificação em duas etapas ligada, a de login não funciona) |
