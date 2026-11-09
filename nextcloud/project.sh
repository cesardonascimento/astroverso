#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"

ASTRO_PROJECT=nextcloud
source ../lib/ui.sh
source ../lib/host.sh
source ../lib/env.sh
source ../lib/proxy.sh

CONTAINER=astro-nextcloud
CONTAINERS=(astro-nextcloud-cron astro-nextcloud astro-nextcloud-redis astro-nextcloud-db)
NETWORK=astro_default
SECRETS=data/secrets
CONFIG=data/html/config/config.php

cmd_describe() {
    echo "Nextcloud: nuvem própria para arquivos, fotos, contatos e agenda"
}

cmd_status() {
    podman container exists "$CONTAINER"
}

occ() {
    podman exec -u www-data "$CONTAINER" php occ "$@"
}

installed() {
    podman unshare grep -qs "'installed' => true" "$CONFIG"
}

configure() {
    ui_step "Configuração"
    if [[ -f .env ]] && ui_confirm "usar a configuração já salva em nextcloud/.env?" y; then
        ui_ok "configuração existente mantida"
        return
    fi
    local host admin files domain
    domain="$(proxy_domain)"
    ui_input host  "endereço do Nextcloud no Caddy" "$(env_get NEXTCLOUD_HOST "nextcloud${domain:+.$domain}")" is_hostname
    ui_input admin "usuário administrador" "$(env_get ADMIN_USER astro)" is_name
    ui_input files "pasta dos arquivos" "$(env_get FILES_DIR "$PWD/data/files")" is_path
    (
        umask 077
        printf "NEXTCLOUD_HOST='%s'\nADMIN_USER='%s'\nFILES_DIR='%s'\n" "$host" "$admin" "$files" > .env.new
    )
    mv .env.new .env
    ui_ok "configuração salva em nextcloud/.env"
}

prepare_secrets() {
    mkdir -p "$SECRETS"
    chmod 700 "$SECRETS"
    if [[ -s $SECRETS/db_password ]]; then
        ui_ok "senha do banco já gerada"
    else
        (umask 022 && openssl rand -hex 32 > "$SECRETS/db_password")
        ui_ok "senha do banco gerada em nextcloud/$SECRETS (só os containers a usam)"
    fi
    if ! installed; then
        (umask 022 && openssl rand -hex 32 > "$SECRETS/admin_password")
    fi
}

prepare_files() {
    local files=$1
    mkdir -p "$files"
    podman unshare chown 33:33 "$files"
    podman unshare chmod 770 "$files"
    ui_ok "pasta dos arquivos pronta em $files"
}

remove_containers() {
    podman compose down >/dev/null 2>&1 || true
    podman rm -f "${CONTAINERS[@]}" >/dev/null 2>&1 || true
}

start_containers() {
    local log
    ui_info "baixando as imagens (alguns minutos na primeira vez)..."
    if ! log="$(podman compose pull 2>&1)"; then
        printf '%s\n' "$log" | ui_prefix >&2
        ui_fail "falha ao baixar as imagens"
    fi
    remove_containers
    if ! log="$(podman compose up -d 2>&1)"; then
        printf '%s\n' "$log" | ui_prefix >&2
        ui_fail "falha ao subir os containers"
    fi
    ui_ok "containers rodando: ${CONTAINERS[*]}"
}

wait_ready() {
    ui_info "aguardando o Nextcloud ficar pronto (a primeira instalação leva alguns minutos)..."
    if ! timeout 600 bash -c "until podman exec -u www-data $CONTAINER php occ status --output=json 2>/dev/null \
            | grep -q '\"installed\":true'; do sleep 5; done"; then
        podman logs --tail 30 "$CONTAINER" 2>&1 | ui_prefix >&2
        ui_fail "o Nextcloud não ficou pronto em 10 minutos"
    fi
    ui_ok "Nextcloud instalado e respondendo"
}

admin_password() {
    local admin=$1 password log
    if [[ ! -f $SECRETS/admin_password ]]; then
        ui_ok "senha de $admin mantida"
        return
    fi
    while true; do
        ui_secret password "senha do administrador $admin"
        if log="$(OC_PASS="$password" podman exec -e OC_PASS -u www-data "$CONTAINER" \
                php occ user:resetpassword --password-from-env "$admin" 2>&1)"; then
            break
        fi
        printf '%s\n' "$log" | ui_prefix >&2
        ui_warn "o Nextcloud recusou a senha, escolha outra"
    done
    rm -f "$SECRETS/admin_password"
    ui_ok "senha de $admin definida"
}

timezone() {
    local tz
    tz="$(timedatectl show -P Timezone 2>/dev/null || true)"
    is_timezone "${tz:-UTC}" || printf 'UTC'
}

tune() {
    local host=$1 subnet tz region window
    subnet="$(podman network inspect "$NETWORK" --format '{{range .Subnets}}{{.Subnet}} {{end}}' | awk '{ print $1 }')"
    occ config:system:set trusted_domains 1 --value="$host" >/dev/null
    occ config:system:set trusted_proxies 0 --value="$subnet" >/dev/null
    occ config:system:set overwriteprotocol --value=https >/dev/null
    occ config:system:set overwrite.cli.url --value="https://$host" >/dev/null
    ui_ok "endereço https://$host aceito, atrás do Caddy ($subnet)"

    tz="$(timezone)"
    occ config:system:set default_timezone --value="$tz" >/dev/null
    region="$(awk -v tz="$tz" '$3 == tz { print $1; exit }' /usr/share/zoneinfo/zone.tab 2>/dev/null || true)"
    if [[ -n $region ]]; then
        occ config:system:set default_phone_region --value="$region" >/dev/null
        ui_ok "fuso $tz e região $region para os telefones sem código do país"
    else
        ui_ok "fuso $tz"
    fi

    window="$(date -u -d "@$(TZ="$tz" date -d 03:00 +%s)" +%-H)"
    occ config:system:set maintenance_window_start --type=integer --value="$window" >/dev/null
    occ background:cron >/dev/null
    ui_ok "tarefas em segundo plano pelo cron, as pesadas às 3h da manhã"

    local log
    if ! log="$(occ db:add-missing-indices 2>&1 && occ maintenance:repair --include-expensive 2>&1)"; then
        printf '%s\n' "$log" | ui_prefix >&2
        ui_fail "falha ao conferir o banco de dados"
    fi
    ui_ok "banco de dados conferido (índices e reparos)"
}

cmd_install() {
    configure
    local host admin files
    host="$(env_get NEXTCLOUD_HOST)"
    admin="$(env_get ADMIN_USER)"
    files="$(env_get FILES_DIR)"

    ui_step "Host"
    host_base

    ui_step "Containers"
    prepare_secrets
    prepare_files "$files"
    start_containers
    wait_ready
    admin_password "$admin"

    ui_step "Ajustes"
    tune "$host"

    ui_step "Caddy"
    proxy_publish "$host" "http://$CONTAINER:80"

    ui_step "Acesso"
    ui_ok "Nextcloud: https://$host (usuário $admin)"
    ui_info "no celular e no computador, use o app do Nextcloud com esse endereço"
}

cmd_remove() {
    local purge=false files
    [[ ${1:-} == --purge ]] && purge=true
    files="$(env_get FILES_DIR)"
    [[ $files == "$PWD/data/"* ]] && files=""

    ui_step "Remoção"
    if cmd_status; then
        remove_containers
        ui_ok "containers removidos"
    else
        ui_info "nenhum container para remover"
    fi
    proxy_unpublish

    if ! $purge; then
        ui_info "dados mantidos em nextcloud/data${files:+ e $files}"
        return
    fi
    if [[ -n $files && -d $files ]]; then
        ui_info "pasta dos arquivos fora do projeto, mantida: $files"
    fi
    if [[ -d data ]]; then
        podman unshare rm -rf data
        ui_ok "dados apagados (nextcloud/data: banco, configuração e arquivos)"
    else
        ui_info "nenhum dado para apagar"
    fi
}

case "${1:-}" in
    describe) cmd_describe ;;
    status)   cmd_status ;;
    actions)  ;;
    install)  cmd_install ;;
    remove)   shift; cmd_remove "$@" ;;
    *)        ui_fail "uso: $0 describe | status | actions | install | remove [--purge]" ;;
esac
