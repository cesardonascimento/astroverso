#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"

ASTRO_PROJECT=nextcloud
source ../lib/ui.sh
source ../lib/host.sh
source ../lib/env.sh
source ../lib/proxy.sh
source ../lib/disk.sh

CONTAINER=astro-nextcloud
CONTAINERS=(astro-nextcloud-cron astro-nextcloud astro-nextcloud-redis astro-nextcloud-db)
NETWORK=astro_default
SECRETS="$STATE/data/secrets"
CONFIG="$STATE/data/html/config/config.php"
OVERRIDE="$STATE/docker-compose.override.yml"
MOVE_FROM=""
DISK_OPTIONS="x-gvfs-hide,x-systemd.before=user@$(id -u).service,context=system_u:object_r:container_file_t:s0"

cmd_describe() {
    echo "Nextcloud: nuvem própria para arquivos, fotos, contatos e agenda"
}

cmd_status() {
    podman container exists "$CONTAINER"
}

compose() {
    local files=(-f docker-compose.yml)
    [[ -f $OVERRIDE ]] && files+=(-f "$OVERRIDE")
    podman compose --env-file "$ENV_FILE" "${files[@]}" "$@"
}

occ() {
    podman exec -u www-data "$CONTAINER" php occ "$@"
}

installed() {
    podman unshare grep -qs "'installed' => true" "$CONFIG"
}

configure() {
    ui_step "Configuração"
    local current_disks
    current_disks="$(env_get DISKS)"
    if [[ -f $ENV_FILE ]] && ui_confirm "usar a configuração já salva em $ENV_FILE?" y; then
        ui_ok "configuração existente mantida"
    else
        local host admin files domain old_files
        domain="$(proxy_domain)"
        old_files="$(env_get FILES_DIR)"
        ui_input host  "endereço do Nextcloud no Caddy" "$(env_get NEXTCLOUD_HOST "nextcloud${domain:+.$domain}")" is_hostname
        ui_input admin "usuário administrador" "$(env_get ADMIN_USER astro)" is_name
        ui_input files "pasta dos arquivos" "$(env_get FILES_DIR "$HOME/.nextcloud")" is_path
        if [[ -n $old_files && $files != "$old_files" ]] && podman unshare test -f "$old_files/.ncdata"; then
            ui_warn "o Nextcloud já guarda os arquivos em $old_files"
            if ui_confirm "mover os arquivos para $files?" n; then
                MOVE_FROM=$old_files
            else
                files=$old_files
                ui_ok "pasta dos arquivos mantida em $old_files"
            fi
        fi
        (
            umask 077
            printf "NEXTCLOUD_HOST='%s'\nADMIN_USER='%s'\nFILES_DIR='%s'\n" "$host" "$admin" "$files" > "$ENV_FILE.new"
        )
        mv "$ENV_FILE.new" "$ENV_FILE"
        ui_ok "configuração salva em $ENV_FILE"
    fi
    if ! grep -q '^DISKS=' "$ENV_FILE"; then
        local disks=()
        disk_choose disks nextcloud "Quais discos guardam arquivos do Nextcloud? (só $USER e o Nextcloud acessam)" "$current_disks"
        printf "DISKS='%s'\n" "${disks[*]}" >> "$ENV_FILE"
        ui_ok "${#disks[@]} disco(s) escolhido(s) para o Nextcloud"
    fi
}

container_uid() {
    podman unshare cat /proc/self/uid_map | awk -v id="$1" '$1 <= id && id < $1 + $3 { print $2 + id - $1; exit }'
}

storage() {
    local uuids=() path wid service
    read -ra uuids <<< "$(env_get DISKS)"
    if cmd_status; then
        remove_containers
        ui_ok "containers parados para soltar os discos (sobem de novo logo adiante)"
    fi
    disk_setup nextcloud "$DISK_OPTIONS" "${uuids[@]}"
    wid="$(container_uid 33)"
    for path in "${DISK_MOUNTS[@]}"; do
        mountpoint -q "$path" || continue
        sudo chown "$USER:" "$path"
        sudo chmod 770 "$path"
        if ! getfacl -cp "$path" 2>/dev/null | grep -qx "default:user:$wid:rwx"; then
            ui_info "liberando $path para o Nextcloud (pode demorar se o disco já tiver muitos arquivos)..."
            sudo setfacl -R -m "u:$wid:rwX,u:$USER:rwX" "$path"
            sudo find "$path" -type d -exec setfacl -m "d:u:$wid:rwx,d:u:$USER:rwx" {} +
        fi
        ui_ok "$path: só $USER e o Nextcloud acessam"
    done
    if ((${#DISK_MOUNTS[@]} == 0)); then
        rm -f "$OVERRIDE"
        return
    fi
    {
        printf 'services:\n'
        for service in nextcloud nextcloud-cron; do
            printf '  %s:\n    volumes:\n' "$service"
            for path in "${DISK_MOUNTS[@]}"; do
                printf '      - %s:/mnt/%s\n' "$path" "${path##*/}"
            done
        done
    } > "$OVERRIDE"
}

external_storage() {
    local admin=$1 path id datadir wanted=() log
    for path in "${DISK_MOUNTS[@]}"; do wanted+=("/mnt/${path##*/}"); done
    if ((${#wanted[@]} == 0)) && ! occ app:list --enabled 2>/dev/null | grep -q 'files_external:'; then
        return
    fi
    occ app:enable files_external >/dev/null
    while IFS=$'\t' read -r id datadir; do
        [[ $datadir == /mnt/* ]] || continue
        if [[ " ${wanted[*]} " == *" $datadir "* ]]; then
            local rest=() item
            for item in "${wanted[@]}"; do [[ $item == "$datadir" ]] || rest+=("$item"); done
            wanted=("${rest[@]}")
            occ files_external:option "$id" filesystem_check_changes 1 >/dev/null
            ui_ok "pasta ${datadir#/mnt/} já aparece no Nextcloud de $admin"
            continue
        fi
        occ files_external:delete -y "$id" >/dev/null
        ui_ok "pasta ${datadir#/mnt/} removida do Nextcloud (os arquivos continuam no disco)"
    done < <(occ files_external:list --output=json 2>/dev/null | python3 -I -c '
import json, sys
for mount in json.load(sys.stdin):
    print(mount["mount_id"], (mount.get("configuration") or {}).get("datadir", ""), sep="\t")
')
    for datadir in "${wanted[@]}"; do
        [[ -n $datadir ]] || continue
        if ! log="$(occ files_external:create "/${datadir#/mnt/}" local null::null -c "datadir=$datadir" 2>&1)" \
                || ! id="$(grep -oE '[0-9]+$' <<< "$log")"; then
            printf '%s\n' "$log" | ui_prefix >&2
            ui_fail "falha ao criar a pasta ${datadir#/mnt/} no Nextcloud"
        fi
        occ files_external:applicable --add-user="$admin" "$id" >/dev/null
        occ files_external:option "$id" filesystem_check_changes 1 >/dev/null
        ui_ok "pasta ${datadir#/mnt/} aparece no Nextcloud de $admin (Armazenamento externo)"
    done
}

prepare_secrets() {
    mkdir -p "$SECRETS"
    chmod 700 "$SECRETS"
    if [[ -s $SECRETS/db_password ]]; then
        ui_ok "senha do banco já gerada"
    else
        (umask 022 && openssl rand -hex 32 > "$SECRETS/db_password")
        ui_ok "senha do banco gerada em $SECRETS (só os containers a usam)"
    fi
    if ! installed; then
        (umask 022 && openssl rand -hex 32 > "$SECRETS/admin_password")
    fi
}

move_files() {
    local from=$1 to=$2
    mkdir -p "$to"
    if [[ -n $(podman unshare find "$to" -mindepth 1 -print -quit) ]]; then
        ui_fail "$to não está vazia: esvazie a pasta ou escolha outra"
    fi
    remove_containers
    ui_info "movendo os arquivos de $from para $to..."
    podman unshare cp -a "$from/." "$to/"
    podman unshare rm -rf "$from"
    ui_ok "arquivos movidos para $to"
}

prepare_files() {
    local files=$1
    if [[ -n $MOVE_FROM ]]; then
        move_files "$MOVE_FROM" "$files"
    fi
    mkdir -p "$files"
    podman unshare chown 33:33 "$files"
    podman unshare chmod 770 "$files"
    ui_ok "pasta dos arquivos pronta em $files"
}

remove_containers() {
    compose down >/dev/null 2>&1 || true
    podman rm -f "${CONTAINERS[@]}" >/dev/null 2>&1 || true
}

start_containers() {
    local log
    ui_info "baixando as imagens (alguns minutos na primeira vez)..."
    if ! log="$(compose pull 2>&1)"; then
        printf '%s\n' "$log" | ui_prefix >&2
        ui_fail "falha ao baixar as imagens"
    fi
    remove_containers
    if ! log="$(compose up -d 2>&1)"; then
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
    occ config:system:set skeletondirectory --value="" >/dev/null
    ui_ok "contas novas começam sem os arquivos de exemplo"

    local log
    if ! log="$(occ db:add-missing-indices 2>&1 && occ maintenance:repair --include-expensive 2>&1)"; then
        printf '%s\n' "$log" | ui_prefix >&2
        ui_fail "falha ao conferir o banco de dados"
    fi
    ui_ok "banco de dados conferido (índices e reparos)"
}

cmd_install() {
    state_setup remove_containers .env .proxy data docker-compose.override.yml
    configure
    local host admin files
    host="$(env_get NEXTCLOUD_HOST)"
    admin="$(env_get ADMIN_USER)"
    files="$(env_get FILES_DIR)"

    ui_step "Host"
    host_base

    ui_step "Discos"
    storage

    ui_step "Containers"
    prepare_secrets
    prepare_files "$files"
    start_containers
    wait_ready
    admin_password "$admin"

    ui_step "Ajustes"
    tune "$host"
    external_storage "$admin"

    ui_step "Caddy"
    proxy_publish "$host" "http://$CONTAINER:80"

    ui_step "Acesso"
    ui_ok "Nextcloud: https://$host (usuário $admin)"
    ui_info "no celular e no computador, use o app do Nextcloud com esse endereço"
    if ((${#DISK_MOUNTS[@]})); then
        ui_warn "só as pastas dos discos (${DISK_MOUNTS[*]##*/}) entram no backup; o resto do Nextcloud ($files) não"
        ui_info "no envio automático de fotos do app do celular, escolha uma pasta dentro de um desses discos"
    fi
}

cmd_remove() {
    local purge=false files
    [[ ${1:-} == --purge ]] && purge=true
    files="$(env_get FILES_DIR)"
    [[ $files == "$STATE/data/"* ]] && files=""

    ui_step "Remoção"
    if cmd_status; then
        remove_containers
        ui_ok "containers removidos"
    else
        ui_info "nenhum container para remover"
    fi
    proxy_unpublish
    if [[ -n $(disk_block "$DISK_FSTAB" nextcloud) ]]; then
        disk_release nextcloud
    fi
    rm -f "$OVERRIDE"

    if ! $purge; then
        ui_info "dados mantidos em $STATE/data${files:+ e $files}"
        return
    fi
    if [[ -n $files && -d $files ]]; then
        ui_info "pasta dos arquivos fora de $STATE, mantida: $files"
    fi
    if [[ -d $STATE/data ]]; then
        podman unshare rm -rf "$STATE/data" "$STATE/backup"
        ui_ok "dados apagados ($STATE/data: banco, configuração e arquivos)"
    else
        ui_info "nenhum dado para apagar"
    fi
}

cmd_backup() {
    local dump="$STATE/backup" files
    mkdir -p "$dump"
    if cmd_status; then
        if ! podman exec astro-nextcloud-db pg_dump -U nextcloud -d nextcloud -Fc > "$dump/nextcloud.pgdump.new"; then
            rm -f "$dump/nextcloud.pgdump.new"
            ui_error "falha no dump do banco do Nextcloud"
            return 1
        fi
        mv "$dump/nextcloud.pgdump.new" "$dump/nextcloud.pgdump"
        ui_ok "dump do banco do Nextcloud em $dump" >&2
    fi
    printf 'exclude %s\n' "$STATE/data/db" "$STATE/data/html"
    local dir
    for dir in config custom_apps themes version.php; do
        [[ -e $STATE/data/html/$dir ]] && printf 'add %s\n' "$STATE/data/html/$dir"
    done
}

cmd_restore() {
    local from=$1 code="$STATE.codigo" files log
    [[ -f $from/backup/nextcloud.pgdump ]] || ui_fail "o backup do Nextcloud não tem o dump do banco"
    remove_containers
    podman unshare rm -rf "$code"
    if [[ -d $STATE/data/html ]]; then
        podman unshare mv "$STATE/data/html" "$code"
    fi
    state_restore "$from"
    if [[ -d $code ]]; then
        podman unshare cp -a --update=none "$code/." "$STATE/data/html/"
        podman unshare rm -rf "$code"
        ui_ok "código do Nextcloud mantido; configuração e apps vieram do backup"
    fi
    files="$(env_get FILES_DIR "$HOME/.nextcloud")"
    if [[ -d $STATE/arquivos ]]; then
        podman unshare rm -rf "${files:?}"
        podman unshare mv "$STATE/arquivos" "$files"
        ui_ok "pasta dos arquivos restaurada em $files"
    elif ! podman unshare test -f "$files/.ncdata"; then
        mkdir -p "$files"
        podman unshare sh -c 'printf "# Nextcloud data directory\n" > "$1/.ncdata" && chown -R 33:33 "$1" && chmod 770 "$1"' sh "$files"
        ui_ok "pasta dos arquivos preparada em $files (vazia: os arquivos ficam nos discos)"
    fi
    podman unshare rm -rf "$STATE/data/db"
    if ! log="$(compose up -d nextcloud-db 2>&1)"; then
        printf '%s\n' "$log" | ui_prefix >&2
        ui_fail "falha ao subir o banco"
    fi
    ui_info "aguardando o banco ficar pronto..."
    if ! timeout 180 bash -c "until podman exec $CONTAINER-db pg_isready -q -h 127.0.0.1 -U nextcloud -d nextcloud; do sleep 2; done"; then
        ui_fail "o banco não ficou pronto em 3 minutos"
    fi
    local dbuser dbpass
    dbuser="$(podman unshare sed -n "s/^ *'dbuser' => '\(.*\)',\$/\1/p" "$CONFIG")"
    dbpass="$(podman unshare sed -n "s/^ *'dbpassword' => '\(.*\)',\$/\1/p" "$CONFIG")"
    if [[ -n $dbuser && $dbuser != nextcloud ]]; then
        if ! log="$(printf 'CREATE ROLE "%s" LOGIN PASSWORD '\''%s'\'';\n' "$dbuser" "${dbpass//\'/\'\'}" \
                | podman exec -i "$CONTAINER-db" psql -q -v ON_ERROR_STOP=1 -U nextcloud -d nextcloud 2>&1)"; then
            printf '%s\n' "$log" | ui_prefix >&2
            ui_fail "falha ao recriar o usuário $dbuser do banco"
        fi
        ui_ok "usuário $dbuser do banco recriado com a senha do config.php"
    fi
    if ! log="$(podman exec -i "$CONTAINER-db" pg_restore -U nextcloud -d nextcloud --exit-on-error \
            < "$STATE/backup/nextcloud.pgdump" 2>&1)"; then
        printf '%s\n' "$log" | ui_prefix >&2
        ui_fail "falha ao restaurar o banco a partir do dump"
    fi
    ui_ok "banco restaurado a partir do dump"
    if ! log="$(compose up -d 2>&1)"; then
        printf '%s\n' "$log" | ui_prefix >&2
        ui_fail "falha ao subir os containers"
    fi
    wait_ready
    occ maintenance:data-fingerprint >/dev/null
    ui_ok "Nextcloud de volta; os apps vão sincronizar de novo com o servidor"
}

case "${1:-}" in
    describe) cmd_describe ;;
    status)   cmd_status ;;
    actions)  ;;
    install)  cmd_install ;;
    remove)   shift; cmd_remove "$@" ;;
    backup)   cmd_backup ;;
    restore)  shift; cmd_restore "$1" ;;
    *)        ui_fail "uso: $0 describe | status | actions | install | remove [--purge] | backup | restore <pasta>" ;;
esac
