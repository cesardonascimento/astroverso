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

cmd_describe() {
    echo "n8n: automações e integrações entre serviços, montadas pelo navegador"
}

cmd_status() {
    podman container exists "$CONTAINER"
}

cmd_actions() {
    :
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
    )
    mv "$ENV_FILE.new" "$ENV_FILE"
    ui_ok "configuração salva em $ENV_FILE (com a chave que protege as credenciais do n8n)"
}

start_containers() {
    local log
    mkdir -p "$DATA"
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

cmd_install() {
    state_setup
    configure

    ui_step "Containers"
    ui_info "baixando as imagens do n8n (alguns minutos na primeira vez)..."
    start_containers
    ui_ok "sem comunicação com os servidores da n8n: telemetria, aviso de versão e modelos desligados"

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

cmd_action() {
    ui_fail "ação desconhecida: ${1:-}"
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
    install)  cmd_install ;;
    remove)   cmd_remove ;;
    backup)   cmd_backup ;;
    restore)  shift; cmd_restore "$1" ;;
    *)        ui_fail "uso: $0 describe | status | actions | action <id> | install | remove | backup | restore <pasta>" ;;
esac
