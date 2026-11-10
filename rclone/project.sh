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
TICK_CALENDAR=("*-*-* 08..19:00/30:00" "*-*-* 20:00:00")
CONFIG_CALENDAR="*-*-* 01:00:00"
LOCAL_CALENDAR="*-*-* 03:00:00"
RECONFIGURE=false

stop_runs() {
    systemctl --user stop "$UNIT_PREFIX-tick.service" "$UNIT_PREFIX-import-*.service" \
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
    cmd_global_actions
}

cmd_remote_actions() {
    printf '%s\n' \
        "sincronizar|Sincronizar com a nuvem agora|nao" \
        "ver-exclusoes|Ver o que a sincronização apagaria (teste sem efeito; argumento: armazenamento)|nao" \
        "liberar-exclusoes|Liberar as exclusões acima do limite na próxima sincronização (argumento: armazenamento)|sim"
    [[ -n $(env_get CONFIG_BACKUP) ]] && echo "backup|Fazer backup das configurações agora|nao"
    return 0
}

remote_target() {
    local -n __remote_out=$1
    local names=()
    mapfile -t names < <(target_names)
    if [[ -n $2 ]]; then
        [[ -f $TARGETS/$2.env ]] || ui_fail "armazenamento desconhecido: $2 (cadastrados: ${names[*]:-nenhum})"
        __remote_out=$2
    elif ((${#names[@]} == 1)); then
        __remote_out=${names[0]}
    else
        ui_fail "diga qual armazenamento: ${names[*]:-nenhum cadastrado}"
    fi
}

cmd_remote() {
    local name
    case "${1:-}" in
        sincronizar)
            systemctl --user start --no-block "$UNIT_PREFIX-tick.service"
            echo "sincronização iniciada em segundo plano; se der problema, o aviso chega aqui"
            ;;
        ver-exclusoes)
            remote_target name "${2:-}"
            echo "teste sem efeito em $name (listar a nuvem leva alguns minutos):"
            ./run.sh preview "$name"
            ;;
        liberar-exclusoes)
            remote_target name "${2:-}"
            target_set "$name" BISYNC_FORCE yes
            systemctl --user start --no-block "$UNIT_PREFIX-tick.service"
            echo "exclusões liberadas em $name; sincronização iniciada em segundo plano"
            ;;
        backup)
            [[ -n $(env_get CONFIG_BACKUP) ]] || ui_fail "backup das configurações não configurado"
            systemctl --user start --no-block "$UNIT_PREFIX-config.service"
            echo "backup das configurações iniciado em segundo plano; se der problema, o aviso chega aqui"
            ;;
        *) ui_fail "ação desconhecida: ${1:-}" ;;
    esac
}

cmd_global_actions() {
    [[ -n $(env_get CONFIG_BACKUP) ]] || return 0
    printf '%s\n' \
        "backup-now|Fazer backup das configurações agora" \
        "restore|Restaurar uma versão das configurações"
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
    printf '[Unit]\nDescription=astro rclone: %s\n\n[Timer]\n' "$1"
    shift
    printf 'OnCalendar=%s\n' "$@"
    printf 'Persistent=true\n\n[Install]\nWantedBy=timers.target\n'
}

schedules() {
    mkdir -p "$UNIT_DIR"
    if [[ -f $UNIT_DIR/$UNIT_PREFIX-nightly.timer ]]; then
        systemctl --user disable -q --now "$UNIT_PREFIX-nightly.timer" 2>/dev/null || true
        rm -f "$UNIT_DIR/$UNIT_PREFIX-nightly.timer" "$UNIT_DIR/$UNIT_PREFIX-nightly.service"
        ui_ok "espelho noturno na nuvem removido (substituído pela sincronização nos dois sentidos)"
    fi
    write_unit "$UNIT_PREFIX-tick.service" "$(service_unit "sincronização com a nuvem" tick)"
    write_unit "$UNIT_PREFIX-tick.timer" "$(timer_unit "sincronização com a nuvem" "${TICK_CALENDAR[@]}")"
    write_unit "$UNIT_PREFIX-local.service" "$(service_unit "sincronização com a nuvem e espelho no disco de backup" local)"
    write_unit "$UNIT_PREFIX-local.timer" "$(timer_unit "sincronização com a nuvem e espelho no disco de backup" "$LOCAL_CALENDAR")"
    write_unit "$UNIT_PREFIX-config.service" "$(service_unit "backup das configurações" config)"
    write_unit "$UNIT_PREFIX-config.timer" "$(timer_unit "backup das configurações" "$CONFIG_CALENDAR")"
    systemctl --user daemon-reload
    systemctl --user enable -q --now "$UNIT_PREFIX-tick.timer"
    ui_ok "nuvem: sincronização nos dois sentidos a cada 30 minutos, das 08:00 às 20:00, e às 03:00"
    if [[ -n $(env_get CONFIG_BACKUP) ]]; then
        systemctl --user enable -q --now "$UNIT_PREFIX-config.timer"
        ui_ok "configurações: backup criptografado à 01:00 em $(env_get CONFIG_BACKUP)"
    else
        systemctl --user disable -q --now "$UNIT_PREFIX-config.timer" 2>/dev/null || true
    fi
    if [[ -n $(env_get BACKUP_MOUNT) ]]; then
        systemctl --user enable -q --now "$UNIT_PREFIX-local.timer"
        ui_ok "disco de backup: espelho às 03:00, logo depois da sincronização com a nuvem, com $(env_get KEEP_DAYS 30) dias de versões"
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
        systemctl --user stop "$UNIT_PREFIX-import-$name.timer" 2>/dev/null || true
        systemd-run --user --quiet --collect --unit "$UNIT_PREFIX-import-$name" \
            --on-calendar "$(date -d "@$at" '+%F %T')" --setenv ASTRO_PLAIN=1 "$PWD/run.sh" tick
        ui_ok "primeira cópia agendada para $(date -d "@$at" '+%d/%m às %H:%M')"
        ui_info "se a máquina reiniciar antes, ela começa na próxima sincronização (das 08:00 às 20:00)"
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
    ui_warn "depois da primeira cópia, $disk/$folder e a nuvem ficam iguais: o que for criado, alterado ou apagado"
    ui_warn "de um lado vai para o outro (a cada 30 minutos, das 08:00 às 20:00, e às 03:00)"
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
    ui_checklist chosen "Quais armazenamentos remover? (os arquivos não são apagados em lugar nenhum)" --all "${names[@]}"
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
        if [[ $(target_get "$name" TOO_MANY_DELETES) == yes ]]; then
            ui_warn "$name: a última sincronização parou porque apagaria mais de 5% dos arquivos"
            ui_info "confira em \"Ver as últimas execuções\" o que seria apagado antes de liberar"
            if ui_confirm "liberar as exclusões nesta rodada?" n; then
                target_set "$name" BISYNC_FORCE yes
            fi
        fi
    done
    systemctl --user start --no-block "$UNIT_PREFIX-tick.service"
    ui_ok "rodada iniciada em segundo plano (sincronização nos dois sentidos ou primeira cópia pendente)"
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
    local dest default name password days
    name="$(target_names | head -1)"
    if [[ -n $name ]]; then
        default="$(target_get "$name" DISK)/$(target_get "$name" FOLDER)/Astro/Configurações"
    else
        default="$(env_get SOURCE "/srv")/Astro/Configurações"
    fi
    if $RECONFIGURE || ! grep -q '^CONFIG_BACKUP=' "$ENV_FILE"; then
        ui_info "toda noite, à 01:00, a configuração de cada serviço vira um arquivo criptografado nesta pasta (uma subpasta por serviço)"
        ui_input dest "pasta do backup das configurações" "$(env_get CONFIG_BACKUP "$default")" is_path
        ui_input days "por quantos dias guardar as versões do backup das configurações" "$(env_get CONFIG_KEEP_DAYS 90)" is_number
        sed -i '/^CONFIG_BACKUP=/d;/^CONFIG_KEEP_DAYS=/d' "$ENV_FILE"
        printf "CONFIG_BACKUP='%s'\nCONFIG_KEEP_DAYS='%s'\n" "$dest" "$days" >> "$ENV_FILE"
    fi
    ui_ok "backup das configurações em $(env_get CONFIG_BACKUP)/<data e hora>/<serviço>/, $(env_get CONFIG_KEEP_DAYS 90) dias de histórico"
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
        backup-now) action_backup_now ;;
        restore)    action_restore ;;
        *)      ui_fail "ação desconhecida: ${1:-}" ;;
    esac
}

action_backup_now() {
    ui_step "Backup das configurações agora"
    [[ -n $(env_get CONFIG_BACKUP) ]] || ui_fail "backup das configurações não configurado: rode a instalação do rclone"
    ./run.sh config
}

rclone_busy() {
    local unit
    for unit in tick local config; do
        if systemctl --user is-active -q "$UNIT_PREFIX-$unit.service" 2>/dev/null; then
            printf '%s\n' "$UNIT_PREFIX-$unit"
        fi
    done
    if pgrep -u "$USER" -x rclone >/dev/null; then
        printf '%s\n' "processo rclone"
    fi
    return 0
}

version_label() {
    local name=$1 label
    label="${name:8:2}/${name:5:2}/${name:0:4} ${name:11:2}:${name:13:2}:${name:15:2}"
    [[ ${#name} -gt 17 ]] && label+=" (${name:18})"
    label="${label//-/ }"
    printf "%s" "${label//restauracao/restauração}"
}

archive_open() {
    gpg --batch --quiet --homedir "$1/gnupg" --pinentry-mode loopback --passphrase-file "$2" -d "$3"
}

action_restore() {
    ui_step "Restaurar uma versão das configurações"
    local dest version choice name i service file key work password preset log
    local versions=() labels=() services=() chosen=() picked=() busy=() restored=() failed=()
    dest="$(env_get CONFIG_BACKUP)"
    [[ -n $dest && -d $dest ]] || ui_fail "pasta do backup das configurações não encontrada: ${dest:-não configurada}"
    mapfile -t versions < <(config_versions "$dest")
    ((${#versions[@]})) || ui_fail "nenhuma versão em $dest"
    for name in "${versions[@]}"; do
        labels+=("$(version_label "$name")  [$(cd "$dest/$name" && ls -d -- */ 2>/dev/null | tr -d / | paste -sd' ')]")
    done
    ui_menu choice "Qual versão restaurar?" "${labels[@]}" "Voltar"
    ((choice < ${#versions[@]})) || return 0
    version="${versions[choice]}"

    for file in "$dest/$version"/*/*.tar.zst.gpg; do
        [[ -f $file ]] && services+=("$(basename "$(dirname "$file")")")
    done
    ((${#services[@]})) || ui_fail "a versão $version não tem nenhum serviço"
    preset="$(seq -s ' ' 0 $((${#services[@]} - 1)))"
    ui_checklist chosen "Quais serviços restaurar?" --all --selected "$preset" "${services[@]}"
    ((${#chosen[@]})) || { ui_info "nenhum serviço escolhido"; return 0; }
    for i in "${chosen[@]}"; do picked+=("${services[i]}"); done
    ui_warn "a configuração atual de ${picked[*]} será trocada pela de $(version_label "$version")"
    ui_info "antes, a situação atual vira uma versão \"antes da restauração\", para poder voltar"
    ui_confirm "continuar?" n || { ui_info "cancelado"; return 0; }

    mapfile -t busy < <(rclone_busy)
    if ((${#busy[@]})); then
        ui_warn "o rclone está trabalhando agora: ${busy[*]}"
        ui_confirm "parar o que está rodando? (a primeira cópia da nuvem continua de onde parou depois)" y \
            || { ui_info "cancelado: tente de novo quando terminar"; return 0; }
        stop_runs
        if ! timeout 60 bash -c "while pgrep -u '$USER' -x rclone >/dev/null; do sleep 1; done"; then
            ui_fail "ainda há um processo do rclone rodando; tente de novo em instantes"
        fi
    fi
    exec 8>"$LOCK"
    flock -n 8 || ui_fail "uma rodada do rclone acabou de começar; tente de novo"
    exec 7>"$CONFIG_LOCK"
    flock -n 7 || ui_fail "um backup das configurações está em andamento; tente de novo"
    ui_ok "rclone parado: nenhuma rodada começa até o fim da restauração"

    work="$(mktemp -d -p /var/tmp astro-restore.XXXXXX)"
    mkdir -p "$work/gnupg" "$work/extract"
    chmod 700 "$work" "$work/gnupg"
    key="$CONFIG_KEY"
    file="$dest/$version/${picked[0]}/${picked[0]}.tar.zst.gpg"
    if [[ ! -s $key ]] || ! archive_open "$work" "$key" "$file" >/dev/null 2>&1; then
        ui_warn "a senha guardada não abre esta versão"
        key="$work/key"
        while true; do
            ui_secret password "senha do backup desta versão"
            (umask 077 && printf '%s' "$password" > "$key")
            archive_open "$work" "$key" "$file" >/dev/null 2>&1 && break
            ui_warn "senha errada"
        done
    fi

    ui_step "Backup da situação atual"
    if ! ASTRO_LOCKED=1 ./run.sh config antes-da-restauracao 7>&- 8>&-; then
        podman unshare rm -rf "$work"
        ui_fail "o backup da situação atual falhou: nada foi alterado"
    fi

    for service in "${picked[@]}"; do
        file="$dest/$version/$service/$service.tar.zst.gpg"
        if ! archive_open "$work" "$key" "$file" | podman unshare tar --zstd -x --numeric-owner -C "$work/extract" -f -; then
            podman unshare rm -rf "$work"
            ui_fail "não foi possível abrir $file: nada foi alterado"
        fi
    done

    for service in "${picked[@]}"; do
        ui_step "Restaurando $service"
        if [[ $service == host ]]; then
            cp "$work/extract/host/host.env" "$ASTRO_HOME/host.env" && restored+=(host) || failed+=(host)
        elif [[ $service == rclone ]]; then
            cmd_restore "$work/extract/rclone" && restored+=(rclone) || failed+=(rclone)
        elif [[ -x ../$service/project.sh ]] && grep -q '^    restore)' "../$service/project.sh"; then
            if ../"$service"/project.sh restore "$work/extract/$service" 7>&- 8>&-; then
                restored+=("$service")
            else
                failed+=("$service")
            fi
        else
            ui_warn "$service não sabe restaurar a configuração"
            failed+=("$service")
        fi
    done
    podman unshare rm -rf "$work"

    ui_step "Resumo"
    ((${#restored[@]})) && ui_ok "restaurados de $(version_label "$version"): ${restored[*]}"
    if ((${#failed[@]})); then
        ui_error "falharam: ${failed[*]} (a situação anterior está na versão \"antes da restauração\")"
        return 1
    fi
    return 0
}

cmd_restore() {
    local backup keep
    backup="$(env_get CONFIG_BACKUP)"
    keep="$(env_get CONFIG_KEEP_DAYS 90)"
    stop_runs
    state_restore "$1" data/config-backup.key
    sed -i '/^CONFIG_BACKUP=/d;/^CONFIG_KEEP_DAYS=/d' "$ENV_FILE"
    printf "CONFIG_BACKUP='%s'\nCONFIG_KEEP_DAYS='%s'\n" "$backup" "$keep" >> "$ENV_FILE"
    ui_ok "pasta do backup das configurações e senha atuais mantidas"
}

cmd_remove() {
    local purge=false unit
    [[ ${1:-} == --purge ]] && purge=true

    ui_step "Remoção"
    systemctl --user stop "$UNIT_PREFIX-import-*.timer" 2>/dev/null || true
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
    global-actions) cmd_global_actions ;;
    remote-actions) cmd_remote_actions ;;
    remote)   shift; cmd_remote "$@" ;;
    action)   shift; cmd_action "$@" ;;
    install)  cmd_install ;;
    remove)   shift; cmd_remove "$@" ;;
    restore)  shift; cmd_restore "$1" ;;
    *)        ui_fail "uso: $0 describe | status | actions | global-actions | remote-actions | remote <id> [argumento] | action <id> | install | remove [--purge] | restore <pasta>" ;;
esac
