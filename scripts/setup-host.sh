#!/usr/bin/env bash
# Prepara um host Linux novo para rodar o astro-adguard com Podman rootless.
# Rode uma vez por máquina:  ./scripts/setup-host.sh
set -euo pipefail

echo "==> Permitindo que usuários comuns (Podman rootless) usem a porta 53"
echo "net.ipv4.ip_unprivileged_port_start=53" | sudo tee /etc/sysctl.d/99-astro-adguard.conf >/dev/null
sudo sysctl --system >/dev/null

if systemctl is-active --quiet systemd-resolved; then
    echo "==> Desativando o DNS stub do systemd-resolved (libera a porta 53)"
    sudo mkdir -p /etc/systemd/resolved.conf.d
    printf '[Resolve]\nDNSStubListener=no\n' | sudo tee /etc/systemd/resolved.conf.d/99-astro-adguard.conf >/dev/null
    # Mantém o host resolvendo nomes usando os servidores reais (não o stub)
    sudo ln -sf /run/systemd/resolve/resolv.conf /etc/resolv.conf
    sudo systemctl restart systemd-resolved
fi

if command -v firewall-cmd >/dev/null && sudo firewall-cmd --state >/dev/null 2>&1; then
    echo "==> Abrindo portas no firewalld (DNS + painel)"
    sudo firewall-cmd --permanent --add-service=dns >/dev/null
    sudo firewall-cmd --permanent --add-port="${WEB_PORT:-8080}/tcp" >/dev/null
    sudo firewall-cmd --reload >/dev/null
fi

if ! podman compose version >/dev/null 2>&1; then
    echo "==> Instalando podman-compose"
    if command -v dnf >/dev/null; then sudo dnf install -y podman-compose
    elif command -v apt-get >/dev/null; then sudo apt-get install -y podman-compose
    else echo "Instale o podman-compose manualmente (pip install --user podman-compose)"; fi
fi

echo "==> Habilitando o serviço que reinicia containers após o boot"
systemctl --user enable --now podman-restart.service >/dev/null 2>&1 || true
loginctl enable-linger "$USER" || true

if command -v tailscale >/dev/null; then
    echo "==> Configurando Tailscale (aceitar rotas de sub-rede por padrão)"
    sudo systemctl enable --now tailscaled
    if tailscale status >/dev/null 2>&1; then
        # Já logado: só ajusta as preferências
        sudo tailscale set --accept-routes --operator="$USER"
    else
        # Primeiro login: mostra o link para autenticar no navegador
        sudo tailscale up --accept-routes --operator="$USER"
    fi
fi

echo "Pronto! Agora: cp .env.example .env && podman compose up -d --build"
