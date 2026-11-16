#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"

ASTRO_PROJECT=desktop
source ../lib/ui.sh
source ../lib/env.sh

EXTENSIONS_DIR="$HOME/.local/share/gnome-shell/extensions"
DCONF_PATH=/org/gnome/shell/
APPS_FILE="$STATE/flatpak-apps.txt"
DCONF_FILE="$STATE/gnome-shell.dconf"
EXTENSIONS_COPY="$STATE/extensions"

cmd_describe() {
    echo "Área de trabalho: apps Flatpak e extensões do GNOME no backup das configurações"
}

cmd_status() {
    [[ -f $ENV_FILE ]]
}

session_run() {
    local runtime="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
    if [[ -S $runtime/bus ]]; then
        DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-unix:path=$runtime/bus}" "$@"
    else
        dbus-run-session -- "$@"
    fi
}

snapshot() {
    local count=0
    mkdir -p "$STATE"
    if command -v flatpak >/dev/null; then
        flatpak list --app --columns=application,origin,installation 2>/dev/null | sort > "$APPS_FILE.new"
        mv "$APPS_FILE.new" "$APPS_FILE"
        count="$(wc -l < "$APPS_FILE")"
    fi
    rm -rf "$EXTENSIONS_COPY"
    if [[ -d $EXTENSIONS_DIR ]]; then
        cp -a "$EXTENSIONS_DIR" "$EXTENSIONS_COPY"
    fi
    if command -v dconf >/dev/null; then
        dconf dump "$DCONF_PATH" > "$DCONF_FILE.new"
        mv "$DCONF_FILE.new" "$DCONF_FILE"
    fi
    ui_ok "$count apps Flatpak, $(find "$EXTENSIONS_COPY" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | wc -l) extensões do GNOME e as configurações do GNOME Shell guardadas"
}

cmd_install() {
    state_setup
    ui_step "Área de trabalho"
    printf "DESKTOP_BACKUP='yes'\n" > "$ENV_FILE"
    chmod 600 "$ENV_FILE"
    snapshot
    ui_info "entram no backup das configurações: a lista dos apps Flatpak (sem os dados deles), as extensões do GNOME e as opções delas"
    ui_info "para trazer de volta: Administração → Backup: configurações ⬅️ local → desktop"
}

cmd_actions() {
    return 0
}

cmd_action() {
    ui_fail "ação desconhecida: ${1:-}"
}

cmd_backup() {
    snapshot >&2
}

restore_apps() {
    local app origin installation installed=() missing=0
    [[ -f $APPS_FILE ]] || return 0
    if ! command -v flatpak >/dev/null; then
        ui_warn "flatpak não instalado: os apps de $APPS_FILE ficaram de fora"
        return 0
    fi
    mapfile -t installed < <(flatpak list --app --columns=application 2>/dev/null)
    while IFS=$'\t' read -r app origin installation; do
        [[ -n $app ]] || continue
        if [[ " ${installed[*]} " == *" $app "* ]]; then
            ui_ok "$app já instalado"
            continue
        fi
        if [[ $installation == user ]]; then
            if flatpak install -y --noninteractive --user "$origin" "$app" >/dev/null 2>&1; then
                ui_ok "$app instalado ($origin, do usuário)"
                continue
            fi
        elif sudo flatpak install -y --noninteractive --system "$origin" "$app" >/dev/null 2>&1; then
            ui_ok "$app instalado ($origin)"
            continue
        fi
        ui_warn "não foi possível instalar $app de $origin: instale pelo Bazaar"
        missing=1
    done < "$APPS_FILE"
    return "$missing"
}

restore_extensions() {
    local dir name
    [[ -d $EXTENSIONS_COPY ]] || return 0
    mkdir -p "$EXTENSIONS_DIR"
    for dir in "$EXTENSIONS_COPY"/*/; do
        [[ -d $dir ]] || continue
        name="$(basename "$dir")"
        rm -rf "${EXTENSIONS_DIR:?}/$name"
        cp -a "$dir" "$EXTENSIONS_DIR/$name"
        ui_ok "extensão $name devolvida"
    done
}

restore_dconf() {
    [[ -f $DCONF_FILE ]] || return 0
    if ! command -v dconf >/dev/null; then
        ui_warn "dconf não instalado: as opções do GNOME Shell ficaram em $DCONF_FILE"
        return 0
    fi
    session_run dconf load "$DCONF_PATH" < "$DCONF_FILE"
    ui_ok "extensões ligadas, favoritos da dock e opções das extensões devolvidos"
}

cmd_restore() {
    state_restore "$1"
    restore_apps || true
    restore_extensions
    restore_dconf
    ui_warn "saia da sessão e entre de novo para o GNOME carregar as extensões"
}

cmd_remove() {
    ui_step "Remoção"
    state_purge
    ui_info "mantidos: os apps Flatpak e as extensões instalados"
}

case "${1:-}" in
    describe) cmd_describe ;;
    status)   cmd_status ;;
    actions)  cmd_actions ;;
    action)   shift; cmd_action "$@" ;;
    install)  cmd_install ;;
    remove)   cmd_remove ;;
    backup)   cmd_backup ;;
    restore)  shift; cmd_restore "$1" ;;
    *)        ui_fail "uso: $0 describe | status | actions | action <id> | install | remove | backup | restore <pasta>" ;;
esac
