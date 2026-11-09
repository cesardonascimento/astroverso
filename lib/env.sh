env_get() {
    local value
    value="$(grep -m1 "^$1=" .env 2>/dev/null | cut -d= -f2- | tr -d "'")" || true
    printf '%s' "${value:-${2:-}}"
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
    [[ $path =~ ^/[A-Za-z0-9._/-]+$ && $path != *..* ]] && printf '%s' "$path"
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
