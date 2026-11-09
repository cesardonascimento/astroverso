#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"

ASTRO_PROJECT=rclone
source ../lib/ui.sh
source ../lib/host.sh
source ../lib/env.sh
source ../lib/disk.sh
source common.sh

UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
UNIT_PREFIX=astro-rclone
TICK_CALENDAR="*:0/15"
CONFIG_CALENDAR="*-*-* 01:00:00"
NIGHTLY_CALENDAR="*-*-* 02:00:00"
LOCAL_CALENDAR="*-*-* 03:00:00"
RECONFIGURE=false

stop_runs() {
    systemctl --user stop "$UNIT_PREFIX-tick.service" "$UNIT_PREFIX-nightly.service" \
        "$UNIT_PREFIX-local.service" "$UNIT_PREFIX-config.service" 2>/dev/null || true
    ui_ok "rodadas em andamento paradas (a primeira cópia continua de onde parou)"
}

cmd_describe() {
    echo "rclone: backup dos discos em outro disco e em armazenamentos em nuvem"
}

cmd_status() {
    systemctl --user is-enabled -q "$UNIT_PREFIX-tick.timer" 2>/dev/null
}

cmd_actions() {
    printf '%s\n' \
        "status|Ver as últimas execuções" \
        "now|Sincronizar agora" \
        "add|Adicionar armazenamento em nuvem" \
        "login|Reconectar a um armazenamento em nuvem" \
        "remove|Remover armazenamento em nuvem"
}

data_disks() {
    disk_mounts rclone
}

pick_data_disk() {
    local -n __pick_out=$1
    local title=$2 default=${3:-} mount owner mounts=() labels=() choice
    while read -r mount owner; do
        if [[ $mount == "$default" ]]; then
            mounts=("$mount" "${mounts[@]}")
            labels=("$mount  (do $owner)" "${labels[@]}")
        else
            mounts+=("$mount")
            labels+=("$mount  (do $owner)")
        fi
    done < <(data_disks)
    if ((${#mounts[@]} == 0)); then
        ui_fail "nenhum disco de dados montado pelo astro: instale antes um projeto com discos (ex.: nextcloud)"
    fi
    ui_menu choice "$title" "${labels[@]}"
    __pick_out=${mounts[choice]}
}

configure() {
    ui_step "Configuração"
    local current_disks
    current_disks="$(env_get BACKUP_DISKS)"
    if [[ -f $ENV_FILE ]] && ui_confirm "usar a configuração já salva em $ENV_FILE?" y; then
        ui_ok "configuração existente mantida"
        return
    fi
    RECONFIGURE=true
    local disks=() source="" days backup
    backup="$(env_get CONFIG_BACKUP)"
    disk_choose disks rclone "Qual disco recebe o espelho noturno? (deixe vazio para só nuvem)" "$current_disks"
    if ((${#disks[@]} > 1)); then
        ui_warn "use um disco só; ficou o primeiro marcado"
        disks=("${disks[0]}")
    fi
    if ((${#disks[@]})); then
        pick_data_disk source "Qual disco copiar para ele toda noite?" "$(env_get SOURCE)"
        ui_input days "por quantos dias guardar o que for apagado ou alterado" "$(env_get KEEP_DAYS 30)" is_number
    else
        days=30
    fi
    (
        umask 077
        printf "BACKUP_DISKS='%s'\nSOURCE='%s'\nKEEP_DAYS='%s'\nCONFIG_BACKUP='%s'\n" "${disks[*]}" "$source" "$days" "$backup" > "$ENV_FILE.new"
    )
    mv "$ENV_FILE.new" "$ENV_FILE"
    ui_ok "configuração salva em $ENV_FILE"
}

install_rclone() {
    if command -v rclone >/dev/null; then
        ui_ok "rclone já instalado ($(rclone version | head -1))"
    elif command -v dnf >/dev/null; then
        sudo dnf install -y -q rclone
        ui_ok "rclone instalado via dnf"
    elif command -v apt-get >/dev/null; then
        sudo apt-get install -y -qq rclone
        ui_ok "rclone instalado via apt"
    else
        ui_fail "instale o rclone manualmente: https://rclone.org/install/"
    fi
}

backup_disk() {
    local uuids=() mount
    read -ra uuids <<< "$(env_get BACKUP_DISKS)"
    disk_setup rclone "x-gvfs-hide,x-systemd.before=user@$(id -u).service" "${uuids[@]}"
    mount="${DISK_MOUNTS[0]:-}"
    sed -i '/^BACKUP_MOUNT=/d' "$ENV_FILE"
    printf "BACKUP_MOUNT='%s'\n" "$mount" >> "$ENV_FILE"
    [[ -n $mount ]] || return 0
    if mountpoint -q "$mount"; then
        sudo chown "$USER:" "$mount"
        sudo chmod 700 "$mount"
        mkdir -p "$mount/atual" "$mount/versoes"
        ui_ok "$mount: só $USER acessa (atual/ e versoes/)"
    fi
}

write_unit() {
    local name=$1 content=$2 file="$UNIT_DIR/$1"
    if [[ $(cat "$file" 2>/dev/null) != "$content" ]]; then
        printf '%s\n' "$content" > "$file"
    fi
}

service_unit() {
    printf '[Unit]\nDescription=astro rclone: %s\nAfter=network-online.target\n\n[Service]\nType=oneshot\nTimeoutStartSec=infinity\nEnvironment=ASTRO_PLAIN=1\nExecStart=%s %s\n' \
        "$1" "$PWD/run.sh" "$2"
}

timer_unit() {
    printf '[Unit]\nDescription=astro rclone: %s\n\n[Timer]\nOnCalendar=%s\nPersistent=true\n\n[Install]\nWantedBy=timers.target\n' \
        "$1" "$2"
}

schedules() {
    mkdir -p "$UNIT_DIR"
    write_unit "$UNIT_PREFIX-tick.service" "$(service_unit "envio a cada 15 minutos" tick)"
    write_unit "$UNIT_PREFIX-tick.timer" "$(timer_unit "envio a cada 15 minutos" "$TICK_CALENDAR")"
    write_unit "$UNIT_PREFIX-nightly.service" "$(service_unit "espelho noturno na nuvem" nightly)"
    write_unit "$UNIT_PREFIX-nightly.timer" "$(timer_unit "espelho noturno na nuvem" "$NIGHTLY_CALENDAR")"
    write_unit "$UNIT_PREFIX-local.service" "$(service_unit "espelho noturno no disco de backup" local)"
    write_unit "$UNIT_PREFIX-local.timer" "$(timer_unit "espelho noturno no disco de backup" "$LOCAL_CALENDAR")"
    write_unit "$UNIT_PREFIX-config.service" "$(service_unit "backup das configurações" config)"
    write_unit "$UNIT_PREFIX-config.timer" "$(timer_unit "backup das configurações" "$CONFIG_CALENDAR")"
    systemctl --user daemon-reload
    systemctl --user enable -q --now "$UNIT_PREFIX-tick.timer" "$UNIT_PREFIX-nightly.timer"
    ui_ok "nuvem: envio a cada 15 minutos e espelho com exclusões às 02:00"
    if [[ -n $(env_get CONFIG_BACKUP) ]]; then
        systemctl --user enable -q --now "$UNIT_PREFIX-config.timer"
        ui_ok "configurações: backup criptografado à 01:00 em $(env_get CONFIG_BACKUP)"
    else
        systemctl --user disable -q --now "$UNIT_PREFIX-config.timer" 2>/dev/null || true
    fi
    if [[ -n $(env_get BACKUP_MOUNT) ]]; then
        systemctl --user enable -q --now "$UNIT_PREFIX-local.timer"
        ui_ok "disco de backup: espelho às 03:00, com $(env_get KEEP_DAYS 30) dias de versões"
    else
        systemctl --user disable -q --now "$UNIT_PREFIX-local.timer" 2>/dev/null || true
    fi
}

pick_provider() {
    local -n __provider_out=$1
    local files=() labels=() file choice
    for file in "$PROVIDERS"/*.sh; do
        files+=("$(basename "$file" .sh)")
        labels+=("$(provider_load "$(basename "$file" .sh)" && provider_describe)")
    done
    ui_menu choice "Qual armazenamento em nuvem?" "${labels[@]}"
    __provider_out=${files[choice]}
}

folder_in_use() {
    local disk=$1 folder=$2 name
    for name in $(target_names); do
        [[ $(target_get "$name" DISK) == "$disk" && $(target_get "$name" FOLDER) == "$folder" ]] && return 0
    done
    return 1
}

schedule_import() {
    local name=$1 choice time at
    ui_menu choice "Quando fazer a primeira cópia da nuvem para o disco?" \
        "Agora, em segundo plano" "Num horário" "Depois, pelo menu (Sincronizar agora)"
    case $choice in
        0) at="$(date +%s)" ;;
        1)
            ui_input time "horário (HH:MM)" "02:00" is_time
            at="$(date -d "$time" +%s)"
            (( at > $(date +%s) )) || at="$(date -d "tomorrow $time" +%s)"
            ;;
        2) at=manual ;;
    esac
    target_set "$name" IMPORT_AT "$at"
    target_set "$name" IMPORT_DONE no
    if [[ $at == manual ]]; then
        ui_ok "primeira cópia fica para quando você escolher \"Sincronizar agora\""
    elif ((at <= $(date +%s))); then
        systemctl --user start --no-block "$UNIT_PREFIX-tick.service"
        ui_ok "primeira cópia começou em segundo plano (acompanhe em \"Ver as últimas execuções\")"
    else
        ui_ok "primeira cópia agendada para $(date -d "@$at" '+%d/%m às %H:%M') (começa em até 15 minutos depois)"
    fi
}

action_add() {
    ui_step "Adicionar armazenamento em nuvem"
    command -v rclone >/dev/null || ui_fail "instale o projeto rclone primeiro"
    local provider name disk folder
    pick_provider provider
    provider_load "$provider"
    while true; do
        ui_input name "nome do armazenamento (pasta padrão e nome no rclone)" "$(provider_default_name)" is_folder
        [[ -f $TARGETS/$name.env ]] || break
        ui_warn "já existe um armazenamento chamado $name"
    done
    pick_data_disk disk "Em qual disco guardar a cópia de $(provider_describe)?" "$(env_get SOURCE)"
    while true; do
        ui_input folder "pasta dentro de $disk (nunca a raiz do disco)" "$name" is_folder
        folder_in_use "$disk" "$folder" || break
        ui_warn "$disk/$folder já é usada por outro armazenamento"
    done
    provider_configure "$name"
    mkdir -p "$TARGETS"
    target_set "$name" PROVIDER "$provider"
    target_set "$name" DISK "$disk"
    target_set "$name" FOLDER "$folder"
    target_set "$name" REMOTE_PATH ""
    ui_ok "$(provider_describe) ↔ $disk/$folder"
    ui_warn "a partir da primeira cópia, quem manda é $disk/$folder: o que for apagado só na nuvem volta, e o que"
    ui_warn "for apagado aqui é apagado lá à noite. Mexa nos arquivos pelo Nextcloud, não pelo app da nuvem"
    schedule_import "$name"
}

pick_target() {
    local -n __target_out=$1
    local names=() choice
    mapfile -t names < <(target_names)
    ((${#names[@]})) || ui_fail "nenhum armazenamento em nuvem cadastrado"
    ui_menu choice "$2" "${names[@]}"
    __target_out=${names[choice]}
}

action_login() {
    ui_step "Reconectar"
    local name
    pick_target name "Qual armazenamento reconectar?"
    provider_load "$(target_get "$name" PROVIDER)"
    provider_configure "$name"
}

action_remove() {
    ui_step "Remover armazenamento em nuvem"
    local names=() chosen=() i
    mapfile -t names < <(target_names)
    ((${#names[@]})) || { ui_info "nenhum armazenamento em nuvem cadastrado"; return; }
    ui_checklist chosen "Quais armazenamentos remover? (os arquivos não são apagados em lugar nenhum)" "${names[@]}"
    for i in "${chosen[@]}"; do
        rm -f "$TARGETS/${names[i]}.env"
        rclone_section_remove "${names[i]}"
        ui_ok "${names[i]} removido (a cópia local e a nuvem ficam como estão)"
    done
}

action_status() {
    ui_step "Armazenamentos em nuvem"
    local name at
    for name in $(target_names); do
        if [[ $(target_get "$name" IMPORT_DONE) == yes ]]; then
            ui_ok "$name: $(target_get "$name" DISK)/$(target_get "$name" FOLDER), primeira cópia concluída"
        else
            at="$(target_get "$name" IMPORT_AT)"
            [[ $at == manual ]] && at="aguardando \"Sincronizar agora\"" || at="a partir de $(date -d "@$at" '+%d/%m %H:%M')"
            ui_info "$name: primeira cópia pendente, $at"
        fi
    done
    [[ -n $(target_names) ]] || ui_info "nenhum cadastrado"
    ui_step "Agendamentos"
    systemctl --user list-timers --all "$UNIT_PREFIX-*" --no-pager 2>/dev/null | ui_prefix || true
    ui_step "Últimas mensagens"
    journalctl --user -u "$UNIT_PREFIX-*" -n 25 --no-pager -o cat 2>/dev/null | ui_prefix || true
}

action_now() {
    ui_step "Sincronizar agora"
    local name
    for name in $(target_names); do
        if [[ $(target_get "$name" IMPORT_DONE) != yes ]]; then
            target_set "$name" IMPORT_AT "$(date +%s)"
        fi
    done
    systemctl --user start --no-block "$UNIT_PREFIX-tick.service"
    ui_ok "rodada iniciada em segundo plano (envio dos arquivos recentes ou primeira cópia pendente)"
    ui_info "acompanhe em \"Ver as últimas execuções\" ou com: journalctl --user -fu $UNIT_PREFIX-tick"
}

cmd_install() {
    state_setup stop_runs .env data
    configure

    ui_step "Host"
    host_base
    install_rclone

    ui_step "Disco de backup"
    backup_disk

    ui_step "Armazenamentos em nuvem"
    if [[ -n $(target_names) ]]; then
        local name
        for name in $(target_names); do
            ui_ok "$name ↔ $(target_get "$name" DISK)/$(target_get "$name" FOLDER)"
        done
    elif ui_confirm "adicionar um armazenamento em nuvem agora?" y; then
        action_add
    else
        ui_info "adicione depois em \"Configurar um projeto instalado\""
    fi

    ui_step "Backup das configurações"
    config_backup_setup

    ui_step "Agendamentos"
    schedules
}

config_backup_setup() {
    local dest default name password
    name="$(target_names | head -1)"
    if [[ -n $name ]]; then
        default="$(target_get "$name" DISK)/$(target_get "$name" FOLDER)/Astro/Configurações"
    else
        default="$(env_get SOURCE "/srv")/Astro/Configurações"
    fi
    if $RECONFIGURE || ! grep -q '^CONFIG_BACKUP=' "$ENV_FILE"; then
        ui_info "toda noite, à 01:00, a configuração de cada serviço vira um arquivo criptografado nesta pasta (uma subpasta por serviço)"
        ui_input dest "pasta do backup das configurações" "$(env_get CONFIG_BACKUP "$default")" is_path
        sed -i '/^CONFIG_BACKUP=/d' "$ENV_FILE"
        printf "CONFIG_BACKUP='%s'\n" "$dest" >> "$ENV_FILE"
    fi
    ui_ok "backup das configurações em $(env_get CONFIG_BACKUP)/<serviço>/<serviço>.tar.zst.gpg"
    if [[ -s $CONFIG_KEY ]] && ui_confirm "manter a senha atual do backup das configurações?" y; then
        ui_ok "senha mantida"
        return
    fi
    ui_warn "guarde esta senha fora da máquina (ex.: gerenciador de senhas): sem ela, o backup não abre"
    ui_secret password "senha do backup das configurações"
    mkdir -p "$DATA"
    (umask 077 && printf '%s' "$password" > "$CONFIG_KEY")
    ui_ok "senha guardada em $CONFIG_KEY (só $USER lê)"
}

cmd_action() {
    case "${1:-}" in
        status) action_status ;;
        now)    action_now ;;
        add)    action_add ;;
        login)  action_login ;;
        remove) action_remove ;;
        *)      ui_fail "ação desconhecida: ${1:-}" ;;
    esac
}

cmd_remove() {
    local purge=false unit
    [[ ${1:-} == --purge ]] && purge=true

    ui_step "Remoção"
    for unit in tick nightly local config; do
        systemctl --user disable -q --now "$UNIT_PREFIX-$unit.timer" 2>/dev/null || true
        rm -f "$UNIT_DIR/$UNIT_PREFIX-$unit.timer" "$UNIT_DIR/$UNIT_PREFIX-$unit.service"
    done
    systemctl --user daemon-reload
    ui_ok "agendamentos removidos"
    if [[ -n $(disk_block "$DISK_FSTAB" rclone) ]]; then
        disk_release rclone
    fi
    if $purge && [[ -d data ]]; then
        rm -rf data
        ui_ok "configuração da nuvem apagada (rclone/data: logins e armazenamentos)"
    fi
    ui_info "mantidos: os arquivos nos discos, na nuvem e o rclone"
}

case "${1:-}" in
    describe) cmd_describe ;;
    status)   cmd_status ;;
    actions)  cmd_actions ;;
    action)   shift; cmd_action "$@" ;;
    install)  cmd_install ;;
    remove)   shift; cmd_remove "$@" ;;
    *)        ui_fail "uso: $0 describe | status | actions | action <id> | install | remove [--purge]" ;;
esac
