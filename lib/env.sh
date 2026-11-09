ASTRO_HOME="$HOME/.astro"
STATE="$ASTRO_HOME/${ASTRO_PROJECT:-astro}"
ENV_FILE="$STATE/.env"
export ASTRO_STATE="$STATE"

env_get() {
    local value
    value="$(grep -m1 "^$1=" "${3:-$ENV_FILE}" 2>/dev/null | cut -d= -f2- | tr -d "'")" || true
    printf '%s' "${value:-${2:-}}"
}

compose() {
    podman compose --env-file "$ENV_FILE" "$@"
}

state_setup() {
    local stop=$1 item pending=()
    shift
    mkdir -p "$STATE"
    chmod 700 "$ASTRO_HOME" "$STATE"
    for item in "$@"; do
        [[ -e $item ]] && pending+=("$item")
    done
    ((${#pending[@]})) || return 0
    ui_step "Migração para $STATE"
    "$stop"
    for item in "${pending[@]}"; do
        if [[ -e $STATE/$item ]]; then
            ui_warn "$item existe nos dois lugares: mantido o de $STATE, o antigo ficou em $PWD/$item"
            continue
        fi
        podman unshare mv "$item" "$STATE/$item"
        ui_ok "$item movido para $STATE (donos e permissões mantidos)"
    done
}

state_restore() {
    local from=$1 keep
    shift
    [[ -d $from && -f $from/.env ]] || ui_fail "backup incompleto: $from não tem a configuração do $ASTRO_PROJECT"
    mkdir -p "$ASTRO_HOME"
    if [[ -d $STATE ]]; then
        podman unshare rm -rf "$STATE.restaurando"
        podman unshare mv "$STATE" "$STATE.restaurando"
    fi
    podman unshare cp -a "$from" "$STATE"
    for keep in "$@"; do
        podman unshare rm -rf "${STATE:?}/$keep"
        if [[ -e $STATE.restaurando/$keep ]]; then
            podman unshare mv "$STATE.restaurando/$keep" "$STATE/$keep"
        fi
    done
    podman unshare rm -rf "$STATE.restaurando"
    chmod 700 "$STATE"
    ui_ok "configuração do $ASTRO_PROJECT restaurada em $STATE"
}

is_port() {
    [[ $1 =~ ^[0-9]{1,5}$ ]] && (($1 >= 1 && $1 <= 65535)) && printf '%s' "$1"
}

is_ipv4() {
    local octet
    [[ $1 =~ ^([0-9]{1,3})\.([0-9]{1,3})\.([0-9]{1,3})\.([0-9]{1,3})$ ]] || return 1
    for octet in "${BASH_REMATCH[@]:1}"; do ((10#$octet <= 255)) || return 1; done
    printf '%s' "$1"
}

is_hostname() {
    local host="${1,,}"
    host="${host%.}"
    [[ $host =~ ^([a-z0-9]([a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,}$ ]] && printf '%s' "$host"
}

is_name() {
    [[ $1 =~ ^[A-Za-z0-9._@-]+$ ]] && printf '%s' "$1"
}

is_timezone() {
    [[ $1 =~ ^[A-Za-z0-9_+/-]+$ && -f /usr/share/zoneinfo/$1 ]] && printf '%s' "$1"
}

is_username() {
    [[ $1 =~ ^[a-z_][a-z0-9_-]{0,31}$ ]] && printf '%s' "$1"
}

is_path() {
    local path="${1%/}"
    [[ $path =~ ^/[[:alnum:]\ ._/-]+$ && $path != *..* ]] && printf '%s' "$path"
}

is_folder() {
    [[ $1 =~ ^[A-Za-z0-9_-][A-Za-z0-9._-]*$ ]] && printf '%s' "$1"
}

is_email() {
    [[ $1 =~ ^[A-Za-z0-9._%+-]+@([A-Za-z0-9-]+\.)+[A-Za-z]{2,}$ ]] && printf '%s' "${1,,}"
}

is_time() {
    [[ $1 =~ ^([01]?[0-9]|2[0-3]):([0-5][0-9])$ ]] && printf '%02d:%s' "$((10#${BASH_REMATCH[1]}))" "${BASH_REMATCH[2]}"
}

is_number() {
    [[ $1 =~ ^[0-9]{1,5}$ ]] && (($1 > 0)) && printf '%s' "$((10#$1))"
}
