NOTIFY_ENV="$HOME/.astro/host.env"
NOTIFY_FLAGS="${XDG_STATE_HOME:-$HOME/.local/state}/astro/notify"
NOTIFY_REPEAT=86400

is_discord_webhook() {
    [[ $1 =~ ^https://(ptb\.|canary\.)?discord(app)?\.com/api/webhooks/[0-9]+/[A-Za-z0-9_-]+$ ]] && printf '%s' "$1"
}

notify_webhook() {
    grep -m1 '^DISCORD_WEBHOOK=' "$NOTIFY_ENV" 2>/dev/null | cut -d= -f2- | tr -d "'" || true
}

notify_discord() {
    local webhook=$1 text=$2
    python3 -I -c '
import json, sys
print(json.dumps({"username": "astro", "content": sys.argv[1][:1900]}))
' "$text" | curl -fsS --max-time 20 -o /dev/null -H 'Content-Type: application/json' --data-binary @- \
        -K <(printf 'url = "%s"\n' "$webhook")
}

notify_send() {
    local webhook
    webhook="$(notify_webhook)"
    [[ -n $webhook ]] || return 2
    if ! notify_discord "$webhook" "**$(hostname -s)** · ${ASTRO_PROJECT:-astro}"$'\n'"$1" 2>/dev/null; then
        ui_warn "não foi possível avisar no Discord"
        return 1
    fi
}

notify_flag() {
    printf '%s/%s-%s' "$NOTIFY_FLAGS" "${ASTRO_PROJECT:-astro}" "${1//\//_}"
}

notify_problem() {
    local flag
    flag="$(notify_flag "$1")"
    if [[ -f $flag ]] && (($(date +%s) - $(stat -c %Y "$flag") < NOTIFY_REPEAT)); then
        return 0
    fi
    mkdir -p "$NOTIFY_FLAGS"
    if notify_send "⚠️ $2"; then
        touch "$flag"
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

notify_save() {
    local rest
    mkdir -p "${NOTIFY_ENV%/*}"
    rest="$(grep -v '^DISCORD_WEBHOOK=' "$NOTIFY_ENV" 2>/dev/null || true)"
    (
        umask 077
        {
            [[ -n $rest ]] && printf '%s\n' "$rest"
            [[ -n $1 ]] && printf "DISCORD_WEBHOOK='%s'\n" "$1"
        } > "$NOTIFY_ENV.new"
    )
    mv "$NOTIFY_ENV.new" "$NOTIFY_ENV"
    chmod 600 "$NOTIFY_ENV"
}

notify_configure() {
    ui_step "Notificações no Discord"
    local choice webhook
    if [[ -n $(notify_webhook) ]]; then
        ui_menu choice "As notificações estão ligadas. O que fazer?" \
            "Enviar uma mensagem de teste" "Trocar o webhook" "Desligar as notificações" "Voltar"
        case $choice in
            0)
                if notify_send "🔔 mensagem de teste"; then
                    ui_ok "mensagem de teste enviada"
                else
                    ui_error "o Discord recusou a mensagem: confira o webhook ou troque por outro"
                fi
                return 0
                ;;
            2)
                notify_save ""
                ui_ok "notificações desligadas (o webhook foi apagado de $NOTIFY_ENV)"
                ui_info "para apagá-lo também no Discord: Configurações do canal → Integrações → Webhooks"
                return 0
                ;;
            3) return 0 ;;
        esac
    fi
    ui_info "o astro avisa num canal do Discord quando algo precisa da sua atenção (ex.: backup parado)"
    ui_info "no Discord: Configurações do canal → Integrações → Webhooks → Novo webhook → Copiar URL do webhook"
    ui_info "quem tiver essa URL consegue escrever no canal: ela fica só em $NOTIFY_ENV (só $USER lê)"
    while true; do
        ui_secret webhook "URL do webhook (não aparece na tela)"
        if ! is_discord_webhook "$webhook" >/dev/null; then
            ui_warn "não parece uma URL de webhook do Discord (https://discord.com/api/webhooks/...)"
            continue
        fi
        if notify_discord "$webhook" "🔔 **$(hostname -s)** · astro"$'\n'"notificações ligadas: os avisos do astro chegam neste canal" 2>/dev/null; then
            break
        fi
        ui_warn "o Discord recusou a mensagem: confira a URL e tente de novo"
    done
    notify_save "$webhook"
    ui_ok "notificações ligadas: confira a mensagem de teste no canal"
    ui_info "no celular, deixe as notificações desse canal em \"Todas as mensagens\""
}
