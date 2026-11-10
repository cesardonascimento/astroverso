export PODMAN_COMPOSE_WARNING_LOGS=false

HOST_PORTS_CONF=/etc/sysctl.d/99-astro.conf
HOST_FORWARD_CONF=/etc/sysctl.d/99-astro-tailscale.conf
HOST_SSH_CONF=/etc/ssh/sshd_config.d/10-astro.conf

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
    echo "net.ipv4.ip_unprivileged_port_start=$port" | sudo tee "$HOST_PORTS_CONF" >/dev/null
    sudo sysctl -q -p "$HOST_PORTS_CONF"
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
    if ! command -v firewall-cmd >/dev/null || ! systemctl is-active -q firewalld; then
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

host_firewall_remove() {
    command -v firewall-cmd >/dev/null && systemctl is-active -q firewalld || return 0
    local rule changed=false
    for rule in "$@"; do
        if [[ $rule == */* ]]; then
            if firewall-cmd -q --query-port="$rule"; then
                sudo firewall-cmd -q --permanent --remove-port="$rule"
                changed=true
            fi
        elif firewall-cmd -q --query-service="$rule"; then
            sudo firewall-cmd -q --permanent --remove-service="$rule"
            changed=true
        fi
    done
    if $changed; then
        sudo firewall-cmd -q --reload
        ui_ok "firewall fechado de novo: $*"
    fi
    return 0
}

host_firewall_block_lan() {
    local port=$1 zone rule
    rule="rule port port=\"$port\" protocol=\"tcp\" reject"
    if ! command -v firewall-cmd >/dev/null || ! systemctl is-active -q firewalld; then
        ui_warn "firewalld inativo, a porta $port continua acessível pela rede"
        return
    fi
    zone="$(firewall-cmd --get-default-zone)"
    if ! firewall-cmd -q --zone="$zone" --query-rich-rule="$rule"; then
        sudo firewall-cmd -q --permanent --zone="$zone" --add-rich-rule="$rule"
        sudo firewall-cmd -q --reload
    fi
    ui_ok "porta $port bloqueada para a rede (acesso só pelo Caddy, com HTTPS)"
}

host_firewall_unblock_lan() {
    local port=$1 zone rule
    rule="rule port port=\"$port\" protocol=\"tcp\" reject"
    command -v firewall-cmd >/dev/null && systemctl is-active -q firewalld || return 0
    zone="$(firewall-cmd --get-default-zone)"
    firewall-cmd -q --zone="$zone" --query-rich-rule="$rule" || return 0
    sudo firewall-cmd -q --permanent --zone="$zone" --remove-rich-rule="$rule"
    sudo firewall-cmd -q --reload
    ui_ok "porta $port liberada de novo para a rede"
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
    host_tailscale_port_forward
}

host_ssh_auth_methods() {
    ssh -o BatchMode=yes -o PreferredAuthentications=none -o ConnectTimeout=5 \
        -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null 127.0.0.1 2>&1 \
        | grep -oP 'Permission denied \(\K[^)]*' || true
}

host_ssh() {
    local service=sshd methods
    if [[ ! -x /usr/sbin/sshd ]]; then
        if command -v dnf >/dev/null; then
            sudo dnf install -y -q openssh-server
        elif command -v apt-get >/dev/null; then
            sudo apt-get install -y -qq openssh-server
        else
            ui_warn "instale o openssh-server manualmente, etapa ignorada"
            return
        fi
        ui_ok "servidor SSH instalado"
    fi
    systemctl list-unit-files ssh.service 2>/dev/null | grep -q '^ssh\.service' && service=ssh

    if systemctl is-enabled -q "$service" 2>/dev/null && systemctl is-active -q "$service"; then
        ui_ok "SSH já ativo"
    else
        sudo systemctl enable -q --now "$service"
        ui_ok "SSH ativado e configurado para iniciar no boot"
    fi
    host_firewall ssh

    methods="$(host_ssh_auth_methods)"
    if [[ $methods != *password* ]]; then
        ui_ok "SSH aceita só login por chave"
    elif [[ ! -s $HOME/.ssh/authorized_keys ]]; then
        ui_warn "SSH aceita login por senha; para usar só chaves, adicione sua chave pública"
        ui_info "em ~/.ssh/authorized_keys (ssh-copy-id $USER@$(host_lan_ip)) e rode a instalação de novo"
    elif ui_confirm "desativar o login por senha no SSH (só chaves, mais seguro)?" y; then
        printf 'PasswordAuthentication no\nKbdInteractiveAuthentication no\n' \
            | sudo tee "$HOST_SSH_CONF" >/dev/null
        sudo systemctl reload "$service"
        ui_ok "SSH agora aceita só login por chave"
    fi
    ui_info "acesso: ssh $USER@$(host_lan_ip)"
}

HOST_SLEEP_TARGETS=(sleep.target suspend.target hibernate.target hybrid-sleep.target suspend-then-hibernate.target)
HOST_LOGIND_CONF=/etc/systemd/logind.conf.d/99-astro.conf

host_no_sleep() {
    local target masked=true
    for target in "${HOST_SLEEP_TARGETS[@]}"; do
        [[ $(systemctl is-enabled "$target" 2>/dev/null) == masked ]] || masked=false
    done
    $masked || sudo systemctl mask -q "${HOST_SLEEP_TARGETS[@]}"

    if [[ ! -f $HOST_LOGIND_CONF ]]; then
        sudo mkdir -p "$(dirname "$HOST_LOGIND_CONF")"
        printf '[Login]\nHandleLidSwitch=ignore\nHandleLidSwitchExternalPower=ignore\nHandleLidSwitchDocked=ignore\nIdleAction=ignore\n' \
            | sudo tee "$HOST_LOGIND_CONF" >/dev/null
        sudo systemctl reload systemd-logind 2>/dev/null || sudo systemctl kill -s HUP systemd-logind
    fi

    if command -v gsettings >/dev/null \
        && gsettings list-schemas 2>/dev/null | grep -qx org.gnome.settings-daemon.plugins.power; then
        gsettings set org.gnome.settings-daemon.plugins.power sleep-inactive-ac-type nothing 2>/dev/null || true
        gsettings set org.gnome.settings-daemon.plugins.power sleep-inactive-battery-type nothing 2>/dev/null || true
    fi
    ui_ok "suspensão e hibernação desativadas, inclusive ao fechar a tampa"
}

host_upgrade() {
    local latest=""
    ui_info "atualizando o sistema (pode demorar na primeira vez)..."
    if command -v dnf >/dev/null; then
        sudo dnf upgrade -y -q --refresh
        latest="$(rpm -q --qf '%{VERSION}-%{RELEASE}.%{ARCH}\n' kernel-core 2>/dev/null | sort -V | tail -1)" || true
    elif command -v apt-get >/dev/null; then
        sudo apt-get update -qq
        sudo apt-get upgrade -y -qq
    else
        ui_warn "gerenciador de pacotes não reconhecido, atualização ignorada"
        return
    fi
    ui_ok "sistema atualizado"
    if [[ -n $latest && $latest != "$(uname -r)" ]] || [[ -e /var/run/reboot-required ]]; then
        HOST_REBOOT=true
        ui_warn "kernel novo instalado: reinicie a máquina ao final para usá-lo"
    fi
}

host_undo() {
    local target masked=()
    for target in "${HOST_SLEEP_TARGETS[@]}"; do
        [[ $(systemctl is-enabled "$target" 2>/dev/null) == masked ]] && masked+=("$target")
    done
    ((${#masked[@]} == 0)) || sudo systemctl unmask -q "${masked[@]}"
    if [[ -f $HOST_LOGIND_CONF ]]; then
        sudo rm -f "$HOST_LOGIND_CONF"
        sudo systemctl reload systemd-logind 2>/dev/null || sudo systemctl kill -s HUP systemd-logind
    fi
    if command -v gsettings >/dev/null \
        && gsettings list-schemas 2>/dev/null | grep -qx org.gnome.settings-daemon.plugins.power; then
        gsettings reset org.gnome.settings-daemon.plugins.power sleep-inactive-ac-type 2>/dev/null || true
        gsettings reset org.gnome.settings-daemon.plugins.power sleep-inactive-battery-type 2>/dev/null || true
    fi
    ui_ok "suspensão e tampa de volta ao padrão do sistema"

    if [[ -f $HOST_PORTS_CONF ]]; then
        sudo rm -f "$HOST_PORTS_CONF"
        sudo sysctl -q -w net.ipv4.ip_unprivileged_port_start=1024
        ui_ok "portas abaixo de 1024 voltam a ser só do root"
    fi

    if command -v tailscale >/dev/null && tailscale status >/dev/null 2>&1; then
        tailscale set --advertise-routes= 2>/dev/null || sudo tailscale set --advertise-routes=
        ui_ok "rede local não é mais anunciada no Tailscale (a conexão continua)"
    fi
    if [[ -f $HOST_FORWARD_CONF ]]; then
        sudo rm -f "$HOST_FORWARD_CONF"
        sudo sysctl -q -w net.ipv4.ip_forward=0 net.ipv6.conf.all.forwarding=0
        ui_ok "encaminhamento de pacotes desativado"
    fi
    if command -v firewall-cmd >/dev/null && systemctl is-active -q firewalld && firewall-cmd -q --query-masquerade; then
        sudo firewall-cmd -q --permanent --remove-masquerade
        sudo firewall-cmd -q --reload
        ui_ok "masquerade removido do firewalld"
    fi

    if [[ -f $HOST_SSH_CONF ]]; then
        sudo rm -f "$HOST_SSH_CONF"
        sudo systemctl reload sshd 2>/dev/null || sudo systemctl reload ssh 2>/dev/null || true
        ui_ok "SSH aceita login por senha de novo (o serviço continua ativo)"
    fi

    systemctl --user disable -q --now podman-restart.service 2>/dev/null || true
    if [[ $(loginctl show-user "$USER" -P Linger 2>/dev/null) == yes ]]; then
        loginctl disable-linger "$USER"
    fi
    ui_ok "containers e serviços de $USER não sobem mais sozinhos no boot"
}

host_base() {
    host_no_sleep
    host_compose
    host_autostart
    host_ssh
    host_tailscale
}

host_lan_subnet() {
    local device
    device="$(ip -4 route get 1.1.1.1 | grep -oP 'dev \K\S+')"
    ip -4 route show dev "$device" scope link proto kernel | awk '{ print $1; exit }'
}

HOST_STATE="$HOME/.astro/host.env"

host_tailscale_port() {
    local port
    port="$(systemctl show tailscaled -p Environment --value 2>/dev/null | grep -oP '(^|\s)PORT=\K[0-9]+')" || true
    printf '%s' "${port:-41641}"
}

host_tailscale_port_forward() {
    local forward
    forward="$(host_lan_ip):$(host_tailscale_port)"
    if grep -qx "TAILSCALE_PORT_FORWARD=$forward" "$HOST_STATE" 2>/dev/null; then
        ui_ok "porta UDP ${forward#*:} redirecionada no roteador para ${forward%:*}"
        return
    fi
    ui_info "para o Tailscale conectar direto de fora de casa (sem relay), redirecione no roteador:"
    ui_info "  protocolo UDP, porta ${forward#*:} → ${forward%:*} (esta máquina), porta ${forward#*:}"
    ui_info "  no roteador, procure \"Redirecionamento de portas\", \"Port Forwarding\" ou \"Servidor virtual\""
    until ui_confirm "já fez esse redirecionamento no roteador?" n; do
        ui_warn "a instalação continua depois do redirecionamento (Ctrl+C para sair)"
    done
    mkdir -p "$(dirname "$HOST_STATE")"
    (
        umask 077
        grep -v '^TAILSCALE_PORT_FORWARD=' "$HOST_STATE" 2>/dev/null > "$HOST_STATE.new" || true
        echo "TAILSCALE_PORT_FORWARD=$forward" >> "$HOST_STATE.new"
    )
    mv "$HOST_STATE.new" "$HOST_STATE"
    chmod 600 "$HOST_STATE"
    ui_ok "redirecionamento da porta UDP ${forward#*:} confirmado"
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
                | sudo tee "$HOST_FORWARD_CONF" >/dev/null
            sudo sysctl -q -p "$HOST_FORWARD_CONF"
            ui_ok "encaminhamento de pacotes ativado"
        fi
        if command -v firewall-cmd >/dev/null && systemctl is-active -q firewalld \
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

HOST_REBOOT=false
HOST_AKMODS_KEY=/etc/pki/akmods/certs/public_key.der

host_nvidia_gpu() {
    command -v lspci >/dev/null && [[ -n "$(lspci -d 10de::0300; lspci -d 10de::0302)" ]]
}

host_secure_boot_key() {
    [[ $(mokutil --sb-state 2>/dev/null) == *enabled* ]] || return 0
    local state password hash
    if ! sudo test -f "$HOST_AKMODS_KEY"; then
        sudo kmodgenca -a >/dev/null
    fi
    state="$(sudo mokutil --test-key "$HOST_AKMODS_KEY" 2>&1)" || true
    if [[ $state == *"is already enrolled"* ]]; then
        ui_ok "chave que assina o driver já cadastrada no Secure Boot"
        return
    fi
    if [[ $state != *"enrollment request"* ]]; then
        ui_info "o Secure Boot só carrega módulos assinados: a chave que assina o driver precisa ser cadastrada"
        ui_info "crie uma senha temporária, usada uma única vez na tela azul do próximo boot"
        ui_secret password "senha temporária do Secure Boot"
        hash="$(mktemp)"
        printf '%s\n%s\n' "$password" "$password" | mokutil --generate-hash 2>/dev/null | tail -1 > "$hash"
        sudo mokutil --import "$HOST_AKMODS_KEY" --hash-file "$hash"
        rm -f "$hash"
    fi
    HOST_REBOOT=true
    ui_warn "no próximo boot, com teclado e tela na máquina, aparece a tela azul do MOK:"
    ui_info "  Enroll MOK → Continue → Yes → senha temporária → Reboot"
    ui_info "  se ela passar sem resposta (10 segundos), rode a instalação de novo e reinicie"
}

host_nvidia_version() {
    local kernel
    for kernel in "$(uname -r)" $(ls -v /lib/modules | tac); do
        if modinfo -k "$kernel" -F version nvidia 2>/dev/null; then
            return 0
        fi
    done
    return 1
}

host_rpmfusion() {
    local release
    rpm -q rpmfusion-free-release rpmfusion-nonfree-release >/dev/null 2>&1 && return 0
    release="$(rpm -E %fedora)"
    sudo dnf install -y -q \
        "https://mirrors.rpmfusion.org/free/fedora/rpmfusion-free-release-$release.noarch.rpm" \
        "https://mirrors.rpmfusion.org/nonfree/fedora/rpmfusion-nonfree-release-$release.noarch.rpm"
    ui_ok "repositórios do RPM Fusion habilitados"
}

host_intel_media() {
    command -v lspci >/dev/null && [[ -n "$(lspci -d 8086::0300; lspci -d 8086::0380)" ]] || return 0
    [[ $(. /etc/os-release && printf '%s' "$ID") == fedora ]] || return 0
    if rpm -q intel-media-driver >/dev/null 2>&1; then
        ui_ok "driver de vídeo completo da Intel já instalado (H.264/HEVC)"
        return
    fi
    host_rpmfusion
    if rpm -q libva-intel-media-driver >/dev/null 2>&1; then
        sudo dnf swap -y -q libva-intel-media-driver intel-media-driver --allowerasing
    else
        sudo dnf install -y -q intel-media-driver
    fi
    ui_ok "driver de vídeo completo da Intel instalado: codificação H.264/HEVC pela placa integrada"
}

host_nvidia_fedora() {
    local kernel
    host_rpmfusion
    sudo dnf install -y -q akmods mokutil
    host_secure_boot_key
    sudo dnf install -y -q akmod-nvidia xorg-x11-drv-nvidia-cuda
    kernel="$(rpm -q --qf '%{VERSION}-%{RELEASE}.%{ARCH}\n' kernel-core | sort -V | tail -1)"
    sudo dnf install -y -q "kernel-devel-$kernel"
    ui_info "compilando o módulo da NVIDIA para o kernel $kernel (alguns minutos)..."
    sudo akmods --kernels "$kernel" 2>&1 | ui_prefix
    if [[ $kernel != "$(uname -r)" ]]; then
        ui_ok "kernel $kernel instalado, passa a ser usado depois de reiniciar"
    fi
}

host_nvidia_driver() {
    local id version
    if ! host_nvidia_gpu; then
        ui_ok "nenhuma placa NVIDIA, driver proprietário dispensado"
        return
    fi
    if grep -q '^nvidia ' /proc/modules; then
        ui_ok "driver proprietário da NVIDIA ativo ($(modinfo -F version nvidia))"
        return
    fi
    id="$(. /etc/os-release && printf '%s' "$ID")"
    if version="$(host_nvidia_version)"; then
        if [[ $id == fedora ]]; then
            host_secure_boot_key
        fi
        HOST_REBOOT=true
        ui_warn "driver proprietário da NVIDIA $version instalado, carrega depois de reiniciar"
        return
    fi
    ui_info "placa NVIDIA usando o driver livre (nouveau): sem NVENC e com pouco desempenho 3D"
    if [[ $id == fedora ]]; then
        host_nvidia_fedora
    elif command -v ubuntu-drivers >/dev/null; then
        sudo ubuntu-drivers install 2>&1 | ui_prefix
    else
        ui_warn "instale o driver proprietário da NVIDIA manualmente; etapa ignorada"
        return
    fi
    version="$(host_nvidia_version)" || ui_fail "o módulo da NVIDIA não foi compilado"
    HOST_REBOOT=true
    ui_ok "driver proprietário da NVIDIA $version instalado, carrega depois de reiniciar"
}
