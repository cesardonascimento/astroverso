#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"

ASTROVERSO_PROJECT=rclone
source ../lib/ui.sh
source ../lib/host.sh
source ../lib/env.sh
source ../lib/disk.sh
source common.sh

UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
UNIT_PREFIX=astroverso-rclone
TICK_CALENDAR=("*-*-* 08..20/2:00:00")
CONFIG_CALENDAR="*-*-* 01:00:00"
LOCAL_CALENDAR="*-*-* 03:00:00"
NETWORK_CALENDAR="*-*-* *:00/15:00"
RECONFIGURE=false

stop_runs() {
    systemctl --user stop "$UNIT_PREFIX-tick.service" "$UNIT_PREFIX-import-*.service" \
        "$UNIT_PREFIX-local.service" "$UNIT_PREFIX-config.service" "$UNIT_PREFIX-network.service" 2>/dev/null || true
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
        "now|Backup: local 🔄 nuvem (agora)" \
        "add|Adicionar armazenamento em nuvem" \
        "login|Reconectar a um armazenamento em nuvem" \
        "remove|Remover armazenamento em nuvem" \
        "network-now|Backup: rede ➡️ local (agora)" \
        "network-add|Adicionar cópia da rede" \
        "network-login|Reconectar a uma cópia da rede" \
        "network-remove|Remover cópia da rede"
}

cmd_remote_actions() {
    printf '%s\n' \
        "backup:cloud|Backup: local 🔄 nuvem agora (roda a fase atual: ⬅️, ↔️ ou 🔄)|nao" \
        "backup:cloud-check|Backup: local 🔄 nuvem (teste): o que a sincronização apagaria, sem efeito (argumento: armazenamento)|nao" \
        "backup:cloud-force|Backup: local 🔄 nuvem (liberar exclusões acima do limite na próxima rodada; argumento: armazenamento)|sim"
    [[ -n $(env_get BACKUP_MOUNT) ]] && echo "backup:daily|Backup: local ➡️ backup diário agora (sincroniza com a nuvem antes)|nao"
    [[ -n $(env_get CONFIG_BACKUP) ]] && echo "backup:configs|Backup: configurações ➡️ local agora|nao"
    [[ -n $(share_names) ]] && echo "backup:network|Backup: rede ➡️ local agora (argumento: cópia; sem ele, todas)|nao"
    return 0
}

cmd_help() {
    local group="Backups"
    printf '%s\n' \
        "$group|Backup: local ⬅️ nuvem|download inicial: traz tudo da nuvem para o disco, sem apagar nada|uma vez, ao cadastrar a nuvem|backup:cloud|10" \
        "$group|Backup: local ↔️ nuvem|mesclagem: junta disco e nuvem, sem apagar nada|depois do download inicial, ou se o estado se perder|backup:cloud|20" \
        "$group|Backup: local 🔄 nuvem|sincronização: o que é criado, alterado ou apagado de um lado vai para o outro|de 2 em 2 horas, das 08:00 às 20:00|backup:cloud|30" \
        "$group|Backup: local 🔄 nuvem (teste)|mostra o que a sincronização apagaria, sem efeito|quando chegar um aviso de exclusões|backup:cloud-check|40" \
        "$group|Backup: local 🔄 nuvem (liberar exclusões)|libera o limite de 5% numa rodada; pede confirmação|depois de conferir o teste|backup:cloud-force|50"
    [[ -n $(env_get BACKUP_MOUNT) ]] && echo "$group|Backup: local ➡️ backup diário|cópia do disco no disco de backup, com as versões do dia (sincroniza com a nuvem antes)|03:00|backup:daily|60"
    if [[ -n $(env_get CONFIG_BACKUP) ]]; then
        printf '%s\n' \
            "$group|Backup: configurações ➡️ local|arquivo criptografado de cada serviço|01:00|backup:configs|70" \
            "$group|Backup: configurações ⬅️ local|restaura uma versão das configurações|pelo assistente (Administração)|-|90"
    fi
    [[ -n $(share_names) ]] && echo "$group|Backup: rede ➡️ local|cópia de uma pasta compartilhada de outra máquina da rede; o disco fica igual a ela|uma vez por dia, na primeira vez em que a máquina responder (testa a cada 15 min)|backup:network|65"
    return 0
}

cloud_now() {
    systemctl --user start --no-block "$UNIT_PREFIX-tick.service"
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
        backup:cloud)
            cloud_now
            echo "Backup: local 🔄 nuvem iniciado em segundo plano; o início e o fim chegam aqui"
            ;;
        backup:cloud-check)
            remote_target name "${2:-}"
            echo "teste sem efeito em $name (listar a nuvem leva alguns minutos):"
            ./run.sh preview "$name"
            ;;
        backup:cloud-force)
            remote_target name "${2:-}"
            target_set "$name" BISYNC_FORCE yes
            cloud_now
            echo "exclusões liberadas em $name; Backup: local 🔄 nuvem iniciado em segundo plano"
            ;;
        backup:daily)
            [[ -n $(env_get BACKUP_MOUNT) ]] || ui_fail "disco de backup não configurado"
            systemctl --user start --no-block "$UNIT_PREFIX-local.service"
            echo "Backup: local ➡️ backup diário iniciado em segundo plano (em $(env_get BACKUP_MOUNT)); o início e o fim chegam aqui"
            ;;
        backup:network)
            network_force "${2:-}"
            echo "Backup: rede ➡️ local iniciado em segundo plano; o resultado chega aqui"
            ;;
        backup:configs)
            [[ -n $(env_get CONFIG_BACKUP) ]] || ui_fail "backup das configurações não configurado"
            systemctl --user start --no-block "$UNIT_PREFIX-config.service"
            echo "Backup: configurações ➡️ local iniciado em segundo plano; o início e o fim chegam aqui"
            ;;
        *) ui_fail "ação desconhecida: ${1:-}" ;;
    esac
}

cmd_global_actions() {
    [[ -n $(env_get CONFIG_BACKUP) ]] || return 0
    printf '%s\n' \
        "backup-now|Backup: configurações ➡️ local (agora)" \
        "restore|Backup: configurações ⬅️ local (restaurar uma versão)"
}

data_disks() {
    local skip=${1:-} mount type
    while read -r mount type; do
        [[ $mount == "$skip" ]] || printf '%s %s\n' "$mount" "$type"
    done < <(disk_mounts | sort -k2,2r -k1,1)
}

pick_data_disk() {
    local -n __pick_out=$1
    local title=$2 default=${3:-} skip=${4:-} mount type mounts=() labels=() choice
    while read -r mount type; do
        if [[ $mount == "$default" ]]; then
            mounts=("$mount" "${mounts[@]}")
            labels=("$mount  ($type)" "${labels[@]}")
        else
            mounts+=("$mount")
            labels+=("$mount  ($type)")
        fi
    done < <(data_disks "$skip")
    if ((${#mounts[@]} == 0)); then
        ui_fail "nenhum disco da máquina em $DISK_ROOT: cadastre em Gerenciar Astroverso → Administração → Discos da máquina"
    fi
    ui_menu choice "$title" "${labels[@]}"
    __pick_out=${mounts[choice]}
}

configure() {
    ui_step "Configuração"
    if config_reuse; then
        ui_ok "configuração existente mantida"
        return
    fi
    RECONFIGURE=true
    local mount type mounts=() labels=() choice current backup_mount="" source days backup
    backup="$(env_get CONFIG_BACKUP)"
    current="$(env_get SOURCE)"
    while read -r mount type; do
        if [[ $mount == "$current" ]]; then
            mounts=("$mount" "${mounts[@]}")
            labels=("$mount  ($type)" "${labels[@]}")
        else
            mounts+=("$mount")
            labels+=("$mount  ($type)")
        fi
    done < <(data_disks)
    mounts+=("")
    labels+=("Nenhum (sem espelho, só a nuvem)")
    ui_step "Espelho noturno"
    ui_info "o espelho copia um disco inteiro para outro toda noite, às 03:00"
    ui_menu choice "ORIGEM: qual disco proteger (o que será copiado)?" "${labels[@]}"
    source=${mounts[choice]}
    if [[ -n $source && -z $(data_disks "$source") ]]; then
        ui_warn "não há outro disco da máquina para receber a cópia de $source: sem espelho noturno"
        source=""
    fi
    if [[ -n $source ]]; then
        pick_data_disk backup_mount "DESTINO: em qual disco guardar a cópia de $source?" "$(env_get BACKUP_MOUNT)" "$source"
        ui_input days "por quantos dias guardar o que for apagado ou alterado" "$(env_get KEEP_DAYS 30)" is_number
        ui_ok "espelho noturno: $source → $backup_mount/atual"
        ui_info "o que for apagado ou alterado na origem fica em $backup_mount/versoes por $days dias"
    else
        days=30
        ui_info "sem espelho noturno"
    fi
    (
        umask 077
        printf "BACKUP_MOUNT='%s'\nSOURCE='%s'\nKEEP_DAYS='%s'\nCONFIG_BACKUP='%s'\n" "$backup_mount" "$source" "$days" "$backup" > "$ENV_FILE.new"
    )
    mv "$ENV_FILE.new" "$ENV_FILE"
    ui_ok "configuração salva em $ENV_FILE"
}

install_rclone() {
    local package missing=()
    for package in rclone zstd; do
        command -v "$package" >/dev/null || missing+=("$package")
    done
    if ((${#missing[@]} == 0)); then
        ui_ok "rclone já instalado ($(rclone version | head -1))"
    elif command -v dnf >/dev/null; then
        sudo dnf install -y -q "${missing[@]}"
        ui_ok "instalados via dnf: ${missing[*]}"
    elif command -v apt-get >/dev/null; then
        sudo apt-get install -y -qq "${missing[@]}"
        ui_ok "instalados via apt: ${missing[*]}"
    else
        ui_fail "instale manualmente: ${missing[*]}"
    fi
}

backup_disk() {
    local mount
    mount="$(env_get BACKUP_MOUNT)"
    [[ -n $mount ]] || return 0
    if ! mountpoint -q "$mount"; then
        ui_warn "$mount não está montado: o espelho fica parado até ele voltar (veja Gerenciar Astroverso → Administração → Discos da máquina)"
        return 0
    fi
    [[ $(disk_type "$mount") == compartilhado ]] && ui_warn "$mount é compartilhado: todos os usuários da máquina leem o espelho"
    mkdir -p "$mount/atual" "$mount/versoes"
    ui_ok "espelho noturno em $mount (atual/ e versoes/)"
}

write_unit() {
    local name=$1 content=$2 file="$UNIT_DIR/$1"
    if [[ $(cat "$file" 2>/dev/null) != "$content" ]]; then
        printf '%s\n' "$content" > "$file"
    fi
}

service_unit() {
    printf '[Unit]\nDescription=astroverso rclone: %s\nAfter=network-online.target\n\n[Service]\nType=oneshot\nTimeoutStartSec=infinity\nEnvironment=ASTROVERSO_PLAIN=1\nNice=19\nCPUSchedulingPolicy=idle\nIOSchedulingClass=idle\nExecStart=%s %s\n' \
        "$1" "$PWD/run.sh" "$2"
}

timer_unit() {
    printf '[Unit]\nDescription=astroverso rclone: %s\n\n[Timer]\n' "$1"
    shift
    printf 'OnCalendar=%s\n' "$@"
    printf 'Persistent=true\n\n[Install]\nWantedBy=timers.target\n'
}

write_units() {
    mkdir -p "$UNIT_DIR"
    write_unit "$UNIT_PREFIX-tick.service" "$(service_unit "Backup: local 🔄 nuvem" tick)"
    write_unit "$UNIT_PREFIX-tick.timer" "$(timer_unit "Backup: local 🔄 nuvem" "${TICK_CALENDAR[@]}")"
    write_unit "$UNIT_PREFIX-local.service" "$(service_unit "Backup: local ➡️ backup diário" local)"
    write_unit "$UNIT_PREFIX-local.timer" "$(timer_unit "Backup: local ➡️ backup diário" "$LOCAL_CALENDAR")"
    write_unit "$UNIT_PREFIX-config.service" "$(service_unit "Backup: configurações ➡️ local" config)"
    write_unit "$UNIT_PREFIX-config.timer" "$(timer_unit "Backup: configurações ➡️ local" "$CONFIG_CALENDAR")"
    write_unit "$UNIT_PREFIX-network.service" "$(service_unit "Backup: rede ➡️ local" network)"
    write_unit "$UNIT_PREFIX-network.timer" "$(timer_unit "Backup: rede ➡️ local" "$NETWORK_CALENDAR")"
    systemctl --user daemon-reload
}

schedules() {
    write_units
    systemctl --user enable -q --now "$UNIT_PREFIX-tick.timer"
    ui_ok "Backup: local 🔄 nuvem de 2 em 2 horas, das 08:00 às 20:00, e às 03:00, com prioridade baixa"
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
    network_schedule
}

network_schedule() {
    if [[ -n $(share_names) ]]; then
        systemctl --user enable -q --now "$UNIT_PREFIX-network.timer"
        ui_ok "cópias da rede: a cada 15 min, cada máquina que responder é copiada uma vez por dia"
    else
        systemctl --user disable -q --now "$UNIT_PREFIX-network.timer" 2>/dev/null || true
    fi
}

network_force() {
    local name names=()
    mapfile -t names < <(share_names)
    ((${#names[@]})) || ui_fail "nenhuma cópia da rede cadastrada"
    if [[ -n $1 ]]; then
        [[ -f $SHARES/$1.env ]] || ui_fail "cópia desconhecida: $1 (cadastradas: ${names[*]})"
        names=("$1")
    fi
    for name in "${names[@]}"; do
        share_set "$name" FORCE yes
    done
    systemctl --user start --no-block "$UNIT_PREFIX-network.service"
}

paths_overlap() {
    [[ $1 == "$2" || $1 == "$2"/* || $2 == "$1"/* ]]
}

dest_conflict() {
    local path=$1 name other
    for name in $(target_names); do
        other="$(target_get "$name" DISK)/$(target_get "$name" FOLDER)"
        if paths_overlap "$path" "$other"; then
            printf 'a pasta do armazenamento em nuvem %s (%s)' "$name" "$other"
            return 0
        fi
    done
    for name in $(share_names); do
        other="$(share_get "$name" DISK)/$(share_get "$name" DEST)"
        if paths_overlap "$path" "$other"; then
            printf 'a cópia da rede %s (%s)' "$name" "$other"
            return 0
        fi
    done
    return 1
}

share_login() {
    local name=$1 host=$2 account user domain password
    while true; do
        ui_input account "usuário da outra máquina (DOMÍNIO\\usuário, usuário ou, no Windows com conta Microsoft, o e-mail)" "" is_account
        ui_secret password "senha desse usuário (no Windows com conta Microsoft, a da conta, não o PIN)"
        user=$account
        domain=WORKGROUP
        if [[ $account == *\\* ]]; then
            domain=${account%%\\*}
            user=${account#*\\}
        elif [[ $account == *@* ]]; then
            domain=MicrosoftAccount
        fi
        rclone_section_write "rede-$name" "type = smb" "host = $host" "user = $user" "domain = $domain" \
            "pass = $(printf '%s' "$password" | rclone obscure -)"
        if ! share_responds "$host"; then
            ui_warn "$host não responde agora: o acesso será conferido na primeira cópia"
            return 0
        fi
        if rclone_run lsf "$(share_remote "$name")" --max-depth 1 --retries 1 --low-level-retries 1 >/dev/null 2>&1; then
            ui_ok "acesso a $(share_remote "$name") conferido"
            return 0
        fi
        ui_warn "não foi possível abrir $(share_get "$name" SHARE) em $host com esse usuário e senha (ou a pasta não existe)"
        ui_confirm "tentar outro usuário e senha?" y || return 0
    done
}

action_network_add() {
    ui_step "Adicionar cópia da rede"
    command -v rclone >/dev/null || ui_fail "instale o projeto rclone primeiro"
    local name host share folder disk dest days conflict
    ui_info "copia uma pasta compartilhada de outra máquina da rede (ex.: um disco compartilhado no Windows) para um disco desta"
    ui_info "a outra máquina é a fonte de verdade: o destino fica igual a ela, inclusive no que for apagado lá"
    while true; do
        ui_input name "nome da cópia (ex.: o nome da outra máquina)" "" is_folder
        [[ -f $SHARES/$name.env ]] || break
        ui_warn "já existe uma cópia chamada $name"
    done
    ui_input host "endereço da outra máquina na rede local (IP ou nome)" "" is_host
    share_responds "$host" || ui_warn "$host não respondeu na porta 445 agora (desligada ou sem compartilhamento): dá para seguir mesmo assim"
    ui_input share "nome do compartilhamento" "" is_label
    ui_input folder "pasta dentro do compartilhamento (/ para ele inteiro)" "/" is_relpath
    pick_data_disk disk "Em qual disco guardar a cópia de $host?" "$(env_get SOURCE)" "$(env_get BACKUP_MOUNT)"
    while true; do
        ui_input dest "pasta dentro de $disk (nunca a raiz do disco)" "$name" is_relpath
        if [[ -z $dest ]]; then
            ui_warn "escolha uma pasta, não a raiz do disco"
        elif conflict="$(dest_conflict "$disk/$dest")"; then
            ui_warn "$disk/$dest se sobrepõe a $conflict"
        else
            break
        fi
    done
    if [[ -n $(find "$disk/$dest" -type f -print -quit 2>/dev/null) ]]; then
        ui_warn "$disk/$dest já tem arquivos: o que não existir em $host/$share${folder:+/$folder} será apagado na primeira cópia"
        [[ -n $(env_get BACKUP_MOUNT) && $disk == "$(env_get SOURCE)" ]] \
            && ui_info "o que for apagado fica $(env_get KEEP_DAYS 30) dias em $(env_get BACKUP_MOUNT)/versoes"
        ui_confirm "continuar?" n || { ui_info "cancelado"; return 0; }
    fi
    ui_input days "avisar no Discord depois de quantos dias sem cópia" "7" is_number
    mkdir -p "$SHARES"
    chmod 700 "$DATA"
    share_set "$name" HOST "$host"
    share_set "$name" SHARE "$share"
    share_set "$name" FOLDER "$folder"
    share_set "$name" DISK "$disk"
    share_set "$name" DEST "$dest"
    share_set "$name" ALERT_DAYS "$days"
    share_set "$name" LAST_OK "$(date +%s)"
    share_set "$name" LAST_DONE ""
    share_set "$name" FORCE no
    share_login "$name" "$host"
    write_units
    network_schedule
    systemctl --user start --no-block "$UNIT_PREFIX-network.service"
    ui_ok "$name: $host/$share${folder:+/$folder} ➡️ $disk/$dest, uma vez por dia"
    ui_info "a primeira cópia começou em segundo plano (ou começa quando $host responder); acompanhe em \"Ver as últimas execuções\""
}

action_network_login() {
    ui_step "Reconectar a uma cópia da rede"
    local names=() choice name
    mapfile -t names < <(share_names)
    ((${#names[@]})) || ui_fail "nenhuma cópia da rede cadastrada"
    ui_menu choice "Qual cópia reconectar?" "${names[@]}"
    name=${names[choice]}
    share_login "$name" "$(share_get "$name" HOST)"
    write_units
    network_schedule
    systemctl --user start --no-block "$UNIT_PREFIX-network.service"
    ui_ok "$name: login trocado; a próxima cópia usa o usuário e a senha novos"
}

action_network_remove() {
    ui_step "Remover cópia da rede"
    local names=() chosen=() i
    mapfile -t names < <(share_names)
    ((${#names[@]})) || { ui_info "nenhuma cópia da rede cadastrada"; return; }
    ui_checklist chosen "Quais cópias remover? (os arquivos não são apagados em lugar nenhum)" --all "${names[@]}"
    for i in "${chosen[@]}"; do
        rm -f "$SHARES/${names[i]}.env"
        rclone_section_remove "rede-${names[i]}"
        ui_ok "${names[i]} removida (a cópia no disco fica como está)"
    done
    network_schedule
}

action_network_now() {
    ui_step "Backup: rede ➡️ local (agora)"
    network_force ""
    ui_ok "rodada iniciada em segundo plano (máquinas que não responderem ficam de fora)"
    ui_info "acompanhe em \"Ver as últimas execuções\" ou com: journalctl --user -fu $UNIT_PREFIX-network"
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
        cloud_now
        ui_ok "primeira cópia começou em segundo plano (acompanhe em \"Ver as últimas execuções\")"
    else
        systemctl --user stop "$UNIT_PREFIX-import-$name.timer" 2>/dev/null || true
        systemd-run --user --quiet --collect --unit "$UNIT_PREFIX-import-$name" \
            --on-calendar "$(date -d "@$at" '+%F %T')" --setenv ASTROVERSO_PLAIN=1 "$PWD/run.sh" tick
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
    pick_data_disk disk "Em qual disco guardar a cópia de $(provider_describe)?" "$(env_get SOURCE)" "$(env_get BACKUP_MOUNT)"
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
    ui_warn "de um lado vai para o outro (de 2 em 2 horas, das 08:00 às 20:00, e às 03:00)"
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
    local name at failures
    for name in $(target_names); do
        if [[ $(target_get "$name" IMPORT_DONE) == yes ]]; then
            failures="$(target_get "$name" FAILURES)"
            ui_ok "$name: $(target_get "$name" DISK)/$(target_get "$name" FOLDER) ↔ nuvem"
            if [[ $(target_get "$name" TOO_MANY_DELETES) == yes ]]; then
                ui_warn "$name: sincronização parada: mais de 5% dos arquivos seriam apagados (libere em \"Sincronizar agora\")"
            elif ((${failures:-0} >= 3)); then
                ui_warn "$name: a sincronização falhou $failures vezes seguidas (veja as mensagens abaixo)"
            elif [[ $(target_get "$name" BISYNC_READY) != yes ]]; then
                ui_info "$name: a próxima sincronização junta os dois lados, sem apagar nada"
            else
                ui_ok "$name: sincronização em dia"
            fi
        else
            at="$(target_get "$name" IMPORT_AT)"
            [[ $at == manual ]] && at="aguardando \"Sincronizar agora\"" || at="a partir de $(date -d "@$at" '+%d/%m %H:%M')"
            ui_info "$name: primeira cópia pendente, $at"
        fi
    done
    [[ -n $(target_names) ]] || ui_info "nenhum cadastrado"
    ui_step "Cópias da rede"
    local last
    for name in $(share_names); do
        last="$(share_get "$name" LAST_OK)"
        ui_ok "$name: $(share_get "$name" HOST)/$(share_get "$name" SHARE) ➡️ $(share_get "$name" DISK)/$(share_get "$name" DEST)"
        if [[ -n $(share_get "$name" LAST_DONE) ]]; then
            ui_info "$name: última cópia em $(date -d "@$last" '+%d/%m %H:%M')"
        else
            ui_info "$name: primeira cópia pendente (espera $(share_get "$name" HOST) responder)"
        fi
    done
    [[ -n $(share_names) ]] || ui_info "nenhuma cadastrada"
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
    cloud_now
    ui_ok "rodada iniciada em segundo plano (sincronização nos dois sentidos ou primeira cópia pendente)"
    ui_info "acompanhe em \"Ver as últimas execuções\" ou com: journalctl --user -fu $UNIT_PREFIX-tick"
}

cmd_install() {
    state_setup
    configure

    ui_step "Host"
    install_rclone
    write_units

    ui_step "Disco de backup"
    backup_disk

    ui_step "Armazenamentos em nuvem"
    if [[ -n $(target_names) ]]; then
        local name
        for name in $(target_names); do
            ui_ok "$name ↔ $(target_get "$name" DISK)/$(target_get "$name" FOLDER), sincronizados nos dois sentidos"
        done
    elif [[ -z $(disk_mounts) ]]; then
        ui_warn "nenhum disco da máquina: a cópia da nuvem precisa de um disco para ficar"
        ui_info "cadastre um em Gerenciar Astroverso → Administração → Discos da máquina e reinstale o Astroverso"
    elif ui_confirm "adicionar um armazenamento em nuvem agora?" y; then
        action_add
    else
        ui_info "adicione depois em Gerenciar Astroverso → rclone"
    fi

    ui_step "Cópias da rede"
    if [[ -n $(share_names) ]]; then
        for name in $(share_names); do
            ui_ok "$name: $(share_get "$name" HOST)/$(share_get "$name" SHARE) ➡️ $(share_get "$name" DISK)/$(share_get "$name" DEST)"
        done
    else
        ui_info "nenhuma: para copiar uma pasta compartilhada de outra máquina, use \"Adicionar cópia da rede\" em Gerenciar Astroverso → rclone"
    fi

    ui_step "Backup das configurações"
    config_backup_setup

    ui_step "Agendamentos"
    schedules
    if ! podman container exists astroverso-discord 2>/dev/null; then
        ui_info "para receber avisos com botões quando algo der errado, instale também o projeto discord"
    fi
}

config_backup_setup() {
    local dest default="" name password days disk
    name="$(target_names | head -1)"
    if [[ -n $name ]]; then
        default="$(target_get "$name" DISK)/$(target_get "$name" FOLDER)/Astroverso/Configurações"
    else
        disk="$(env_get SOURCE)"
        [[ -n $disk ]] || disk="$(disk_mounts | awk 'NR == 1 { print $1 }')"
        [[ -z $disk ]] || default="$disk/Astroverso/Configurações"
    fi
    default="$(env_get CONFIG_BACKUP "$default")"
    if [[ -z $default ]]; then
        ui_warn "nenhum disco da máquina: o backup das configurações fica desligado"
        ui_info "cadastre um em Gerenciar Astroverso → Administração → Discos da máquina e reinstale o Astroverso"
        sed -i '/^CONFIG_BACKUP=/d;/^CONFIG_KEEP_DAYS=/d' "$ENV_FILE"
        printf "CONFIG_BACKUP=''\nCONFIG_KEEP_DAYS='90'\n" >> "$ENV_FILE"
        return 0
    fi
    if $RECONFIGURE || ! grep -q '^CONFIG_BACKUP=' "$ENV_FILE" || [[ -z $(env_get CONFIG_BACKUP) ]]; then
        ui_info "toda noite, à 01:00, a configuração de cada serviço vira um arquivo criptografado nesta pasta (uma subpasta por serviço)"
        while true; do
            ui_input dest "pasta do backup das configurações" "$default" is_path
            mkdir -p "$dest" 2>/dev/null && [[ -w $dest ]] && break
            ui_warn "não foi possível gravar em $dest: escolha outra pasta"
        done
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
        network-now)    action_network_now ;;
        network-add)    action_network_add ;;
        network-login)  action_network_login ;;
        network-remove) action_network_remove ;;
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
    for unit in tick local config network; do
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

    work="$(mktemp -d -p /var/tmp astroverso-restore.XXXXXX)"
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
    if ! ASTROVERSO_LOCKED=1 ./run.sh config antes-da-restauracao 7>&- 8>&-; then
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
            cp "$work/extract/host/host.env" "$ASTROVERSO_HOME/host.env" && restored+=(host) || failed+=(host)
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
    local unit
    ui_step "Remoção"
    stop_runs
    systemctl --user stop "$UNIT_PREFIX-import-*.timer" 2>/dev/null || true
    for unit in tick local config network; do
        systemctl --user disable -q --now "$UNIT_PREFIX-$unit.timer" 2>/dev/null || true
        rm -f "$UNIT_DIR/$UNIT_PREFIX-$unit.timer" "$UNIT_DIR/$UNIT_PREFIX-$unit.service"
    done
    systemctl --user daemon-reload
    ui_ok "agendamentos removidos"
    rm -rf "${XDG_CACHE_HOME:-$HOME/.cache}/rclone/bisync"
    state_purge
    ui_info "mantidos: os arquivos nos discos e na nuvem, o backup das configurações e o pacote do rclone"
}

case "${1:-}" in
    describe) cmd_describe ;;
    status)   cmd_status ;;
    actions)  cmd_actions ;;
    global-actions) cmd_global_actions ;;
    remote-actions) cmd_remote_actions ;;
    help)     cmd_help ;;
    remote)   shift; cmd_remote "$@" ;;
    action)   shift; cmd_action "$@" ;;
    install)  cmd_install ;;
    remove)   cmd_remove ;;
    restore)  shift; cmd_restore "$1" ;;
    *)        ui_fail "uso: $0 describe | status | actions | global-actions | remote-actions | help | remote <id> [argumento] | action <id> | install | remove | restore <pasta>" ;;
esac
