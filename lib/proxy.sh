proxy_domain() {
    [[ -f ../caddy/.env ]] && (cd ../caddy && env_get CADDY_DOMAIN)
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
    echo "$1 $2" > .proxy
    ui_ok "rota declarada no Caddy: https://$1 → $2"
    proxy_reload
}

proxy_unpublish() {
    [[ -f .proxy ]] || return 0
    rm -f .proxy
    ui_ok "rota removida do Caddy"
    proxy_reload
}
