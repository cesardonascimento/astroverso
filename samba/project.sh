#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"

ASTRO_PROJECT=samba
source ../lib/ui.sh
source ../lib/host.sh
source ../lib/env.sh

SHARE=Public
SHARE_DIR="$HOME/Public"
CONF=/etc/samba/smb.conf
MARK_BEGIN="# astro samba: inicio"
MARK_END="# astro samba: fim"

cmd_describe() {
    echo "Samba: a pasta $SHARE de $USER como pasta de rede (\\\\<ip>\\$SHARE)"
}

smb_service() {
    if systemctl cat smbd.service >/dev/null 2>&1 && ! systemctl cat smb.service >/dev/null 2>&1; then
        printf smbd.service
    else
        printf smb.service
    fi
}

cmd_status() {
    [[ -f $ENV_FILE ]] && systemctl is-enabled -q "$(smb_service)" 2>/dev/null
}

install_packages() {
    if rpm -q samba >/dev/null 2>&1 || dpkg -s samba >/dev/null 2>&1; then
        ui_ok "Samba já instalado"
    elif command -v dnf >/dev/null; then
        sudo dnf install -y -q samba
        ui_ok "Samba instalado via dnf"
    elif command -v apt-get >/dev/null; then
        sudo apt-get install -y -qq samba
        ui_ok "Samba instalado via apt"
    else
        ui_fail "instale manualmente: samba"
    fi
}

share_block() {
    printf '%s\n' \
        "$MARK_BEGIN" \
        "[global]" \
        "    multicast dns register = no" \
        "[$SHARE]" \
        "    path = $SHARE_DIR" \
        "    valid users = $USER" \
        "    read only = no" \
        "    browseable = yes" \
        "    create mask = 0644" \
        "    directory mask = 0755" \
        "$MARK_END"
}

conf_without_share() {
    awk -v begin="$MARK_BEGIN" -v end="$MARK_END" '
        $0 == begin { skip = 1; next }
        $0 == end { skip = 0; next }
        !skip { print }
    ' "$CONF"
}

write_conf() {
    local wanted
    wanted="$(conf_without_share; share_block)"
    if [[ $wanted == "$(cat "$CONF")" ]]; then
        ui_ok "pasta $SHARE já compartilhada em $CONF"
        return
    fi
    [[ -e $CONF.astro-bak ]] || sudo cp -a "$CONF" "$CONF.astro-bak"
    printf '%s\n' "$wanted" | sudo tee "$CONF" >/dev/null
    if ! testparm -s "$CONF" >/dev/null 2>&1; then
        sudo cp -a "$CONF.astro-bak" "$CONF"
        ui_fail "configuração do Samba inválida (testparm): $CONF voltou ao que era"
    fi
    ui_ok "pasta $SHARE compartilhada só para $USER ($CONF)"
}

selinux_label() {
    command -v selinuxenabled >/dev/null && selinuxenabled || return 0
    if command -v semanage >/dev/null; then
        if ! sudo semanage fcontext -l -C 2>/dev/null | grep -qF "$SHARE_DIR(/.*)?"; then
            sudo semanage fcontext -a -t samba_share_t "$SHARE_DIR(/.*)?"
        fi
        sudo restorecon -R "$SHARE_DIR"
    else
        sudo chcon -R -t samba_share_t "$SHARE_DIR"
    fi
    ui_ok "SELinux: o Samba lê e grava só em $SHARE_DIR (samba_share_t)"
}

samba_user() {
    local password
    if sudo pdbedit -L 2>/dev/null | grep -q "^$USER:" && ui_confirm "manter a senha atual do Samba de $USER?" y; then
        ui_ok "senha do Samba de $USER mantida"
        return
    fi
    ui_info "a senha do Samba vale só para a pasta de rede; pode ser a mesma do login ou outra"
    ui_secret password "senha do Samba de $USER"
    printf '%s\n%s\n' "$password" "$password" | sudo smbpasswd -s -a "$USER" >/dev/null
    ui_ok "usuário $USER cadastrado no Samba"
}

cmd_install() {
    local domain
    state_setup
    ui_step "Configuração"
    printf "SHARE_DIR='%s'\n" "$SHARE_DIR" > "$ENV_FILE"
    chmod 600 "$ENV_FILE"
    ui_ok "configuração salva em $ENV_FILE"

    ui_step "Samba"
    install_packages
    mkdir -p "$SHARE_DIR"
    write_conf
    selinux_label
    samba_user
    sudo systemctl enable -q "$(smb_service)"
    sudo systemctl restart "$(smb_service)"
    ui_ok "Samba ativo (sobe no boot)"
    host_firewall samba

    ui_step "Acesso"
    ui_ok "Windows: \\\\$(host_lan_ip)\\$SHARE (no Explorador de Arquivos)"
    ui_ok "macOS, Linux e iPhone: smb://$(host_lan_ip)/$SHARE"
    domain="$(env_get CADDY_DOMAIN "" "$ASTRO_HOME/caddy/.env")"
    if [[ -n $domain ]]; then
        ui_ok "pelo nome (em casa e pelo Tailscale, via AdGuard): smb://$(hostname -s).$domain/$SHARE"
    fi
    ui_info "entre com o usuário $USER e a senha do Samba"
    ui_info "arquivos movidos para $SHARE_DIR por fora mantêm o rótulo do SELinux de onde vieram: rode a instalação de novo se algum não aparecer"
}

cmd_actions() {
    return 0
}

cmd_action() {
    ui_fail "ação desconhecida: ${1:-}"
}

cmd_remove() {
    ui_step "Remoção"
    if [[ -f $CONF ]] && grep -qxF "$MARK_BEGIN" "$CONF"; then
        conf_without_share | sudo tee "$CONF.new" >/dev/null
        sudo mv "$CONF.new" "$CONF"
        command -v restorecon >/dev/null && sudo restorecon "$CONF" 2>/dev/null || true
        ui_ok "pasta $SHARE não é mais compartilhada"
    fi
    if command -v pdbedit >/dev/null && sudo pdbedit -L 2>/dev/null | grep -q "^$USER:"; then
        sudo smbpasswd -x "$USER" >/dev/null
        ui_ok "usuário $USER tirado do Samba"
    fi
    if systemctl is-enabled -q "$(smb_service)" 2>/dev/null; then
        sudo systemctl disable -q --now "$(smb_service)"
        ui_ok "Samba desligado"
    fi
    if command -v semanage >/dev/null && sudo semanage fcontext -l -C 2>/dev/null | grep -qF "$SHARE_DIR(/.*)?"; then
        sudo semanage fcontext -d "$SHARE_DIR(/.*)?"
        [[ -d $SHARE_DIR ]] && sudo restorecon -R "$SHARE_DIR"
        ui_ok "SELinux de $SHARE_DIR de volta ao padrão"
    fi
    host_firewall_remove samba
    state_purge
    ui_info "mantidos: pacote do Samba e os arquivos de $SHARE_DIR"
}

case "${1:-}" in
    describe) cmd_describe ;;
    status)   cmd_status ;;
    actions)  cmd_actions ;;
    action)   shift; cmd_action "$@" ;;
    install)  cmd_install ;;
    remove)   cmd_remove ;;
    *)        ui_fail "uso: $0 describe | status | actions | action <id> | install | remove" ;;
esac
