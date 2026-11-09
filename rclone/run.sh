#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"

ASTRO_PROJECT=rclone
source ../lib/ui.sh
source ../lib/env.sh
source common.sh

MARGIN=120
MAX_DELETE=1000
RCLONE_OPTIONS=(--retries 3 --low-level-retries 10 --stats 5m --stats-one-line --stats-log-level NOTICE --log-level NOTICE)

lock() {
    [[ ${ASTRO_LOCKED:-} == 1 ]] && return 0
    exec 9>"${2:-$LOCK}"
    if [[ $1 == wait ]]; then
        flock 9
    elif ! flock -n 9; then
        ui_info "outra rodada ainda em andamento, esta fica para a próxima"
        exit 0
    fi
}

disk_ready() {
    if mountpoint -q "$1"; then
        return 0
    fi
    ui_warn "$1 não está montado: nada é copiado nem apagado"
    return 1
}

target_paths() {
    local name=$1
    DISK="$(target_get "$name" DISK)"
    LOCAL="$DISK/$(target_get "$name" FOLDER)"
    REMOTE="$name:$(target_get "$name" REMOTE_PATH)"
    provider_load "$(target_get "$name" PROVIDER)"
    mapfile -t PROVIDER_OPTIONS < <(provider_options)
}

import_target() {
    local name=$1 at
    at="$(target_get "$name" IMPORT_AT)"
    if [[ $at == manual ]]; then
        ui_info "$name: primeira cópia aguardando \"Sincronizar agora\""
        return 0
    fi
    if (($(date +%s) < at)); then
        ui_info "$name: primeira cópia agendada para $(date -d "@$at" '+%d/%m %H:%M')"
        return 0
    fi
    mkdir -p "$LOCAL"
    ui_step "$name: primeira cópia $REMOTE → $LOCAL (continua de onde parou)"
    if ! rclone_run copy "$REMOTE" "$LOCAL" "${RCLONE_OPTIONS[@]}" "${PROVIDER_OPTIONS[@]}"; then
        ui_error "$name: primeira cópia interrompida, a próxima rodada continua"
        return 1
    fi
    target_set "$name" IMPORT_DONE yes
    target_set "$name" LAST_UPLOAD "$(date +%s)"
    ui_ok "$name: primeira cópia concluída; o envio a cada 15 minutos e o espelho noturno estão ativos"
}

upload_target() {
    local name=$1 list start since
    start="$(date +%s)"
    since="$(target_get "$name" LAST_UPLOAD)"
    since="$(( ${since:-$((start - 1200))} - MARGIN ))"
    list="$(mktemp)"
    find "$LOCAL" -type f -newerct "@$since" ! -name '*.partial' -printf '%P\n' > "$list"
    if [[ ! -s $list ]]; then
        rm -f "$list"
        target_set "$name" LAST_UPLOAD "$start"
        return 0
    fi
    ui_step "$name: enviando $(wc -l < "$list") arquivo(s) novo(s) ou alterado(s)"
    if ! rclone_run copy "$LOCAL" "$REMOTE" --files-from-raw "$list" --no-traverse \
            "${RCLONE_OPTIONS[@]}" "${PROVIDER_OPTIONS[@]}"; then
        rm -f "$list"
        ui_error "$name: envio falhou, a próxima rodada tenta de novo"
        return 1
    fi
    rm -f "$list"
    target_set "$name" LAST_UPLOAD "$start"
    ui_ok "$name: envio concluído"
}

mirror_target() {
    local name=$1
    ui_step "$name: espelho $LOCAL → $REMOTE (com exclusões, no máximo $MAX_DELETE)"
    if ! rclone_run sync "$LOCAL" "$REMOTE" --max-delete "$MAX_DELETE" --exclude '*.partial' \
            "${RCLONE_OPTIONS[@]}" "${PROVIDER_OPTIONS[@]}"; then
        ui_error "$name: espelho falhou (se passou de $MAX_DELETE exclusões, confira antes de rodar de novo)"
        return 1
    fi
    ui_ok "$name: espelho concluído"
}

run_targets() {
    local mode=$1 name failed=0
    for name in $(target_names); do
        (
            target_paths "$name"
            disk_ready "$DISK" || exit 1
            if [[ $(target_get "$name" IMPORT_DONE) != yes ]]; then
                [[ $mode == tick ]] || { ui_info "$name: espelho só depois da primeira cópia"; exit 0; }
                import_target "$name"
            elif [[ $mode == tick ]]; then
                upload_target "$name"
            else
                mirror_target "$name"
            fi
        ) || failed=1
    done
    return "$failed"
}

local_mirror() {
    local source backup days
    source="$(env_get SOURCE)"
    backup="$(env_get BACKUP_MOUNT)"
    days="$(env_get KEEP_DAYS 30)"
    if [[ -z $source || -z $backup ]]; then
        ui_info "nenhum disco de backup configurado"
        return 0
    fi
    disk_ready "$source" || return 1
    disk_ready "$backup" || return 1
    ui_step "espelho $source → $backup/atual (alterados e apagados vão para $backup/versoes/$(date +%F))"
    if ! podman unshare rclone --config /dev/null sync "$source/" "$backup/atual" --metadata --links \
            --backup-dir "$backup/versoes/$(date +%F)" --exclude '/lost+found/**' "${RCLONE_OPTIONS[@]}"; then
        ui_error "espelho local falhou"
        return 1
    fi
    podman unshare find "$backup/versoes" -mindepth 1 -maxdepth 1 -type d -mtime "+$days" -exec rm -rf {} +
    ui_ok "espelho local concluído; versões com mais de $days dias apagadas"
}

regex_escape() {
    sed -e 's/[][\\.*^$]/\\&/g' <<< "$1"
}

service_parts() {
    local project="../$1/project.sh" output kind rest
    PART_EXCLUDES=()
    PART_ADDS=()
    PART_INCLUDES=()
    [[ -f $project ]] && grep -q '^    backup)' "$project" || return 0
    if ! output="$("$project" backup)"; then
        ui_error "$1: falha ao preparar o backup (dump do banco ou cópia consistente)"
        return 1
    fi
    while read -r kind rest; do
        case $kind in
            exclude) PART_EXCLUDES+=("--exclude=${rest#/}") ;;
            add)     PART_ADDS+=("${rest#/}") ;;
            include) PART_INCLUDES+=("$rest") ;;
        esac
    done <<< "$output"
}

tar_ok() {
    local rc=0
    "$@" || rc=$?
    ((rc <= 1))
}

service_archive() {
    local service=$1 archive=$2 source=$3 entry name path runner=() owner=() target=$1
    [[ -f /$source ]] && target="$service/${source##*/}"
    local transform="s|^$(regex_escape "$source")|$target|"
    tar_ok podman unshare tar -cf "$archive" -C / "${PART_EXCLUDES[@]}" --transform="$transform" "$source" || return 1
    if ((${#PART_ADDS[@]})); then
        tar_ok podman unshare tar -rf "$archive" -C / --transform="$transform" "${PART_ADDS[@]}" || return 1
    fi
    for entry in "${PART_INCLUDES[@]}"; do
        name="${entry%% *}"
        path="${entry#* }"
        path="${path#/}"
        runner=()
        owner=(--owner=0 --group=0 --numeric-owner)
        if [[ /$path == "$HOME"/* ]]; then
            runner=(podman unshare)
            owner=()
        fi
        tar_ok "${runner[@]}" tar -rf "$archive" -C / "${owner[@]}" "${PART_EXCLUDES[@]}" \
            --transform="s|^$(regex_escape "$path")|$service/$name|" "$path" || return 1
    done
    zstd -q --rm -f "$archive" -o "$archive.zst"
}

service_publish() {
    local service=$1 work=$2 dest=$3 file
    file="$service.tar.zst.gpg"
    gpg --batch --yes --quiet --homedir "$work/gnupg" --pinentry-mode loopback --passphrase-file "$CONFIG_KEY" \
        --symmetric --cipher-algo AES256 -o "$work/$file" "$work/$service.tar.zst" || return 1
    mkdir -p "$dest/$service"
    cp "$work/$file" "$dest/$service/.$file.partial"
    mv "$dest/$service/.$file.partial" "$dest/$service/$file"
}

config_prune() {
    local dest=$1 days=$2 limit name
    limit="$(date -d "-$days days" +%F)"
    while read -r name; do
        [[ -n $name && ${name:0:10} < $limit ]] || continue
        rm -rf -- "${dest:?}/$name"
        ui_ok "versão $name apagada (mais de $days dias)"
    done < <(config_versions "$dest")
}

config_backup() {
    local dest work disk version label=${1:-}
    dest="$(env_get CONFIG_BACKUP)"
    if [[ -z $dest ]]; then
        ui_info "backup das configurações não configurado"
        return 0
    fi
    if [[ ! -s $CONFIG_KEY ]]; then
        ui_error "senha do backup das configurações não encontrada em $CONFIG_KEY: rode a instalação do rclone"
        return 1
    fi
    disk="$(cut -d/ -f1-3 <<< "$dest")"
    if [[ $disk == /srv/* ]]; then
        disk_ready "$disk" || return 1
    fi
    work="$(mktemp -d -p /var/tmp astro-config.XXXXXX)"
    mkdir -p "$work/gnupg"
    chmod 700 "$work/gnupg"
    version="$(date +%F_%H%M%S)${label:+_$label}"
    ui_step "backup das configurações → $dest/$version/<serviço>/<serviço>.tar.zst.gpg"
    local dir service saved=() failed=0
    for dir in "$ASTRO_HOME"/*/; do
        service="$(basename "$dir")"
        if service_parts "$service" \
                && service_archive "$service" "$work/$service.tar" "${ASTRO_HOME#/}/$service" \
                && service_publish "$service" "$work" "$dest/$version"; then
            saved+=("$service")
        else
            ui_error "$service: backup das configurações falhou"
            failed=1
        fi
    done
    if [[ -f $ASTRO_HOME/host.env ]]; then
        PART_EXCLUDES=()
        PART_ADDS=()
        PART_INCLUDES=()
        if service_archive host "$work/host.tar" "${ASTRO_HOME#/}/host.env" && service_publish host "$work" "$dest/$version"; then
            saved+=(host)
        else
            ui_error "host: backup das configurações falhou"
            failed=1
        fi
    fi
    podman unshare rm -rf "$work"
    ((${#saved[@]})) && ui_ok "versão $version salva e criptografada: ${saved[*]}"
    ((failed)) || config_prune "$dest" "$(env_get CONFIG_KEEP_DAYS 90)"
    return "$failed"
}

case "${1:-}" in
    tick)    lock skip; run_targets tick ;;
    nightly) lock wait; run_targets nightly ;;
    local)   lock wait; local_mirror ;;
    config)  lock wait "$CONFIG_LOCK"; config_backup "${2:-}" ;;
    *)       ui_fail "uso: $0 tick | nightly | local | config [rótulo]" ;;
esac
