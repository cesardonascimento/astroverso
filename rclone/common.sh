BACKUP_DIR="$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")"
DATA="$STATE/data"
CONFIG_KEY="$DATA/config-backup.key"
LOCK="${XDG_RUNTIME_DIR:-/tmp}/astroverso-rclone.lock"
CONFIG_LOCK="${XDG_RUNTIME_DIR:-/tmp}/astroverso-rclone-config.lock"
VERSION_PATTERN='^[0-9]{4}-[0-9]{2}-[0-9]{2}_[0-9]{6}(_[a-z-]+)?$'

config_versions() {
    local dest=$1 dir name
    for dir in "$dest"/*/; do
        name="$(basename "$dir")"
        [[ $name =~ $VERSION_PATTERN ]] && printf '%s\n' "$name"
    done | sort -r
    return 0
}
RCLONE_CONF="$DATA/rclone.conf"
TARGETS="$DATA/targets"
SHARES="$DATA/rede"
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

file_get() {
    local value
    value="$(grep -m1 "^$2=" "$1" 2>/dev/null | cut -d= -f2- | tr -d "'")" || true
    printf '%s' "$value"
}

file_set() {
    local file=$1 rest
    rest="$(grep -v "^$2=" "$file" 2>/dev/null || true)"
    (umask 077 && { [[ -n $rest ]] && printf '%s\n' "$rest"; printf "%s='%s'\n" "$2" "$3"; } > "$file.new")
    mv "$file.new" "$file"
}

target_get() {
    file_get "$TARGETS/$1.env" "$2"
}

target_set() {
    file_set "$TARGETS/$1.env" "$2" "$3"
}

share_names() {
    local file
    for file in "$SHARES"/*.env; do
        [[ -f $file ]] && basename "$file" .env
    done
    return 0
}

share_get() {
    file_get "$SHARES/$1.env" "$2"
}

share_set() {
    file_set "$SHARES/$1.env" "$2" "$3"
}

share_remote() {
    local folder
    folder="$(share_get "$1" FOLDER)"
    printf 'rede-%s:/C:/ProgramData/Astroverso/snapshot-%s%s' "$1" "$1" "${folder:+/$folder}"
}

share_responds() {
    timeout 3 bash -c "</dev/tcp/$1/22" 2>/dev/null
}

share_ssh() {
    local name=$1
    shift
    ssh -i "$SHARES/$name.key" -o IdentitiesOnly=yes -o BatchMode=yes -o LogLevel=ERROR -o UpdateHostKeys=yes -o ConnectTimeout=10 \
        -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile="$SHARES/$name.known_hosts" \
        "$(share_get "$name" USER)@$(share_get "$name" HOST)" "$@"
}

share_snapshot() {
    local name=$1 action=$2 script
    script="$(sed -e "s/__NOME__/$name/g" -e "s/__ACAO__/$action/g" -e "s/__DRIVE__/$(share_get "$name" DRIVE)/g" \
        "$BACKUP_DIR/snapshot.ps1" | iconv -f UTF-8 -t UTF-16LE | base64 -w0)"
    share_ssh "$name" powershell -NoProfile -NonInteractive -EncodedCommand "$script" < /dev/null
}
