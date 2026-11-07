#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"

ASTRO_PROJECT=adguard
source ../lib/ui.sh
source ../lib/host.sh

CONTAINER=astro-adguard
IMAGE=localhost/astro-adguard:latest
CONF_FILE=data/conf/AdGuardHome.yaml

env_value() {
    local value
    value="$(grep -m1 "^$1=" .env 2>/dev/null | cut -d= -f2- | tr -d "'")" || true
    printf '%s' "${value:-${2:-}}"
}

cmd_describe() {
    echo "AdGuard Home: DNS da rede com bloqueio de anúncios"
}

cmd_status() {
    podman container exists "$CONTAINER"
}

remove_container() {
    podman compose down >/dev/null 2>&1 || true
    podman rm -f "$CONTAINER" >/dev/null 2>&1 || true
}

NEW_PASSWORD=""

normalize_domain() {
    local domain="${1,,}"
    domain="${domain#\*.}"
    domain="${domain%.}"
    [[ $domain =~ ^([a-z0-9]([a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,}$ ]] || return 1
    printf '%s' "$domain"
}

configure() {
    ui_step "Configuração"
    if [[ -f .env ]] && ui_confirm "usar a configuração já salva em adguard/.env?" y; then
        ui_ok "configuração existente mantida"
        return
    fi

    local username language timezone web_port dns_ip
    ui_input  username "usuário do painel" "$(env_value ADGUARD_USERNAME admin)"
    ui_secret NEW_PASSWORD "senha do painel"
    ui_input  web_port "porta do painel no host" "$(env_value WEB_PORT 8080)"
    ui_input  dns_ip   "IP do host onde o DNS escuta (0.0.0.0 = todos)" "$(env_value DNS_BIND_IP 0.0.0.0)"
    ui_input  timezone "fuso horário" "$(timedatectl show -P Timezone 2>/dev/null || echo America/Sao_Paulo)"
    ui_input  language "idioma do painel" "$(env_value ADGUARD_LANGUAGE pt-br)"

    ui_step "Reescritas DNS"
    local rewrite_answer="" domains=() domain
    if ui_confirm "adicionar domínios de reescrita (*.dominio → IP)?" n; then
        local default_answer=$dns_ip
        [[ $default_answer == 0.0.0.0 ]] && default_answer="$(host_lan_ip)"
        ui_input rewrite_answer "IP de destino das reescritas" "$(env_value ADGUARD_REWRITE_ANSWER "$default_answer")"
        ui_list domains "domínio" normalize_domain
        for domain in "${domains[@]}"; do
            ui_ok "*.$domain → $rewrite_answer"
        done
        ((${#domains[@]})) || ui_info "nenhum domínio informado"
    else
        ui_info "sem reescritas"
    fi

    (
        umask 077
        cat > .env <<EOF
ADGUARD_USERNAME='$username'
ADGUARD_LANGUAGE='$language'
TZ='$timezone'
DNS_BIND_IP='$dns_ip'
WEB_PORT='$web_port'
ADGUARD_REWRITE_ANSWER='$rewrite_answer'
ADGUARD_REWRITES='$(IFS=,; echo "${domains[*]}")'
EOF
    )

    if [[ -f $CONF_FILE ]]; then
        mv "$CONF_FILE" "$CONF_FILE.bak"
        ui_info "config anterior do AdGuard salva em adguard/$CONF_FILE.bak"
    fi
}

save_password_hash() {
    local hash
    hash="$(printf '%s' "$NEW_PASSWORD" \
        | podman run --rm -i --entrypoint htpasswd "$IMAGE" -niBC 10 "" | tr -d ':\n')"
    printf "ADGUARD_PASSWORD_HASH='%s'\n" "$hash" >> .env
    ui_ok "configuração salva em adguard/.env (senha guardada como hash bcrypt)"
}

setup_port53() {
    if (( $(sysctl -n net.ipv4.ip_unprivileged_port_start) <= 53 )); then
        ui_ok "porta 53 já liberada para Podman rootless"
    else
        echo "net.ipv4.ip_unprivileged_port_start=53" | sudo tee /etc/sysctl.d/99-astro-adguard.conf >/dev/null
        sudo sysctl -q -p /etc/sysctl.d/99-astro-adguard.conf
        ui_ok "porta 53 liberada para Podman rootless"
    fi

    local conf=/etc/systemd/resolved.conf.d/99-astro-adguard.conf
    if ! systemctl is-active --quiet systemd-resolved; then
        ui_ok "systemd-resolved inativo, porta 53 livre"
    elif [[ -f $conf ]]; then
        ui_ok "DNS stub do systemd-resolved já desativado"
    else
        sudo mkdir -p "$(dirname "$conf")"
        printf '[Resolve]\nDNSStubListener=no\n' | sudo tee "$conf" >/dev/null
        sudo ln -sf /run/systemd/resolve/resolv.conf /etc/resolv.conf
        sudo systemctl restart systemd-resolved
        ui_ok "DNS stub do systemd-resolved desativado, porta 53 livre"
    fi
}

cmd_install() {
    configure
    local web_port
    web_port="$(env_value WEB_PORT 8080)"

    ui_step "Host"
    setup_port53
    host_firewall dns "$web_port/tcp"
    host_compose
    host_autostart
    host_tailscale

    ui_step "Container"
    local log
    ui_info "construindo a imagem..."
    if ! log="$(podman compose build 2>&1)"; then
        printf '%s\n' "$log" | ui_prefix >&2
        ui_fail "falha ao construir a imagem"
    fi
    [[ -z $NEW_PASSWORD ]] || save_password_hash

    ui_info "subindo o container..."
    remove_container
    if ! log="$(podman compose up -d 2>&1)"; then
        printf '%s\n' "$log" | ui_prefix >&2
        ui_fail "falha ao subir o container"
    fi
    if ! timeout 60 bash -c "until curl -sf http://127.0.0.1:$web_port/login.html >/dev/null; do sleep 1; done"; then
        podman compose logs --tail 20 2>&1 | ui_prefix >&2
        ui_fail "o AdGuard não respondeu em 60s"
    fi
    ui_ok "container $CONTAINER rodando"

    local lan_ip ts_ip
    lan_ip="$(env_value DNS_BIND_IP 0.0.0.0)"
    [[ $lan_ip == 0.0.0.0 ]] && lan_ip="$(host_lan_ip)"
    ts_ip="$(host_tailscale_ip)"
    ui_step "Acesso"
    ui_ok "DNS:    $lan_ip${ts_ip:+  |  Tailscale: $ts_ip}"
    ui_ok "Painel: http://$lan_ip:$web_port${ts_ip:+  |  http://$ts_ip:$web_port}"
}

cmd_remove() {
    local purge=false
    [[ ${1:-} == --purge ]] && purge=true

    ui_step "Remoção"
    if cmd_status; then
        remove_container
        ui_ok "container $CONTAINER removido"
    else
        ui_info "nenhum container para remover"
    fi

    if $purge; then
        if [[ -d data ]]; then
            podman unshare rm -rf data
            ui_ok "dados apagados (adguard/data)"
        else
            ui_info "nenhum dado para apagar"
        fi
    else
        ui_info "dados mantidos em adguard/data"
    fi
}

case "${1:-}" in
    describe) cmd_describe ;;
    status)   cmd_status ;;
    install)  cmd_install ;;
    remove)   shift; cmd_remove "$@" ;;
    *)        ui_fail "uso: $0 describe | status | install | remove [--purge]" ;;
esac
