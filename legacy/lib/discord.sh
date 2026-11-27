DISCORD_CLIENT=homelab
DISCORD_SERVER_STATE="$HOME/.astroverso/discord"
DISCORD_HOST_ENV="$HOME/.astroverso/host.env"
DISCORD_SPOOL="${XDG_STATE_HOME:-$HOME/.local/state}/astroverso/avisos"

discord_conf() {
    local value
    value="$(grep -m1 "^$1=" "$2" 2>/dev/null | cut -d= -f2- | tr -d "'")" || true
    printf '%s' "$value"
}

discord_url() {
    local url host
    url="$(discord_conf DISCORD_URL "$DISCORD_HOST_ENV")"
    if [[ -z $url ]]; then
        host="$(discord_conf DISCORD_HOST "$DISCORD_SERVER_STATE/.env")"
        [[ -n $host ]] && url="https://$host"
    fi
    [[ -n $url ]] && printf '%s' "${url%/}"
}

discord_key() {
    local key
    key="$(discord_conf DISCORD_KEY "$DISCORD_HOST_ENV")"
    [[ -n $key ]] || key="$(cat "$DISCORD_SERVER_STATE/clientes/$DISCORD_CLIENT.key" 2>/dev/null)" || true
    [[ -n $key ]] && printf '%s' "$key"
}

discord_ready() {
    discord_url >/dev/null && discord_key >/dev/null
}

discord_api() {
    local method=$1 path=$2 data=${3:-} url key
    url="$(discord_url)" && key="$(discord_key)" || return 2
    printf 'header = "Authorization: Bearer %s"\n' "$key" \
        | curl -sf -m "${DISCORD_TIMEOUT:-20}" -K - -X "$method" -H 'Content-Type: application/json' \
            ${data:+--data-binary "@$data"} "$url$path"
}

discord_flush() {
    local file
    for file in "$DISCORD_SPOOL"/*.json; do
        [[ -f $file ]] || continue
        discord_api POST /v1/mensagens "$file" >/dev/null || return 1
        rm -f "$file"
    done
}
