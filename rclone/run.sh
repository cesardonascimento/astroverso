#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"

ASTRO_PROJECT=rclone
source ../lib/ui.sh
source ../lib/env.sh
source common.sh

LOCK="${XDG_RUNTIME_DIR:-/tmp}/astro-rclone.lock"
MARGIN=120
MAX_DELETE=1000
RCLONE_OPTIONS=(--retries 3 --low-level-retries 10 --stats 5m --stats-one-line --stats-log-level NOTICE --log-level NOTICE)

lock() {
    exec 9>"$LOCK"
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

config_parts() {
    local project kind path output
    CONFIG_EXCLUDES=()
    CONFIG_INCLUDES=()
    CONFIG_ADDS=()
    for project in ../*/project.sh; do
        grep -q '^    backup)' "$project" || continue
        if ! output="$("$project" backup)"; then
            ui_error "falha ao preparar o backup de $(basename "$(dirname "$project")")"
            return 1
        fi
        while read -r kind path; do
            case $kind in
                exclude) CONFIG_EXCLUDES+=("--exclude=${path#/}") ;;
                include) CONFIG_INCLUDES+=("${path#/}") ;;
                add)     CONFIG_ADDS+=("${path#/}") ;;
            esac
        done <<< "$output"
    done
}

config_tar() {
    local archive=$1 rc=0
    shift
    "$@" tar -cf "$archive" -C / "${CONFIG_EXCLUDES[@]}" "${HOME#/}/.astro" "${CONFIG_INCLUDES[@]}" || rc=$?
    if ((rc == 0 || rc == 1)) && ((${#CONFIG_ADDS[@]})); then
        "$@" tar -rf "$archive" -C / "${CONFIG_ADDS[@]}" || rc=$?
    fi
    ((rc <= 1)) || return 1
    zstd -q --rm -f "$archive" -o "$archive.zst"
}

config_backup() {
    local dest work home user disk
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
    config_parts || return 1
    work="$(mktemp -d -p /var/tmp astro-config.XXXXXX)"
    ui_step "backup das configurações → $dest/astro-config.tar.gpg"
    if ! config_tar "$work/$USER.tar" podman unshare; then
        ui_error "falha ao empacotar $HOME/.astro"
        podman unshare rm -rf "$work"
        return 1
    fi
    for home in /home/*/; do
        home="${home%/}"
        user="${home##*/}"
        [[ $home != "$HOME" && -r $home/.astro ]] || continue
        if ! tar --zstd -cf "$work/$user.tar.zst" -C / "${home#/}/.astro"; then
            ui_warn "não foi possível ler tudo em $home/.astro"
        fi
    done
    (cd "$work" && tar -cf astro-config.tar ./*.tar.zst)
    mkdir -p "$work/gnupg" "$dest"
    chmod 700 "$work/gnupg"
    if ! gpg --batch --yes --quiet --homedir "$work/gnupg" --pinentry-mode loopback --passphrase-file "$CONFIG_KEY" \
            --symmetric --cipher-algo AES256 -o "$work/astro-config.tar.gpg" "$work/astro-config.tar"; then
        ui_error "falha ao criptografar o backup das configurações"
        podman unshare rm -rf "$work"
        return 1
    fi
    cp "$work/astro-config.tar.gpg" "$dest/.astro-config.tar.gpg.partial"
    mv "$dest/.astro-config.tar.gpg.partial" "$dest/astro-config.tar.gpg"
    ui_ok "configurações salvas ($(du -h "$dest/astro-config.tar.gpg" | cut -f1), criptografadas): $(cd "$work" && ls ./*.tar.zst | sed 's|^\./||; s|\.tar\.zst$||' | paste -sd' ')"
    podman unshare rm -rf "$work"
}

case "${1:-}" in
    tick)    lock skip; run_targets tick ;;
    nightly) lock wait; run_targets nightly ;;
    local)   lock wait; local_mirror ;;
    config)  lock wait; config_backup ;;
    *)       ui_fail "uso: $0 tick | nightly | local | config" ;;
esac
