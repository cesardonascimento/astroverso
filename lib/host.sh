export PODMAN_COMPOSE_WARNING_LOGS=false

host_compose() {
    if podman compose version >/dev/null 2>&1; then
        ui_ok "podman-compose já instalado"
    elif command -v dnf >/dev/null; then
        sudo dnf install -y -q podman-compose
        ui_ok "podman-compose instalado via dnf"
    elif command -v apt-get >/dev/null; then
        sudo apt-get install -y -qq podman-compose
        ui_ok "podman-compose instalado via apt"
    else
        ui_fail "instale o podman-compose manualmente: pip install --user podman-compose"
    fi
}

host_autostart() {
    if [[ $(loginctl show-user "$USER" -P Linger) == yes ]] \
        && systemctl --user is-enabled -q podman-restart.service 2>/dev/null; then
        ui_ok "inicialização automática já habilitada"
        return
    fi
    systemctl --user enable -q --now podman-restart.service
    loginctl enable-linger "$USER"
    ui_ok "containers sobem sozinhos após o boot"
}

host_firewall() {
    if ! command -v firewall-cmd >/dev/null || ! firewall-cmd --state >/dev/null 2>&1; then
        ui_ok "firewalld inativo, nada a liberar"
        return
    fi
    local rule changed=false
    for rule in "$@"; do
        if [[ $rule == */* ]]; then
            firewall-cmd -q --query-port="$rule" || { sudo firewall-cmd -q --permanent --add-port="$rule"; changed=true; }
        else
            firewall-cmd -q --query-service="$rule" || { sudo firewall-cmd -q --permanent --add-service="$rule"; changed=true; }
        fi
    done
    $changed && sudo firewall-cmd -q --reload
    ui_ok "firewall liberado: $*"
}

host_tailscale() {
    if ! command -v tailscale >/dev/null; then
        ui_warn "Tailscale não instalado, etapa ignorada"
        return
    fi
    systemctl is-active -q tailscaled || sudo systemctl enable -q --now tailscaled
    if ! tailscale status >/dev/null 2>&1; then
        sudo tailscale up --accept-routes --operator="$USER" 2>&1 | ui_prefix
    elif ! tailscale debug prefs | grep -q '"RouteAll": true'; then
        tailscale set --accept-routes 2>/dev/null || sudo tailscale set --accept-routes --operator="$USER"
    fi
    ui_ok "Tailscale conectado com --accept-routes ($(tailscale ip -4))"
}

host_lan_ip() {
    ip -4 route get 1.1.1.1 | grep -oP 'src \K\S+'
}

host_tailscale_ip() {
    tailscale ip -4 2>/dev/null || true
}
