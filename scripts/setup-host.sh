#!/usr/bin/env bash
set -euo pipefail

step() { printf '\n\033[1;34m==>\033[0m \033[1m%s\033[0m\n' "$*"; }
ok()   { printf '    \033[32m✔\033[0m %s\n' "$*"; }
warn() { printf '    \033[33m!\033[0m %s\n' "$*"; }

step "Porta 53 para Podman rootless"
echo "net.ipv4.ip_unprivileged_port_start=53" | sudo tee /etc/sysctl.d/99-astro-adguard.conf >/dev/null
sudo sysctl -q -p /etc/sysctl.d/99-astro-adguard.conf
ok "portas a partir da 53 liberadas para usuários comuns"

step "systemd-resolved"
if systemctl is-active --quiet systemd-resolved; then
    sudo mkdir -p /etc/systemd/resolved.conf.d
    printf '[Resolve]\nDNSStubListener=no\n' | sudo tee /etc/systemd/resolved.conf.d/99-astro-adguard.conf >/dev/null
    sudo ln -sf /run/systemd/resolve/resolv.conf /etc/resolv.conf
    sudo systemctl restart systemd-resolved
    ok "DNS stub desativado, porta 53 livre"
else
    ok "não está ativo, nada a fazer"
fi

step "Firewall"
if command -v firewall-cmd >/dev/null && sudo firewall-cmd --state >/dev/null 2>&1; then
    sudo firewall-cmd -q --permanent --add-service=dns
    sudo firewall-cmd -q --permanent --add-port="${WEB_PORT:-8080}/tcp"
    sudo firewall-cmd -q --reload
    ok "DNS (53) e painel (${WEB_PORT:-8080}/tcp) liberados no firewalld"
else
    ok "firewalld não está ativo, nada a fazer"
fi

step "podman-compose"
if podman compose version >/dev/null 2>&1; then
    ok "já instalado"
elif command -v dnf >/dev/null; then
    sudo dnf install -y -q podman-compose
    ok "instalado via dnf"
elif command -v apt-get >/dev/null; then
    sudo apt-get install -y -qq podman-compose
    ok "instalado via apt"
else
    warn "instale manualmente: pip install --user podman-compose"
fi

step "Inicialização automática dos containers"
systemctl --user enable --now podman-restart.service >/dev/null 2>&1
loginctl enable-linger "$USER"
ok "containers sobem sozinhos após o boot"

step "Tailscale"
if command -v tailscale >/dev/null; then
    sudo systemctl enable --now tailscaled
    if tailscale status >/dev/null 2>&1; then
        sudo tailscale set --accept-routes --operator="$USER"
    else
        sudo tailscale up --accept-routes --operator="$USER"
    fi
    ok "conectado com --accept-routes ($(tailscale ip -4))"
else
    warn "não instalado, etapa ignorada"
fi

step "Host pronto"
ok "próximos passos: cp .env.example .env && podman compose up -d --build"
