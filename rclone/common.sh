BACKUP_DIR="$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")"
DATA="$STATE/data"
CONFIG_KEY="$DATA/config-backup.key"
RCLONE_CONF="$DATA/rclone.conf"
TARGETS="$DATA/targets"
PROVIDERS="$BACKUP_DIR/providers"

rclone_run() {
    rclone --config "$RCLONE_CONF" "$@"
}

rclone_get() {
    [[ -f $RCLONE_CONF ]] || return 0
    awk -v section="[$1]" -v key="$2" '
        $0 == section { inside = 1; next }
        /^\[/ { inside = 0 }
        inside && $1 == key { sub(/^[^=]*= */, ""); print; exit }
    ' "$RCLONE_CONF"
}

rclone_section_remove() {
    [[ -f $RCLONE_CONF ]] || return 0
    local rest
    rest="$(awk -v section="[$1]" '
        $0 == section { skip = 1; next }
        /^\[/ { skip = 0 }
        !skip { print }
    ' "$RCLONE_CONF")"
    (umask 077 && printf '%s\n' "$rest" | sed '/^$/N;/^\n$/D' > "$RCLONE_CONF.new")
    mv "$RCLONE_CONF.new" "$RCLONE_CONF"
}

rclone_section_write() {
    local name=$1
    shift
    mkdir -p "$DATA"
    chmod 700 "$DATA"
    rclone_section_remove "$name"
    (umask 077 && { printf '\n[%s]\n' "$name"; printf '%s\n' "$@"; } >> "$RCLONE_CONF")
}

provider_load() {
    unset -f provider_describe provider_default_name provider_options provider_configure
    source "$PROVIDERS/$1.sh"
}

target_names() {
    local file
    for file in "$TARGETS"/*.env; do
        [[ -f $file ]] && basename "$file" .env
    done
    return 0
}

target_get() {
    local value
    value="$(grep -m1 "^$2=" "$TARGETS/$1.env" 2>/dev/null | cut -d= -f2- | tr -d "'")" || true
    printf '%s' "$value"
}

target_set() {
    local file="$TARGETS/$1.env" rest
    rest="$(grep -v "^$2=" "$file" 2>/dev/null || true)"
    (umask 077 && { [[ -n $rest ]] && printf '%s\n' "$rest"; printf "%s='%s'\n" "$2" "$3"; } > "$file.new")
    mv "$file.new" "$file"
}
