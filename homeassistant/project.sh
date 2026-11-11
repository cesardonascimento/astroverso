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
    echo "Home Assistant: automação da casa, com aparelhos de várias marcas num painel só"
}

cmd_status() {
    podman container exists "$CONTAINER"
}

configure() {
    ui_step "Configuração"
    if [[ -f $ENV_FILE ]] && ui_confirm "usar a configuração já salva em $ENV_FILE?" y; then
        ui_ok "configuração existente mantida"
        grep -q '^HA_USER=' "$ENV_FILE" || printf "HA_NAME='Astro'\nHA_USER='astro'\n" >> "$ENV_FILE"
        return
    fi
    local host port tz domain name user
    domain="$(proxy_domain)"
    ui_input host "endereço do Home Assistant no Caddy" "$(env_get HA_HOST "homeassistant${domain:+.$domain}")" is_hostname
    ui_input port "porta do Home Assistant no host" "$(env_get HA_PORT 8123)" is_port
    ui_input name "nome da casa no Home Assistant (aparece no app)" "$(env_get HA_NAME Astro)" is_label
    ui_input user "usuário administrador do Home Assistant" "$(env_get HA_USER astro)" is_username
    tz="$(timedatectl show -P Timezone 2>/dev/null || true)"
    tz="$(is_timezone "${tz:-UTC}" || printf 'UTC')"
    (
        umask 077
        printf "HA_HOST='%s'\nHA_PORT='%s'\nTZ='%s'\nHA_NAME='%s'\nHA_USER='%s'\n" "$host" "$port" "$tz" "$name" "$user" > "$ENV_FILE.new"
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
    podman network exists "$NETWORK" || podman network create "$NETWORK" >/dev/null
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

core_storage() {
    python3 -I - "$@" <<'PY'
import json, os, sys
mode, path, *pairs = sys.argv[1:]
numbers = {"latitude", "longitude", "elevation", "radius"}
wanted = {}
for pair in pairs:
    key, value = pair.split("=", 1)
    wanted[key] = float(value) if key in numbers else value
if os.path.exists(path):
    data = json.load(open(path))
elif mode == "check":
    sys.exit(1)
else:
    data = {"version": 1, "minor_version": 4, "key": "core.config", "data": {
        "latitude": 52.3731339, "longitude": 4.8903147, "elevation": 0, "radius": 100,
        "unit_system_v2": "metric", "location_name": "Home", "time_zone": "UTC", "external_url": None,
        "internal_url": None, "currency": "EUR", "country": None, "language": "en"}}
current = data["data"]
if mode == "check":
    sys.exit(0 if all(current.get(k) == v for k, v in wanted.items()) else 1)
current.update(wanted)
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

ha_country() {
    awk -v tz="$(env_get TZ UTC)" '$3 == tz { print $1; exit }' /usr/share/zoneinfo/zone.tab 2>/dev/null || true
}

ha_locale() {
    local country
    country="$(ha_country)"
    [[ -n $country ]] && locale -a 2>/dev/null | grep -m1 -E "^[a-z]{2}_${country}\.utf-?8$" && return 0
    printf '%s' "${LANG%%.*}"
}

ha_language() {
    local lang
    lang="$(ha_locale)"
    lang=${lang%%.*}
    [[ $lang =~ ^[a-z]{2}(_[A-Z]{2})?$ ]] || lang=en
    printf '%s' "${lang/_/-}"
}

ha_currency() {
    local currency
    currency="$(LC_ALL="$(ha_locale)" locale int_curr_symbol 2>/dev/null | tr -d ' ')" || currency=""
    [[ $currency =~ ^[A-Z]{3}$ ]] && printf '%s' "$currency"
    return 0
}

ha_coordinates() {
    awk -v tz="$(env_get TZ UTC)" '$3 == tz { print $2; exit }' /usr/share/zoneinfo/zone.tab 2>/dev/null | python3 -I -c '
import re, sys
text = sys.stdin.read().strip()
m = re.match(r"([+-]\d{2})(\d{2})(\d{2})?([+-]\d{3})(\d{2})(\d{2})?$", text)
if m:
    def deg(d, mi, se):
        value = abs(int(d)) + int(mi) / 60 + int(se or 0) / 3600
        return -value if d.startswith("-") else value
    print(round(deg(m[1], m[2], m[3]), 4), round(deg(m[4], m[5], m[6]), 4))
'
}

ha_post() {
    local url=$1 headers=$2
    curl -fsS -m 30 -X POST -H 'Content-Type: application/json' ${headers:+-H "@$headers"} --data-binary @- "$url"
}

onboarding() {
    local port=$1 base="http://127.0.0.1:$1" client="http://127.0.0.1:$1/" user name password code token refresh
    local headers result
    result="$(curl -fsS -m 10 "$base/api/onboarding" 2>/dev/null)" || result=""
    if ! python3 -I -c 'import json, sys; sys.exit(0 if any(s["step"] == "user" and not s["done"] for s in json.loads(sys.argv[1])) else 1)' "${result:-[]}" 2>/dev/null; then
        ui_ok "Home Assistant já configurado (usuário administrador existente)"
        return 1
    fi
    user="$(env_get HA_USER astro)"
    name="$(env_get HA_NAME Astro)"
    ui_info "o Home Assistant ainda não tem usuário: a instalação faz a configuração inicial"
    ui_secret password "senha do usuário $user no Home Assistant"
    if ! code="$(printf '%s' "$password" | python3 -I -c '
import json, sys
print(json.dumps({"client_id": sys.argv[1], "name": sys.argv[2], "username": sys.argv[2],
                  "password": sys.stdin.read(), "language": sys.argv[3]}))
' "$client" "$user" "$(ha_language)" | ha_post "$base/api/onboarding/users" "" | python3 -I -c 'import json, sys; print(json.load(sys.stdin)["auth_code"])')"; then
        ui_warn "não foi possível criar o usuário: abra https://$(env_get HA_HOST) e faça a configuração inicial por lá"
        return 1
    fi
    result="$(printf 'grant_type=authorization_code&code=%s&client_id=%s' "$code" "$client" \
        | curl -fsS -m 30 --data-binary @- "$base/auth/token")"
    token="$(python3 -I -c 'import json, sys; print(json.loads(sys.argv[1])["access_token"])' "$result")"
    refresh="$(python3 -I -c 'import json, sys; print(json.loads(sys.argv[1])["refresh_token"])' "$result")"
    headers="$(mktemp)"
    printf 'Authorization: Bearer %s\n' "$token" > "$headers"
    echo '{}' | ha_post "$base/api/onboarding/core_config" "$headers" >/dev/null
    echo '{}' | ha_post "$base/api/onboarding/analytics" "$headers" >/dev/null
    printf '{"client_id": "%s", "redirect_uri": "%s?auth_callback=1"}' "$client" "$client" \
        | ha_post "$base/api/onboarding/integration" "$headers" >/dev/null
    rm -f "$headers"
    printf 'token=%s&action=revoke' "$refresh" | curl -fsS -m 30 --data-binary @- "$base/auth/token" >/dev/null || true
    ui_ok "usuário administrador $user criado e configuração inicial concluída"
    return 0
}

core_settings() {
    local config=$1 onboarded=$2 file="$1/.storage/core.config" host country pairs=()
    host="$(env_get HA_HOST)"
    pairs=("internal_url=https://$host" "external_url=https://$host")
    if $onboarded; then
        local currency lat lon
        country="$(ha_country)"
        currency="$(ha_currency)"
        read -r lat lon < <(ha_coordinates) || true
        pairs+=("location_name=$(env_get HA_NAME Astro)" "language=$(ha_language)" "time_zone=$(env_get TZ UTC)")
        [[ -z $country ]] || pairs+=("country=$country")
        [[ -z $currency ]] || pairs+=("currency=$currency")
        [[ $country == US ]] && pairs+=("unit_system_v2=us_customary")
        [[ -z $lat ]] || pairs+=("latitude=$lat" "longitude=$lon")
    fi
    if core_storage check "$file" "${pairs[@]}"; then
        ui_ok "o Home Assistant já se anuncia como https://$host"
        return
    fi
    podman stop "$CONTAINER" >/dev/null
    core_storage apply "$file" "${pairs[@]}"
    mv "$file.new" "$file"
    podman start "$CONTAINER" >/dev/null
    ui_ok "o Home Assistant se anuncia como https://$host (o app encontra o endereço com HTTPS)"
    if $onboarded; then
        ui_ok "casa \"$(env_get HA_NAME Astro)\"${country:+, país $country}, idioma $(ha_language)${currency:+, moeda $currency}; a localização exata se ajusta em Configurações → Sistema → Geral"
    fi
}

cmd_install() {
    state_setup
    configure
    local host config="$CONFIG" port
    host="$(env_get HA_HOST)"
    port="$(env_get HA_PORT)"

    ui_step "Host"
    host_firewall_block_lan "$port"

    ui_step "Container"
    mkdir -p "$config"
    start_container
    proxy_settings "$config" "$port"
    wait_ready "$port"
    local onboarded=false
    if onboarding "$port"; then
        onboarded=true
    fi
    core_settings "$config" "$onboarded"
    wait_ready "$port"

    ui_step "Caddy"
    proxy_publish "$host" "http://host.containers.internal:$port"

    ui_step "Acesso"
    ui_ok "Home Assistant: https://$host"
    ui_info "no celular ou tablet, no app do Home Assistant, use \"Inserir endereço manualmente\": https://$host"
    ui_info "os aparelhos entram pelas integrações: Configurações → Dispositivos e serviços → Adicionar integração"
}

cmd_remove() {
    ui_step "Remoção"
    remove_container
    images_remove
    ui_ok "container $CONTAINER removido"
    host_firewall_unblock_lan "$(env_get HA_PORT 8123)"
    proxy_unpublish
    state_purge
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
    remove)   cmd_remove ;;
    backup)   cmd_backup ;;
    restore)  shift; cmd_restore "$1" ;;
    *)        ui_fail "uso: $0 describe | status | actions | install | remove | backup | restore <pasta>" ;;
esac
