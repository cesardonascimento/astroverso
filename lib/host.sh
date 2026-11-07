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

host_unprivileged_ports() {
    local port=$1 current
    current="$(sysctl -n net.ipv4.ip_unprivileged_port_start)"
    if ((current <= port)); then
        ui_ok "portas a partir da $current já liberadas para Podman rootless"
        return
    fi
    echo "net.ipv4.ip_unprivileged_port_start=$port" | sudo tee /etc/sysctl.d/99-astro.conf >/dev/null
    sudo sysctl -q -p /etc/sysctl.d/99-astro.conf
    ui_ok "portas a partir da $port liberadas para Podman rootless"
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

host_tailscale_install() {
    local ID VERSION_ID VERSION_CODENAME UBUNTU_CODENAME repo
    source /etc/os-release
    if command -v dnf >/dev/null; then
        if ! sudo dnf install -y -q tailscale 2>/dev/null; then
            [[ $ID == fedora ]] && repo=fedora || repo="rhel/${VERSION_ID%%.*}"
            curl -fsSL "https://pkgs.tailscale.com/stable/$repo/tailscale.repo" \
                | sudo tee /etc/yum.repos.d/tailscale.repo >/dev/null
            sudo dnf install -y -q tailscale
        fi
    elif command -v apt-get >/dev/null; then
        if [[ -n ${UBUNTU_CODENAME:-} ]]; then
            repo="ubuntu/$UBUNTU_CODENAME"
        else
            repo="debian/$VERSION_CODENAME"
        fi
        curl -fsSL "https://pkgs.tailscale.com/stable/$repo.noarmor.gpg" \
            | sudo tee /usr/share/keyrings/tailscale-archive-keyring.gpg >/dev/null
        curl -fsSL "https://pkgs.tailscale.com/stable/$repo.tailscale-keyring.list" \
            | sudo tee /etc/apt/sources.list.d/tailscale.list >/dev/null
        sudo apt-get update -qq
        sudo apt-get install -y -qq tailscale
    else
        ui_fail "instale o Tailscale manualmente: https://tailscale.com/download"
    fi
    command -v tailscale >/dev/null || ui_fail "falha ao instalar o Tailscale"
    ui_ok "Tailscale $(tailscale version | head -1) instalado"
}

host_tailscale() {
    if ! command -v tailscale >/dev/null; then
        host_tailscale_install
    fi
    systemctl is-active -q tailscaled || sudo systemctl enable -q --now tailscaled
    if ! tailscale status >/dev/null 2>&1; then
        sudo tailscale up --accept-routes --operator="$USER" 2>&1 | ui_prefix
    elif ! tailscale debug prefs | grep -q '"RouteAll": true'; then
        tailscale set --accept-routes 2>/dev/null || sudo tailscale set --accept-routes --operator="$USER"
    fi
    ui_ok "Tailscale conectado com --accept-routes ($(tailscale ip -4))"
    host_tailscale_subnet
}

host_lan_subnet() {
    local device
    device="$(ip -4 route get 1.1.1.1 | grep -oP 'dev \K\S+')"
    ip -4 route show dev "$device" scope link proto kernel | awk '{ print $1; exit }'
}

host_tailscale_subnet() {
    local subnet
    subnet="$(host_lan_subnet)"
    if [[ -z $subnet ]]; then
        ui_warn "rede local não detectada, anúncio da rede no Tailscale ignorado"
        return
    fi

    if ! tailscale debug prefs | grep -q "\"$subnet\""; then
        if ! ui_confirm "anunciar a rede local $subnet no Tailscale (acesso remoto a toda a rede)?" y; then
            ui_info "rede local não anunciada no Tailscale"
            return
        fi
        if [[ $(sysctl -n net.ipv4.ip_forward) != 1 ]]; then
            printf 'net.ipv4.ip_forward = 1\nnet.ipv6.conf.all.forwarding = 1\n' \
                | sudo tee /etc/sysctl.d/99-astro-tailscale.conf >/dev/null
            sudo sysctl -q -p /etc/sysctl.d/99-astro-tailscale.conf
            ui_ok "encaminhamento de pacotes ativado"
        fi
        if command -v firewall-cmd >/dev/null && firewall-cmd --state >/dev/null 2>&1 \
            && ! firewall-cmd -q --query-masquerade; then
            sudo firewall-cmd -q --permanent --add-masquerade
            sudo firewall-cmd -q --reload
            ui_ok "masquerade liberado no firewalld"
        fi
        tailscale set --advertise-routes="$subnet" 2>/dev/null \
            || sudo tailscale set --advertise-routes="$subnet"
    fi

    if tailscale status --json | sed -n '/^  "Self": {/,/^  }/p' | grep -q "\"$subnet\""; then
        ui_ok "rede $subnet anunciada e aprovada no Tailscale"
    else
        ui_warn "rede $subnet anunciada, falta aprovar no painel do Tailscale:"
        ui_info "https://login.tailscale.com/admin/machines → $(hostname -s) → Edit route settings → marque $subnet"
    fi
}

host_lan_ip() {
    ip -4 route get 1.1.1.1 | grep -oP 'src \K\S+'
}

host_tailscale_ip() {
    tailscale ip -4 2>/dev/null || true
}
