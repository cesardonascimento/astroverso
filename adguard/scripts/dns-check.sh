#!/usr/bin/env bash
set -uo pipefail

DNS_IP=${1:?uso: astro-dns-check IP_DO_ADGUARD}
RENEW_ATTEMPTS=3
WAIT_SECONDS=300

device="$(ip -4 route show default | grep -oP 'dev \K\S+' | head -1)"
[[ -n $device && $device != tailscale* ]] || exit 0
connection="$(nmcli -g GENERAL.CONNECTION device show "$device" 2>/dev/null)"
[[ -n $connection ]] || exit 0

primary_dns() { nmcli -g IP4.DNS device show "$device" | cut -d'|' -f1 | tr -d ' '; }

attempt=0
while [[ $(primary_dns) != "$DNS_IP" ]]; do
    if ((attempt++ >= RENEW_ATTEMPTS)); then
        echo "o roteador continua entregando $(primary_dns) como DNS primário em $device, confira o DHCP do roteador"
        exit 1
    fi
    echo "o roteador entregou $(primary_dns) como DNS primário em $device, pedindo de novo ($attempt/$RENEW_ATTEMPTS)"
    nmcli connection up "$connection" >/dev/null
    sleep 5
done

waited=0
until timeout 2 bash -c "</dev/tcp/$DNS_IP/53" 2>/dev/null; do
    if ((waited >= WAIT_SECONDS)); then
        echo "o AdGuard ($DNS_IP) não respondeu em ${WAIT_SECONDS}s"
        exit 1
    fi
    sleep 5
    waited=$((waited + 5))
done

current="$(resolvectl status "$device" | awk -F': ' '/Current DNS Server/ { print $2 }')"
if [[ -n $current && $current != "$DNS_IP" ]]; then
    echo "DNS em uso era $current, voltando para o AdGuard ($DNS_IP)"
    systemctl restart systemd-resolved
fi
echo "DNS primário em $device: AdGuard ($DNS_IP)"
