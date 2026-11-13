#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"

ASTRO_PROJECT=n8n
source ../lib/ui.sh
source ../lib/host.sh
source ../lib/env.sh
source ../lib/proxy.sh

CONTAINER=astro-n8n
CONTAINERS=(astro-n8n-runners astro-n8n)
DATA="$STATE/data/n8n"
HASH_FILE="$STATE/data/owner_password_hash"
IMAGE="$(sed -n 's/^ *image: *\(.*n8nio\/n8n:.*\)$/\1/p' docker-compose.yml | head -1)"
BCRYPT=/usr/local/lib/node_modules/n8n/node_modules/bcryptjs
IMPORT_FILE=/home/node/.n8n/.astro-importar.json
NEXTCLOUD=astro-nextcloud
EMAIL_HOOK=astro-contas-email

cmd_describe() {
    echo "n8n: automações e integrações entre serviços, montadas pelo navegador"
}

cmd_status() {
    podman container exists "$CONTAINER"
}

cmd_actions() {
    echo "credentials|Credenciais (dados dos outros projetos para as rotinas, chave da Anthropic)"
}

cmd_remote_actions() {
    echo "contas:email|Contas: enviar agora o e-mail consolidado (contas emitidas no mês anterior; argumento: AAAA-MM, opcional)|nao"
}

cmd_help() {
    printf '%s\n' \
        "Contas|Contas: buscar e-mails|traz os e-mails encaminhados para a caixa do astro, e a rotina Contas: leitura lê as cobranças novas|de 5 em 5 minutos, das 08:00 às 20:00|mailserver:fetch|10" \
        "Contas|Contas: e-mail do mês|manda aos destinatários as contas emitidas no mês anterior, com o QR Code do Pix ou o código de barras|dia 5 de cada mês, às 08:00 (rotina Contas: notificação mensal ligada)|contas:email|20"
}

remove_containers() {
    compose down >/dev/null 2>&1 || true
    podman rm -f "${CONTAINERS[@]}" >/dev/null 2>&1 || true
}

timezone() {
    local tz
    tz="$(timedatectl show -P Timezone 2>/dev/null || true)"
    is_timezone "${tz:-UTC}" || printf 'UTC'
}

random_key() {
    openssl rand -base64 48 | tr -dc 'A-Za-z0-9' | head -c "$1"
}

password_hash() {
    local password=$1
    printf '%s' "$password" | podman run --rm -i --entrypoint node "$IMAGE" -e '
let data = "";
process.stdin.on("data", (chunk) => data += chunk).on("end", () => console.log(require(process.argv[1]).hashSync(data, 10)));
' "$BCRYPT"
}

ask_password() {
    local password hash
    while true; do
        ui_secret password "senha do administrador (mínimo 8 caracteres)"
        ((${#password} >= 8)) && break
        ui_warn "senha curta: use pelo menos 8 caracteres"
    done
    ui_info "preparando o hash da senha (bcrypt)..."
    hash="$(password_hash "$password")"
    [[ $hash == \$2* ]] || ui_fail "não foi possível gerar o hash da senha"
    mkdir -p "$STATE/data"
    (
        umask 077
        printf '%s' "$hash" > "$HASH_FILE.new"
    )
    chmod 644 "$HASH_FILE.new"
    mv "$HASH_FILE.new" "$HASH_FILE"
    ui_ok "senha guardada como hash bcrypt em $HASH_FILE"
}

configure() {
    ui_step "Configuração"
    local host email first last domain key token
    if [[ -f $HASH_FILE ]] && config_reuse; then
        host="$(env_get N8N_HOST)"
        email="$(env_get OWNER_EMAIL)"
        first="$(env_get OWNER_FIRST_NAME)"
        last="$(env_get OWNER_LAST_NAME)"
        ui_ok "configuração existente mantida"
        if [[ ${ASTRO_REUSE_CONFIG:-} != 1 ]] && ui_confirm "trocar a senha do administrador?" n; then
            ask_password
        fi
    else
        domain="$(proxy_domain)"
        ui_input host  "endereço do n8n no Caddy" "$(env_get N8N_HOST "n8n${domain:+.$domain}")" is_hostname
        ui_info "o administrador é criado pela instalação: ninguém na rede consegue tomar a conta antes de você"
        ui_input email "e-mail para entrar no n8n (só o login: não precisa existir, o n8n não manda e-mails)" \
            "$(env_get OWNER_EMAIL "${domain:+n8n@$domain}")" is_email
        ui_input first "nome do administrador" "$(env_get OWNER_FIRST_NAME)" is_label
        ui_input last  "sobrenome do administrador" "$(env_get OWNER_LAST_NAME)" is_label
        if [[ -f $HASH_FILE ]] && ui_confirm "manter a senha atual do administrador?" y; then
            :
        else
            ask_password
        fi
    fi

    key="$(env_get N8N_ENCRYPTION_KEY)"
    [[ -n $key ]] || key="$(random_key 48)"
    token="$(env_get RUNNERS_TOKEN)"
    [[ -n $token ]] || token="$(random_key 48)"

    (
        umask 077
        printf "N8N_HOST='%s'\nTZ='%s'\nOWNER_EMAIL='%s'\nOWNER_FIRST_NAME='%s'\nOWNER_LAST_NAME='%s'\nN8N_ENCRYPTION_KEY='%s'\nRUNNERS_TOKEN='%s'\n" \
            "$host" "$(timezone)" "$email" "$first" "$last" "$key" "$token" > "$ENV_FILE.new"
        grep -E '^(ANTHROPIC_API_KEY|NEXTCLOUD_APP_PASSWORD|N8N_HOOK_TOKEN)=' "$ENV_FILE" >> "$ENV_FILE.new" 2>/dev/null || true
    )
    mv "$ENV_FILE.new" "$ENV_FILE"
    ui_ok "configuração salva em $ENV_FILE (com a chave que protege as credenciais do n8n)"
}

start_containers() {
    local log
    mkdir -p "$DATA"
    ui_info "construindo o executor de código (imagem oficial + bibliotecas de QR Code e PNG)..."
    if ! log="$(compose build 2>&1)"; then
        printf '%s\n' "$log" | ui_prefix >&2
        ui_fail "falha ao construir a imagem do executor de código"
    fi
    remove_containers
    if ! log="$(compose up -d 2>&1)"; then
        printf '%s\n' "$log" | ui_prefix >&2
        ui_fail "falha ao subir os containers"
    fi
    ui_info "aguardando o n8n ficar pronto (até 3 minutos na primeira vez)..."
    if ! timeout 180 bash -c "until podman exec $CONTAINER wget -q -O /dev/null http://127.0.0.1:5678/healthz 2>/dev/null; do sleep 2; done"; then
        podman logs --tail 30 "$CONTAINER" 2>&1 | ui_prefix >&2
        ui_fail "o n8n não respondeu em 3 minutos"
    fi
    ui_ok "containers ${CONTAINERS[*]} rodando (código dos fluxos roda no astro-n8n-runners, com JavaScript e Python)"
}

env_put() {
    sed -i "/^$1=/d" "$ENV_FILE"
    (
        umask 077
        printf "%s='%s'\n" "$1" "$2" >> "$ENV_FILE"
    )
}

n8n_cli() {
    podman exec "$CONTAINER" n8n "$@"
}

n8n_import() {
    local kind=$1 file=$2 log status=0
    podman exec -i "$CONTAINER" sh -c 'umask 077; cat > "$1"' sh "$IMPORT_FILE" < "$file"
    log="$(n8n_cli "import:$kind" --input="$IMPORT_FILE" 2>&1)" || status=$?
    podman exec "$CONTAINER" rm -f "$IMPORT_FILE"
    if ((status)) || grep -qiE 'error|failed' <<< "$log"; then
        grep -iE 'error|failed' <<< "$log" | tail -3 | ui_prefix >&2
        return 1
    fi
}

nextcloud_app_password() {
    local user out password
    [[ -z $(env_get NEXTCLOUD_APP_PASSWORD) ]] || return 0
    podman container exists "$NEXTCLOUD" || return 0
    user="$(env_get ADMIN_USER "" "$ASTRO_HOME/nextcloud/.env")"
    [[ -n $user ]] || return 0
    out="$(podman exec -u www-data "$NEXTCLOUD" php occ user:auth-tokens:add -n --name=astro-n8n "$user" 2>/dev/null)" || out=""
    password="$(tail -1 <<< "$out" | grep -oE '[A-Za-z0-9-]{20,}$' || true)"
    if [[ -z $password ]]; then
        ui_warn "não foi possível criar a senha de app do Nextcloud para o n8n"
        return 0
    fi
    env_put NEXTCLOUD_APP_PASSWORD "$password"
    ui_ok "senha de app \"astro-n8n\" criada no Nextcloud de $user (para as rotinas gravarem arquivos)"
}

anthropic_key() {
    local key
    [[ -z $(env_get ANTHROPIC_API_KEY) || ${1:-} == trocar ]] || return 0
    [[ ${ASTRO_REUSE_CONFIG:-} != 1 ]] || return 0
    ui_info "as rotinas de contas usam a API da Anthropic (Claude) para ler os e-mails de cobrança"
    ui_info "crie uma chave em https://console.anthropic.com → API Keys (Enter vazio deixa para depois)"
    read -rsp "$(_ui_tag)     $(printf '\033[35m?\033[0m') chave da API da Anthropic: " key </dev/tty
    echo
    if [[ -z $key ]]; then
        ui_info "sem chave: as rotinas de contas não leem e-mails até você cadastrar uma"
        return 0
    fi
    if [[ ! $key =~ ^sk-ant-[A-Za-z0-9_-]+$ ]]; then
        ui_warn "isso não parece uma chave da Anthropic (começa com sk-ant-): não foi salva"
        return 0
    fi
    env_put ANTHROPIC_API_KEY "$key"
    ui_ok "chave da API da Anthropic guardada em $ENV_FILE"
}

credentials_sync() {
    local tmp names
    nextcloud_app_password
    [[ -n $(env_get N8N_HOOK_TOKEN) ]] || env_put N8N_HOOK_TOKEN "$(random_key 48)"
    tmp="$(mktemp)"
    names="$(python3 -I - "$ASTRO_HOME" "$tmp" <<'PYEOF'
import json, sys
home, out = sys.argv[1:]

def env(projeto):
    valores = {}
    try:
        for linha in open(f"{home}/{projeto}/.env", encoding="utf-8"):
            chave, _, valor = linha.rstrip("\n").partition("=")
            valores[chave] = valor.strip("'")
    except OSError:
        pass
    return valores

n8n, mail, discord, nextcloud = env("n8n"), env("mailserver"), env("discord"), env("nextcloud")
creds = []
if mail.get("IMAP_PASSWORD"):
    creds.append({"id": "astroImapInbox01", "name": "Astro: caixa inbox (IMAP)", "type": "imap", "data": {
        "user": "inbox", "password": mail["IMAP_PASSWORD"], "host": "astro-mailserver", "port": 31143,
        "secure": False, "allowUnauthorizedCerts": False}})
if discord.get("DISCORD_TOKEN"):
    creds.append({"id": "astroDiscordBot01", "name": "Astro: bot do Discord", "type": "httpHeaderAuth", "data": {
        "name": "Authorization", "value": "Bot " + discord["DISCORD_TOKEN"]}})
if n8n.get("NEXTCLOUD_APP_PASSWORD") and nextcloud.get("NEXTCLOUD_HOST") and nextcloud.get("ADMIN_USER"):
    creds.append({"id": "astroNextcloud001", "name": "Astro: Nextcloud", "type": "nextCloudApi", "data": {
        "webDavUrl": f"https://{nextcloud['NEXTCLOUD_HOST']}/remote.php/dav/files/{nextcloud['ADMIN_USER']}",
        "user": nextcloud["ADMIN_USER"], "password": n8n["NEXTCLOUD_APP_PASSWORD"]}})
if n8n.get("ANTHROPIC_API_KEY"):
    creds.append({"id": "astroAnthropic001", "name": "Astro: API da Anthropic", "type": "httpHeaderAuth", "data": {
        "name": "x-api-key", "value": n8n["ANTHROPIC_API_KEY"]}})
if mail.get("SEND_KEY"):
    creds.append({"id": "astroEnvioEmail01", "name": "Astro: envio de e-mail", "type": "httpHeaderAuth", "data": {
        "name": "X-Astro-Chave", "value": mail["SEND_KEY"]}})
if n8n.get("N8N_HOOK_TOKEN"):
    creds.append({"id": "astroHookAstro001", "name": "Astro: chamadas do assistente", "type": "httpHeaderAuth", "data": {
        "name": "X-Astro-Chave", "value": n8n["N8N_HOOK_TOKEN"]}})
json.dump(creds, open(out, "w"))
print(", ".join(c["name"].replace("Astro: ", "") for c in creds))
PYEOF
)"
    chmod 600 "$tmp"
    if [[ -z $names ]]; then
        rm -f "$tmp"
        ui_info "nenhuma credencial para as rotinas ainda (instale mailserver, nextcloud e discord)"
        return 0
    fi
    if n8n_import credentials "$tmp"; then
        ui_ok "credenciais das rotinas no n8n: $names"
    else
        ui_warn "não foi possível gravar as credenciais das rotinas no n8n"
    fi
    rm -f "$tmp"
}

action_credentials() {
    local index
    cmd_status || ui_fail "o n8n não está rodando"
    while true; do
        ui_step "Credenciais"
        ui_info "as rotinas usam credenciais com nome fixo (Astro: ...), montadas a partir dos outros projetos"
        ui_menu index "O que fazer?" "Atualizar as credenciais (caixa, Discord, Nextcloud, Anthropic, envio de e-mail)" \
            "Trocar a chave da API da Anthropic" "Voltar"
        case $index in
            0) credentials_sync ;;
            1) anthropic_key trocar; credentials_sync ;;
            *) return 0 ;;
        esac
    done
}

workflows_hint() {
    if [[ -z $(n8n_cli list:workflow 2>/dev/null || true) ]]; then
        ui_info "o n8n está sem rotinas: para trazer as suas, use Administração → Restaurar uma versão → n8n"
    else
        ui_ok "rotinas do n8n mantidas (elas ficam no banco do n8n e entram no backup das configurações)"
    fi
}

cmd_install() {
    state_setup
    configure

    ui_step "Containers"
    ui_info "baixando as imagens do n8n (alguns minutos na primeira vez)..."
    start_containers
    ui_ok "sem comunicação com os servidores da n8n: telemetria, aviso de versão e modelos desligados"

    ui_step "Credenciais"
    anthropic_key
    credentials_sync
    workflows_hint

    ui_step "Caddy"
    proxy_publish "$(env_get N8N_HOST)" "http://$CONTAINER:5678"

    ui_step "Pronto"
    ui_info "abra https://$(env_get N8N_HOST) e entre com $(env_get OWNER_EMAIL) e a senha do administrador"
}

cmd_backup() {
    if cmd_status; then
        podman unshare rm -rf "$DATA/backup"
        if ! podman exec "$CONTAINER" n8n export:entities --outputDir=/home/node/.n8n/backup >/dev/null 2>&1; then
            ui_error "falha na exportação do n8n (export:entities)"
            return 1
        fi
        ui_ok "fluxos, credenciais e usuários do n8n exportados em $DATA/backup" >&2
        printf 'exclude %s\n' "$DATA/database.sqlite" "$DATA/database.sqlite-wal" "$DATA/database.sqlite-shm"
    fi
}

import_entities() {
    local log
    ui_info "carregando a exportação do backup num banco novo..."
    if ! log="$(N8N_ENCRYPTION_KEY="$(env_get N8N_ENCRYPTION_KEY)" podman run --rm -v "$DATA:/home/node/.n8n:Z,U" -e N8N_ENCRYPTION_KEY \
            --entrypoint n8n "$IMAGE" import:entities --inputDir=/home/node/.n8n/backup --truncateTables=true 2>&1)" \
            || grep -q 'Error importing' <<< "$log"; then
        grep -iE 'error|fail' <<< "$log" | tail -5 | ui_prefix >&2
        ui_fail "falha ao carregar a exportação do n8n"
    fi
    ui_ok "fluxos, credenciais e usuários carregados"
}

cmd_restore() {
    remove_containers
    state_restore "$1"
    if ! podman unshare test -e "$DATA/database.sqlite" && podman unshare test -f "$DATA/backup/entities.zip"; then
        import_entities
    fi
    start_containers
    ui_ok "n8n rodando com a configuração restaurada"
}

cmd_remote() {
    case "${1:-}" in
        contas:email) remote_contas_email "${2:-}" ;;
        *)            echo "ação desconhecida: ${1:-}"; return 1 ;;
    esac
}

remote_contas_email() {
    local month=$1 token
    if [[ -n $month && ! $month =~ ^[0-9]{4}-(0[1-9]|1[0-2])$ ]]; then
        echo "mês inválido: use AAAA-MM (ex.: $(date +%Y-%m))"
        return 1
    fi
    cmd_status || { echo "o n8n não está rodando"; return 1; }
    token="$(env_get N8N_HOOK_TOKEN)"
    [[ -n $token ]] || { echo "falta a chave das chamadas: Gerenciar Astro → n8n → Credenciais → Atualizar as credenciais"; return 1; }
    printf '%s' "$token" | podman exec -i "$CONTAINER" node -e '
let chave = "";
process.stdin.on("data", (d) => chave += d).on("end", async () => {
  try {
    const r = await fetch(`http://127.0.0.1:5678/webhook/${process.argv[1]}`, {
      method: "POST",
      headers: { "content-type": "application/json", "x-astro-chave": chave },
      body: JSON.stringify(process.argv[2] ? { mes: process.argv[2] } : {}),
      signal: AbortSignal.timeout(280000),
    });
    const texto = await r.text();
    let mensagem = texto;
    try { mensagem = JSON.parse(texto).mensagem || texto; } catch (e) {}
    if (r.status === 404) mensagem = "a rotina Contas: notificação mensal não está ligada no n8n (ou não tem mais o webhook astro-contas-email)";
    console.log(mensagem);
    process.exit(r.ok ? 0 : 1);
  } catch (e) {
    console.log(`falha ao chamar o n8n: ${e.message}`);
    process.exit(1);
  }
});
' "$EMAIL_HOOK" "$month"
}

cmd_action() {
    case "${1:-}" in
        credentials) action_credentials ;;
        *)       ui_fail "ação desconhecida: ${1:-}" ;;
    esac
}

cmd_remove() {
    ui_step "Remoção"
    remove_containers
    images_remove
    ui_ok "containers ${CONTAINERS[*]} removidos"
    proxy_unpublish
    state_purge
}

case "${1:-}" in
    describe) cmd_describe ;;
    status)   cmd_status ;;
    actions)  cmd_actions ;;
    action)   shift; cmd_action "$@" ;;
    remote-actions) cmd_remote_actions ;;
    remote)   shift; cmd_remote "$@" ;;
    help)     cmd_help ;;
    install)  cmd_install ;;
    remove)   cmd_remove ;;
    backup)   cmd_backup ;;
    restore)  shift; cmd_restore "$1" ;;
    *)        ui_fail "uso: $0 describe | status | actions | action <id> | remote-actions | remote <id> [argumento] | help | install | remove | backup | restore <pasta>" ;;
esac
