ASTROVERSO_HOME="$HOME/.astroverso"
STATE="$ASTROVERSO_HOME/${ASTROVERSO_PROJECT:-astroverso}"
ENV_FILE="$STATE/.env"
export ASTROVERSO_STATE="$STATE"

env_get() {
    local value
    value="$(grep -m1 "^$1=" "${3:-$ENV_FILE}" 2>/dev/null | cut -d= -f2- | tr -d "'")" || true
    printf '%s' "${value:-${2:-}}"
}

compose() {
    podman compose --env-file "$ENV_FILE" "$@"
}

config_reuse() {
    [[ -f $ENV_FILE ]] || return 1
    if [[ ${ASTROVERSO_REUSE_CONFIG:-} == 1 ]]; then
        ui_info "usando a configuração salva em $ENV_FILE"
        return 0
    fi
    ui_confirm "usar a configuração já salva em $ENV_FILE?" y
}

state_setup() {
    mkdir -p "$STATE"
    chmod 700 "$ASTROVERSO_HOME" "$STATE"
}

state_purge() {
    [[ -e $STATE ]] || return 0
    podman unshare rm -rf "$STATE"
    ui_ok "configuração e dados apagados ($STATE)"
}

project_images() {
    [[ -f docker-compose.yml ]] && sed -n 's/^ *image: *//p' docker-compose.yml
    [[ -f Dockerfile ]] && awk '
        /^ARG [A-Za-z_]+=/ { split($2, pair, "="); value[pair[1]] = pair[2] }
        /^FROM / { image = $2; for (name in value) gsub("\\$\\{" name "\\}", value[name], image); print image }
    ' Dockerfile
    return 0
}

images_remove() {
    local image count=0
    while read -r image; do
        [[ -n $image ]] && podman image exists "$image" || continue
        podman rmi -f "$image" >/dev/null 2>&1 && count=$((count + 1))
    done < <(project_images | sort -u)
    ((count == 0)) || ui_ok "$count imagem(ns) apagada(s)"
    return 0
}

state_restore() {
    local from=$1 keep
    shift
    [[ -d $from && -f $from/.env ]] || ui_fail "backup incompleto: $from não tem a configuração do $ASTROVERSO_PROJECT"
    mkdir -p "$ASTROVERSO_HOME"
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
    ui_ok "configuração do $ASTROVERSO_PROJECT restaurada em $STATE"
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

is_label() {
    [[ $1 =~ ^[[:alnum:]][[:alnum:]\ ._-]{0,39}$ ]] && printf '%s' "$1"
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
