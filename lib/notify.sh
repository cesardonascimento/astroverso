NOTIFY_QUEUE="$HOME/.astro/discord/fila"
NOTIFY_FLAGS="${XDG_STATE_HOME:-$HOME/.local/state}/astro/notify"
NOTIFY_REPEAT=86400

notify_send() {
    [[ -d $NOTIFY_QUEUE/saida && -d $NOTIFY_QUEUE/tmp ]] || return 2
    local name tmp
    name="$(date +%s%N)-$$"
    tmp="$NOTIFY_QUEUE/tmp/$name.json"
    if ! python3 -I -c '
import json, sys
host, project, text, *buttons = sys.argv[1:]
items = []
for button in buttons:
    label, action, arg = (button.split("|") + ["", ""])[:3]
    items.append({"rotulo": label, "acao": action, "arg": arg})
print(json.dumps({"texto": f"**{host}** · {project}\n{text}", "botoes": items}, ensure_ascii=False))
' "$(hostname -s)" "${ASTRO_PROJECT:-astro}" "$@" > "$tmp"; then
        rm -f "$tmp"
        ui_warn "não foi possível preparar o aviso para o Discord"
        return 1
    fi
    mv "$tmp" "$NOTIFY_QUEUE/saida/$name.json"
}

notify_flag() {
    printf '%s/%s-%s' "$NOTIFY_FLAGS" "${ASTRO_PROJECT:-astro}" "${1//\//_}"
}

notify_problem() {
    local key=$1 text=$2 flag
    shift 2
    flag="$(notify_flag "$key")"
    if [[ -f $flag ]] && (($(date +%s) - $(stat -c %Y "$flag") < NOTIFY_REPEAT)); then
        return 0
    fi
    mkdir -p "$NOTIFY_FLAGS"
    local status=0
    notify_send "⚠️ $text" "$@" || status=$?
    if ((status == 0)); then
        touch "$flag"
    elif ((status == 2)); then
        ui_info "aviso não enviado (projeto discord não instalado): $text"
    fi
    return 0
}

notify_resolved() {
    local flag
    flag="$(notify_flag "$1")"
    [[ -f $flag ]] || return 0
    notify_send "✅ $2" || true
    rm -f "$flag"
    return 0
}
