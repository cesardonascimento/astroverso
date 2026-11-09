#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"

ASTRO_PROJECT=homeassistant
source ../lib/ui.sh
source ../lib/host.sh
source ../lib/env.sh
source ../lib/proxy.sh

CONTAINER=astro-homeassistant
NETWORK=astro_default
CONFIG="$STATE/config"

cmd_describe() {
    echo "Home Assistant: automação da casa (Tuya, LG, Samsung e outros) num painel só"
}

cmd_status() {
    podman container exists "$CONTAINER"
}

configure() {
    ui_step "Configuração"
    if [[ -f $ENV_FILE ]] && ui_confirm "usar a configuração já salva em $ENV_FILE?" y; then
        ui_ok "configuração existente mantida"
        return
    fi
    local host port tz domain
    domain="$(proxy_domain)"
    ui_input host "endereço do Home Assistant no Caddy" "$(env_get HA_HOST "homeassistant${domain:+.$domain}")" is_hostname
    ui_input port "porta do Home Assistant no host" "$(env_get HA_PORT 8123)" is_port
    tz="$(timedatectl show -P Timezone 2>/dev/null || true)"
    tz="$(is_timezone "${tz:-UTC}" || printf 'UTC')"
    (
        umask 077
        printf "HA_HOST='%s'\nHA_PORT='%s'\nTZ='%s'\n" "$host" "$port" "$tz" > "$ENV_FILE.new"
    )
    mv "$ENV_FILE.new" "$ENV_FILE"
    ui_ok "configuração salva em $ENV_FILE"
}

remove_container() {
    compose down >/dev/null 2>&1 || true
    podman rm -f "$CONTAINER" >/dev/null 2>&1 || true
}

start_container() {
    local log
    ui_info "baixando a imagem (alguns minutos na primeira vez)..."
    if ! log="$(compose pull 2>&1)"; then
        printf '%s\n' "$log" | ui_prefix >&2
        ui_fail "falha ao baixar a imagem"
    fi
    remove_container
    if ! log="$(compose up -d 2>&1)"; then
        printf '%s\n' "$log" | ui_prefix >&2
        ui_fail "falha ao subir o container"
    fi
}

wait_ready() {
    local port=$1
    ui_info "aguardando o Home Assistant responder (a primeira vez leva alguns minutos)..."
    if ! timeout 600 bash -c "until curl -fsS -o /dev/null http://127.0.0.1:$port/manifest.json 2>/dev/null; do sleep 5; done"; then
        podman logs --tail 30 "$CONTAINER" 2>&1 | ui_prefix >&2
        ui_fail "o Home Assistant não respondeu em 10 minutos"
    fi
    ui_ok "container $CONTAINER rodando na porta $port"
}

trusted_proxies() {
    local subnet
    printf '%s\n' 127.0.0.1 ::1
    subnet="$(podman network inspect "$NETWORK" --format '{{range .Subnets}}{{.Subnet}} {{end}}' 2>/dev/null | awk '{ print $1 }')"
    [[ -n $subnet ]] && printf '%s\n' "$subnet"
    host_lan_ip
}

http_storage() {
    python3 -I - "$@" <<'PY'
import json, sys
mode, path, port, *proxies = sys.argv[1:]
data = json.load(open(path))
stable = data["data"]["stable"]
wanted = {"server_port": int(port), "use_x_forwarded_for": True, "trusted_proxies": proxies}
if mode == "check":
    sys.exit(0 if all(stable.get(k) == v for k, v in wanted.items()) else 1)
stable.update(wanted)
with open(path + ".new", "w") as out:
    json.dump(data, out, indent=2)
PY
}

proxy_settings() {
    local config=$1 port=$2 file="$1/.storage/http" proxies=()
    if ! timeout 120 bash -c "until [[ -s '$file' ]]; do sleep 2; done"; then
        ui_fail "o Home Assistant não criou $file"
    fi
    mapfile -t proxies < <(trusted_proxies)
    if http_storage check "$file" "$port" "${proxies[@]}"; then
        ui_ok "Home Assistant já aceita o Caddy como proxy (porta $port)"
        return
    fi
    podman stop "$CONTAINER" >/dev/null
    http_storage apply "$file" "$port" "${proxies[@]}"
    mv "$file.new" "$file"
    podman start "$CONTAINER" >/dev/null
    ui_ok "Home Assistant aceita o Caddy como proxy e escuta na porta $port (.storage/http)"
}

cmd_install() {
    state_setup remove_container .env .proxy
    configure
    local host config="$CONFIG" port
    host="$(env_get HA_HOST)"
    port="$(env_get HA_PORT)"

    ui_step "Host"
    host_base
    host_firewall_block_lan "$port"

    ui_step "Container"
    mkdir -p "$config"
    start_container
    proxy_settings "$config" "$port"
    wait_ready "$port"

    ui_step "Caddy"
    proxy_publish "$host" "http://host.containers.internal:$port"

    ui_step "Acesso"
    ui_ok "Home Assistant: https://$host"
    ui_warn "abra o endereço logo: o primeiro acesso cria o usuário administrador"
    ui_info "integrações sugeridas: Tuya (aparelhos Wi-Fi e o hub Zigbee), LG ThinQ, LG webOS TV e SmartThings"
}

cmd_remove() {
    local purge=false config="$CONFIG"
    [[ ${1:-} == --purge ]] && purge=true

    ui_step "Remoção"
    if cmd_status; then
        remove_container
        ui_ok "container $CONTAINER removido"
    else
        ui_info "nenhum container para remover"
    fi
    proxy_unpublish
    host_firewall_unblock_lan "$(env_get HA_PORT 8123)"

    if $purge && [[ -d $config ]]; then
        podman unshare rm -rf "$config"
        ui_ok "configuração apagada ($config)"
    else
        ui_info "configuração mantida em $config"
    fi
}

cmd_backup() {
    local copy="$CONFIG/home-assistant_v2.backup.db"
    if cmd_status && [[ -f $CONFIG/home-assistant_v2.db ]]; then
        if ! podman exec "$CONTAINER" python3 -c '
import sqlite3
source = sqlite3.connect("/config/home-assistant_v2.db")
target = sqlite3.connect("/config/home-assistant_v2.backup.db")
source.backup(target)
target.close()
source.close()
'; then
            ui_error "falha na cópia do banco do Home Assistant"
            return 1
        fi
        ui_ok "cópia consistente do banco do Home Assistant em $copy" >&2
    fi
    printf 'exclude %s\n' "$CONFIG/home-assistant_v2.db" "$CONFIG/home-assistant_v2.db-wal" "$CONFIG/home-assistant_v2.db-shm"
}

cmd_restore() {
    local log
    remove_container
    state_restore "$1"
    if [[ -f $CONFIG/home-assistant_v2.backup.db ]]; then
        podman unshare rm -f "$CONFIG/home-assistant_v2.db-wal" "$CONFIG/home-assistant_v2.db-shm"
        podman unshare mv "$CONFIG/home-assistant_v2.backup.db" "$CONFIG/home-assistant_v2.db"
        ui_ok "banco do Home Assistant restaurado da cópia do backup"
    fi
    if ! log="$(compose up -d 2>&1)"; then
        printf '%s\n' "$log" | ui_prefix >&2
        ui_fail "falha ao subir o container depois de restaurar"
    fi
    wait_ready "$(env_get HA_PORT 8123)"
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
