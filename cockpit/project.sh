#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"

ASTRO_PROJECT=cockpit
source ../lib/ui.sh
source ../lib/host.sh
source ../lib/env.sh
source ../lib/proxy.sh

CONF=/etc/cockpit/cockpit.conf
PORT=9090

cmd_describe() {
    echo "Cockpit: painel web da máquina e dos containers"
}

cmd_status() {
    systemctl is-enabled -q cockpit.socket 2>/dev/null
}

configure() {
    ui_step "Configuração"
    if [[ -f .env ]] && ui_confirm "usar a configuração já salva em cockpit/.env?" y; then
        ui_ok "configuração existente mantida"
        return
    fi
    local host domain
    domain="$(proxy_domain)"
    ui_input host "endereço do Cockpit no Caddy" "$(env_get COCKPIT_HOST "$(hostname -s)${domain:+.$domain}")" is_hostname
    printf "COCKPIT_HOST='%s'\n" "$host" > .env
    ui_ok "configuração salva em cockpit/.env"
}

install_packages() {
    if rpm -q cockpit cockpit-podman >/dev/null 2>&1 || dpkg -s cockpit cockpit-podman >/dev/null 2>&1; then
        ui_ok "pacotes do Cockpit já instalados"
    elif command -v dnf >/dev/null; then
        sudo dnf install -y -q cockpit cockpit-podman
        ui_ok "Cockpit instalado via dnf"
    elif command -v apt-get >/dev/null; then
        sudo apt-get install -y -qq cockpit cockpit-podman
        ui_ok "Cockpit instalado via apt"
    else
        ui_fail "instale o cockpit e o cockpit-podman manualmente"
    fi
}

configure_proxy_mode() {
    local host=$1 wanted
    wanted="$(printf '[WebService]\nOrigins = https://%s wss://%s\nProtocolHeader = X-Forwarded-Proto\nAllowUnencrypted = true\n' "$host" "$host")"
    if [[ $(cat "$CONF" 2>/dev/null) == "$wanted" ]]; then
        ui_ok "Cockpit já configurado para funcionar atrás do Caddy"
        return
    fi
    printf '%s\n' "$wanted" | sudo tee "$CONF" >/dev/null
    sudo systemctl try-restart cockpit.service
    ui_ok "Cockpit configurado para funcionar atrás do Caddy ($host)"
}

cmd_install() {
    configure
    local host
    host="$(env_get COCKPIT_HOST)"

    ui_step "Host"
    host_base
    install_packages
    configure_proxy_mode "$host"
    host_firewall_block_lan "$PORT"

    ui_step "Serviços"
    sudo systemctl enable -q --now cockpit.socket
    ui_ok "Cockpit ativo (inicia sob demanda na porta $PORT)"
    systemctl --user enable -q --now podman.socket
    ui_ok "containers do usuário $USER visíveis no Cockpit"

    ui_step "Caddy"
    proxy_publish "$host" "http://host.containers.internal:$PORT"

    ui_step "Acesso"
    ui_ok "https://$host (login com o usuário e a senha do sistema)"
}

cmd_remove() {
    local purge=false
    [[ ${1:-} == --purge ]] && purge=true

    ui_step "Remoção"
    if cmd_status; then
        sudo systemctl disable -q --now cockpit.socket cockpit.service
        ui_ok "Cockpit desativado"
    else
        ui_info "Cockpit já estava desativado"
    fi
    proxy_unpublish
    if $purge && [[ -f $CONF ]]; then
        sudo rm -f "$CONF"
        ui_ok "configuração de proxy do Cockpit apagada"
    fi
    ui_info "pacotes do sistema mantidos (cockpit, cockpit-podman)"
}

case "${1:-}" in
    describe) cmd_describe ;;
    status)   cmd_status ;;
    actions)  ;;
    install)  cmd_install ;;
    remove)   shift; cmd_remove "$@" ;;
    *)        ui_fail "uso: $0 describe | status | actions | install | remove [--purge]" ;;
esac
