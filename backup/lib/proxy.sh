proxy_domain() {
    env_get CADDY_DOMAIN "" "$ASTROVERSO_HOME/caddy/.env"
    return 0
}

proxy_reload() {
    if [[ -x ../caddy/project.sh ]] && ../caddy/project.sh status; then
        ../caddy/project.sh action reload
    else
        ui_info "Caddy não instalado; a rota será publicada quando ele for instalado"
    fi
}

proxy_publish() {
    mkdir -p "$STATE"
    echo "$1 $2" > "$STATE/.proxy"
    ui_ok "rota declarada no Caddy: https://$1 → $2"
    proxy_reload
}

proxy_unpublish() {
    [[ -f $STATE/.proxy ]] || return 0
    rm -f "$STATE/.proxy"
    ui_ok "rota removida do Caddy"
    proxy_reload
}
