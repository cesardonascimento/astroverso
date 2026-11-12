#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"

ASTRO_PROJECT=adguard
source ../lib/ui.sh
source ../lib/host.sh
source ../lib/env.sh
source ../lib/proxy.sh

CONTAINER=astro-adguard
IMAGE=localhost/astro-adguard:latest
CONF_FILE="$STATE/data/conf/AdGuardHome.yaml"
DNS_CHECK_BIN=/usr/local/bin/astro-dns-check
DNS_CHECK_UNIT=/etc/systemd/system/astro-dns-check.service
DNS_CHECK_HOOK=/etc/NetworkManager/dispatcher.d/90-astro-dns-check

cmd_describe() {
    echo "AdGuard Home: DNS da rede com bloqueio de anúncios"
}

cmd_status() {
    podman container exists "$CONTAINER"
}

remove_container() {
    compose down >/dev/null 2>&1 || true
    podman rm -f "$CONTAINER" >/dev/null 2>&1 || true
}

NEW_PASSWORD=""

normalize_domain() {
    is_hostname "${1#\*.}"
}

panel_host_default() {
    local domain
    domain="$(proxy_domain)"
    [[ -n $domain ]] || domain="${1:-$(env_get ADGUARD_REWRITES | cut -d, -f1)}"
    [[ -z $domain ]] || printf 'adguard.%s' "$domain"
}

configure() {
    ui_step "Configuração"
    if config_reuse; then
        ui_ok "configuração existente mantida"
        return
    fi

    local username language timezone web_port dns_ip
    ui_input  username "usuário do painel" "$(env_get ADGUARD_USERNAME admin)" is_name
    ui_secret NEW_PASSWORD "senha do painel"
    ui_input  web_port "porta do painel no host" "$(env_get WEB_PORT 8080)" is_port
    ui_input  dns_ip   "IP do host onde o DNS escuta (0.0.0.0 = todos)" "$(env_get DNS_BIND_IP 0.0.0.0)" is_ipv4
    ui_input  timezone "fuso horário" "$(timedatectl show -P Timezone 2>/dev/null || echo UTC)" is_timezone
    ui_input  language "idioma do painel" "$(env_get ADGUARD_LANGUAGE pt-br)" is_name

    ui_step "Reescritas DNS"
    local rewrite_answer="" domains=() extra=() domain caddy_domain default_answer=$dns_ip
    if [[ $default_answer == 0.0.0.0 ]]; then
        default_answer="$(host_lan_ip)"
    fi
    caddy_domain="$(proxy_domain)"
    if [[ -n $caddy_domain ]]; then
        if ui_confirm "responder *.$caddy_domain com o IP desta máquina ($default_answer)?" y; then
            domains+=("$caddy_domain")
        fi
        if ui_confirm "adicionar outros domínios?" n; then
            ui_list extra "domínio, sem o *. (ex.: casa.com)" normalize_domain
        fi
    elif ui_confirm "adicionar domínios de reescrita (*.<domínio> → IP)?" n; then
        ui_list extra "domínio, sem o *. (ex.: casa.com)" normalize_domain
    fi
    for domain in "${extra[@]}"; do
        [[ " ${domains[*]} " == *" $domain "* ]] || domains+=("$domain")
    done
    if ((${#domains[@]})); then
        ui_input rewrite_answer "IP de destino das reescritas" "$(env_get ADGUARD_REWRITE_ANSWER "$default_answer")" is_ipv4
        for domain in "${domains[@]}"; do
            ui_ok "*.$domain → $rewrite_answer"
        done
    else
        ui_info "sem reescritas"
    fi

    ui_step "Caddy"
    local panel_host="" default_host
    default_host="$(env_get PANEL_HOST "$(panel_host_default "${domains[0]:-}")")"
    if [[ -n $default_host ]]; then
        ui_input panel_host "endereço do painel no Caddy" "$default_host" is_hostname
    else
        ui_info "nenhum domínio conhecido, o painel não será publicado no Caddy"
    fi

    (
        umask 077
        cat > "$ENV_FILE" <<EOF
ADGUARD_USERNAME='$username'
PANEL_HOST='$panel_host'
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
        ui_info "config anterior do AdGuard salva em $CONF_FILE.bak"
    fi
}

save_password_hash() {
    local hash
    hash="$(printf '%s' "$NEW_PASSWORD" \
        | podman run --rm -i --entrypoint htpasswd "$IMAGE" -niBC 10 "" | tr -d ':\n')"
    printf "ADGUARD_PASSWORD_HASH='%s'\n" "$hash" >> "$ENV_FILE"
    ui_ok "configuração salva em $ENV_FILE (senha guardada como hash bcrypt)"
}

setup_port53() {
    host_unprivileged_ports 53

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

setup_host_dns() {
    local dns_ip=$1 device connection
    device="$(ip -4 route get 1.1.1.1 | grep -oP 'dev \K\S+')"
    connection="$(nmcli -g GENERAL.CONNECTION device show "$device" 2>/dev/null)" || true
    if [[ -z $connection ]]; then
        ui_warn "conexão de rede não gerenciada pelo NetworkManager, configure o DNS desta máquina para $dns_ip"
        return
    fi
    if [[ $(nmcli -g ipv4.ignore-auto-dns connection show "$connection") == yes \
        && $(nmcli -g ipv4.dns connection show "$connection") == "$dns_ip" ]]; then
        ui_ok "esta máquina já usa só o AdGuard como DNS ($connection)"
        remove_dns_check
        return
    fi
    ui_info "só o AdGuard: a máquina sempre resolve os nomes internos, mas fica sem DNS quando ele está parado"
    ui_info "com o secundário: nunca fica sem DNS, mas pode deixar de resolver os nomes internos após um reinício"
    if ! ui_confirm "usar só o AdGuard como DNS desta máquina?" n; then
        ui_info "DNS desta máquina mantido"
        install_dns_check "$dns_ip"
        return
    fi
    nmcli connection modify "$connection" ipv4.ignore-auto-dns yes ipv4.dns "$dns_ip" ipv6.ignore-auto-dns yes
    nmcli connection up "$connection" >/dev/null
    ui_ok "esta máquina agora usa só o AdGuard como DNS ($connection)"
    remove_dns_check
}

dns_check_unit() {
    printf '%s\n' \
        '[Unit]' \
        'Description=astro: AdGuard como DNS primário' \
        'After=network-online.target' \
        '' \
        '[Service]' \
        'Type=oneshot' \
        'SyslogIdentifier=adguard' \
        "ExecStart=$DNS_CHECK_BIN $1"
}

dns_check_hook() {
    printf '%s\n' \
        '#!/bin/sh' \
        'case "$2" in up|dhcp4-change) systemctl start --no-block astro-dns-check.service ;; esac'
}

install_dns_check() {
    local dns_ip=$1
    if cmp -s scripts/dns-check.sh "$DNS_CHECK_BIN" \
        && [[ $(cat "$DNS_CHECK_UNIT" 2>/dev/null) == "$(dns_check_unit "$dns_ip")" && -x $DNS_CHECK_HOOK ]]; then
        ui_ok "verificação do DNS primário já ativa"
        return
    fi
    sudo install -m 0755 scripts/dns-check.sh "$DNS_CHECK_BIN"
    dns_check_unit "$dns_ip" | sudo tee "$DNS_CHECK_UNIT" >/dev/null
    dns_check_hook | sudo tee "$DNS_CHECK_HOOK" >/dev/null
    sudo chmod 0755 "$DNS_CHECK_HOOK"
    ! command -v restorecon >/dev/null || sudo restorecon -q "$DNS_CHECK_BIN" "$DNS_CHECK_UNIT" "$DNS_CHECK_HOOK"
    sudo systemctl daemon-reload
    sudo systemctl start --no-block astro-dns-check.service
    ui_ok "a cada conexão de rede, o AdGuard volta a ser o DNS primário (log: journalctl -t adguard)"
}

remove_dns_check() {
    [[ -e $DNS_CHECK_UNIT || -e $DNS_CHECK_HOOK || -e $DNS_CHECK_BIN ]] || return 0
    sudo rm -f "$DNS_CHECK_HOOK" "$DNS_CHECK_UNIT" "$DNS_CHECK_BIN"
    sudo systemctl daemon-reload
    ui_ok "verificação do DNS primário removida"
}

split_dns_mismatches() {
    local expected=$1 domain server
    for domain in $(env_get ADGUARD_REWRITES | tr ',' ' '); do
        server="$(tailscale dns status 2>/dev/null \
            | awk -v d="$domain" '$1 == "-" && $2 == d && $3 == "->" { print $4; exit }')"
        [[ -n $server && $server != "$expected" ]] && printf '%s %s\n' "$domain" "$server"
    done
    return 0
}

check_tailscale_split_dns() {
    local lan_ip=$1 domain server mismatches
    if [[ -z $(host_tailscale_ip) || -z $(env_get ADGUARD_REWRITES) ]]; then
        ui_ok "nada a verificar no Split DNS do Tailscale"
        return
    fi
    while true; do
        mismatches="$(split_dns_mismatches "$lan_ip")"
        if [[ -z $mismatches ]]; then
            ui_ok "Split DNS do Tailscale não desvia os domínios das reescritas"
            return
        fi
        while read -r domain server; do
            ui_warn "o Tailscale envia *.$domain para $server, não para este AdGuard"
        done <<< "$mismatches"
        ui_info "em https://login.tailscale.com/admin/dns → Nameservers, troque o servidor do Split DNS"
        ui_info "desses domínios para $lan_ip (IP local desta máquina)"
        ui_confirm "já ajustou? verificar de novo?" y || { ui_warn "Split DNS pendente, esses nomes não vão resolver"; return; }
    done
}

split_dns_route() {
    tailscale dns status 2>/dev/null | awk -v d="$1" '$1 == "-" && $2 == d && $3 == "->" { print $4; exit }'
}

require_split_dns() {
    local domain=$1 lan_ip=$2 server
    [[ -n $(host_tailscale_ip) ]] || return 0
    while true; do
        server="$(split_dns_route "$domain")"
        if [[ $server == "$lan_ip" ]]; then
            ui_ok "Split DNS do Tailscale: $domain → $lan_ip"
            return 0
        fi
        if [[ -z $server ]]; then
            ui_warn "o Split DNS do Tailscale não tem $domain: de fora de casa, os endereços novos não abrem"
        else
            ui_warn "o Tailscale envia $domain para $server, não para este AdGuard"
        fi
        ui_info "em https://login.tailscale.com/admin/dns → Nameservers → Add nameserver → Custom:"
        ui_info "  servidor $lan_ip, com \"Restrict to domain\" (Split DNS) ligado e o domínio $domain"
        ui_info "  e apague a entrada do domínio antigo, se ainda existir"
        ui_confirm "já ajustou? verificar de novo?" y || { ui_warn "Split DNS pendente: de fora de casa, $domain não resolve"; return 0; }
    done
}

cmd_domain() {
    local old=$1 new=$2 lan_ip web_port panel_host log
    web_port="$(env_get WEB_PORT 8080)"
    lan_ip="$(env_get DNS_BIND_IP 0.0.0.0)"
    [[ $lan_ip == 0.0.0.0 ]] && lan_ip="$(host_lan_ip)"

    ui_step "Reescritas DNS"
    if podman unshare test -f "$CONF_FILE"; then
        remove_container
        podman unshare python3 -I -c '
import re, sys
path, old, new = sys.argv[1:]
text = open(path, encoding="utf-8").read()
pattern = re.compile(r"^(\s*-?\s*domain:\s*)([\x27\x22]?)\*\." + re.escape(old) + r"\2\s*$", re.M)
text, count = pattern.subn(lambda m: f"{m.group(1)}{m.group(2)}*.{new}{m.group(2)}", text)
open(path, "w", encoding="utf-8").write(text)
print(count)
' "$CONF_FILE" "$old" "$new" > /dev/null
        if ! log="$(compose up -d 2>&1)"; then
            printf '%s\n' "$log" | ui_prefix >&2
            ui_fail "falha ao subir o container"
        fi
        if ! timeout 60 bash -c "until curl -sf http://127.0.0.1:$web_port/login.html >/dev/null; do sleep 1; done"; then
            compose logs --tail 20 2>&1 | ui_prefix >&2
            ui_fail "o AdGuard não respondeu em 60s"
        fi
    fi
    ui_ok "*.$new → $(env_get ADGUARD_REWRITE_ANSWER "$lan_ip") (no lugar de *.$old)"

    ui_step "DNS"
    require_split_dns "$new" "$lan_ip"

    panel_host="$(env_get PANEL_HOST)"
    if [[ -n $panel_host ]]; then
        ui_step "Caddy"
        proxy_publish "$panel_host" "http://host.containers.internal:$web_port"
    fi
}

cmd_install() {
    state_setup
    configure
    local web_port
    web_port="$(env_get WEB_PORT 8080)"

    ui_step "Host"
    setup_port53
    if [[ -n $(env_get PANEL_HOST) ]]; then
        host_firewall dns
        host_firewall_block_lan "$web_port"
    else
        host_firewall dns "$web_port/tcp"
        host_firewall_unblock_lan "$web_port"
    fi

    ui_step "Container"
    local log
    ui_info "construindo a imagem..."
    if ! log="$(compose build 2>&1)"; then
        printf '%s\n' "$log" | ui_prefix >&2
        ui_fail "falha ao construir a imagem"
    fi
    [[ -z $NEW_PASSWORD ]] || save_password_hash

    ui_info "subindo o container..."
    remove_container
    if ! log="$(compose up -d 2>&1)"; then
        printf '%s\n' "$log" | ui_prefix >&2
        ui_fail "falha ao subir o container"
    fi
    if ! timeout 60 bash -c "until curl -sf http://127.0.0.1:$web_port/login.html >/dev/null; do sleep 1; done"; then
        compose logs --tail 20 2>&1 | ui_prefix >&2
        ui_fail "o AdGuard não respondeu em 60s"
    fi
    ui_ok "container $CONTAINER rodando"

    local lan_ip
    lan_ip="$(env_get DNS_BIND_IP 0.0.0.0)"
    [[ $lan_ip == 0.0.0.0 ]] && lan_ip="$(host_lan_ip)"

    ui_step "DNS"
    setup_host_dns "$lan_ip"
    check_tailscale_split_dns "$lan_ip"

    local panel_host
    panel_host="$(env_get PANEL_HOST)"
    if [[ -n $panel_host ]]; then
        ui_step "Caddy"
        proxy_publish "$panel_host" "http://host.containers.internal:$web_port"
    fi

    ui_step "Acesso"
    ui_ok "DNS:    $lan_ip"
    if [[ -n $panel_host ]]; then
        ui_ok "Painel: https://$panel_host"
    else
        ui_ok "Painel: http://$lan_ip:$web_port"
    fi
}

restore_host_dns() {
    local dns_ip=$1 device connection
    device="$(ip -4 route get 1.1.1.1 2>/dev/null | grep -oP 'dev \K\S+')" || true
    [[ -n $device ]] || return 0
    connection="$(nmcli -g GENERAL.CONNECTION device show "$device" 2>/dev/null)" || true
    [[ -n $connection ]] || return 0
    if [[ $(nmcli -g ipv4.ignore-auto-dns connection show "$connection") == yes \
        && $(nmcli -g ipv4.dns connection show "$connection") == "$dns_ip" ]]; then
        nmcli connection modify "$connection" ipv4.ignore-auto-dns no ipv4.dns "" ipv6.ignore-auto-dns no
        nmcli connection up "$connection" >/dev/null
        ui_ok "esta máquina volta a usar o DNS entregue pelo roteador ($connection)"
    fi
}

restore_port53() {
    local conf=/etc/systemd/resolved.conf.d/99-astro-adguard.conf
    [[ -f $conf ]] || return 0
    sudo rm -f "$conf"
    sudo ln -sf ../run/systemd/resolve/stub-resolv.conf /etc/resolv.conf
    sudo systemctl restart systemd-resolved
    ui_ok "DNS stub do systemd-resolved reativado"
}

cmd_remove() {
    local web_port dns_ip
    web_port="$(env_get WEB_PORT 8080)"
    dns_ip="$(env_get DNS_BIND_IP 0.0.0.0)"
    if [[ $dns_ip == 0.0.0.0 ]]; then
        dns_ip="$(host_lan_ip)" || true
    fi

    ui_step "Remoção"
    restore_host_dns "$dns_ip"
    remove_container
    images_remove
    ui_ok "container $CONTAINER removido"
    remove_dns_check
    restore_port53
    host_firewall_remove dns "$web_port/tcp"
    host_firewall_unblock_lan "$web_port"
    proxy_unpublish
    state_purge
}

cmd_restore() {
    local log
    remove_container
    state_restore "$1"
    if ! log="$(compose up -d 2>&1)"; then
        printf '%s\n' "$log" | ui_prefix >&2
        ui_fail "falha ao subir o container depois de restaurar"
    fi
    ui_ok "container $CONTAINER rodando com a configuração restaurada"
}

case "${1:-}" in
    describe) cmd_describe ;;
    status)   cmd_status ;;
    actions)  ;;
    install)  cmd_install ;;
    domain)   shift; cmd_domain "$1" "$2" ;;
    remove)   cmd_remove ;;
    backup)   printf 'exclude %s\n' "$STATE/data/work" ;;
    restore)  shift; cmd_restore "$1" ;;
    *)        ui_fail "uso: $0 describe | status | actions | install | domain <antigo> <novo> | remove | backup | restore <pasta>" ;;
esac
