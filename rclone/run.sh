#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"

ASTRO_PROJECT=rclone
source ../lib/ui.sh
source ../lib/env.sh
source ../lib/notify.sh
source common.sh

CONFIG_KEY="${ASTRO_BACKUP_KEY:-$CONFIG_KEY}"

MAX_DELETE=5
RCLONE_OPTIONS=(--retries 3 --low-level-retries 10 --stats 5m --stats-one-line --stats-log-level NOTICE --log-level NOTICE)

rclone_owner() {
    podman unshare rclone --config "$RCLONE_CONF" "$@"
}

duration() {
    if (($1 < 60)); then
        printf '%ss' "$1"
    else
        printf '%dmin %02ds' $(($1 / 60)) $(($1 % 60))
    fi
}

routine() {
    local title=$1 retry=$2 start log status summary
    shift 2
    if [[ -z ${INVOCATION_ID:-} ]]; then
        "$@"
        return
    fi
    start=$(date +%s)
    log="$(mktemp)"
    notify_info "▶️ $title começou"
    set +e
    (set -e; "$@") 2>&1 | tee "$log"
    status=${PIPESTATUS[0]}
    set -e
    if ((status == 0)); then
        summary="$(sed -n 's/^\[rclone\] *ok: //p' "$log" | tail -3 | paste -sd '|' | sed 's/|/; /g')"
        notify_info "✅ $title terminou em $(duration $(($(date +%s) - start)))${summary:+: $summary}"
    else
        summary="$(sed -n 's/^\[rclone\] *erro: //p' "$log" | tail -3 | paste -sd '|' | sed 's/|/; /g')"
        if [[ -n $retry ]]; then
            notify_send "❌ $title falhou${summary:+: $summary}" "Tentar de novo|$retry|"
        else
            notify_send "❌ $title falhou${summary:+: $summary}. Veja \"Ver as últimas execuções\" no assistente do rclone"
        fi
    fi
    rm -f "$log"
    return "$status"
}

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
        notify_resolved "disco-${1##*/}" "o disco $1 voltou a ser montado: as cópias seguem normalmente"
        return 0
    fi
    ui_warn "$1 não está montado: nada é copiado nem apagado"
    notify_problem "disco-${1##*/}" "o disco $1 não está montado: nada é copiado nem apagado até ele voltar"
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
    local log error start
    start=$(date +%s)
    if [[ $(target_get "$name" IMPORT_NOTIFIED) != yes ]]; then
        notify_info "▶️ primeira cópia do $name (nuvem → disco) começou"
        target_set "$name" IMPORT_NOTIFIED yes
    fi
    log="$(mktemp)"
    if ! rclone_owner copy "$REMOTE" "$LOCAL" "${RCLONE_OPTIONS[@]}" "${PROVIDER_OPTIONS[@]}" 2>&1 | tee "$log"; then
        error="$(sed 's/\x1b\[[0-9;]*m//g' "$log" | grep -oE '(Failed to copy|ERROR) *: .*' | tail -1)" || true
        rm -f "$log"
        ui_error "$name: primeira cópia interrompida, a próxima rodada continua"
        notify_problem "$name-importacao" "a primeira cópia do $name (nuvem → disco) parou com erro${error:+: $error}. A próxima rodada continua de onde parou" \
            "Tentar de novo|rclone:sync|"
        return 1
    fi
    rm -f "$log"
    target_set "$name" IMPORT_DONE yes
    target_set "$name" BISYNC_READY no
    rm -f "$(notify_flag "$name-importacao")"
    notify_info "✅ primeira cópia do $name terminou em $(duration $(($(date +%s) - start))); a sincronização nos dois sentidos começa na próxima rodada"
    ui_ok "$name: primeira cópia concluída; a sincronização nos dois sentidos está ativa"
}

bisync_target() {
    local name=$1 log failures options=()
    options=(--create-empty-src-dirs --conflict-resolve newer --conflict-loser num --resilient --recover
        --max-lock 2h --max-delete "$MAX_DELETE" --exclude '*.partial')
    if [[ $(target_get "$name" BISYNC_READY) != yes ]]; then
        ui_step "$name: primeira sincronização $LOCAL ↔ $REMOTE (junta os dois lados, sem apagar nada)"
        options+=(--resync --resync-mode newer)
    else
        ui_step "$name: sincronizando $LOCAL ↔ $REMOTE"
    fi
    if [[ $(target_get "$name" BISYNC_FORCE) == yes ]]; then
        ui_warn "$name: exclusões liberadas nesta rodada, sem o limite de $MAX_DELETE%"
        options+=(--force)
        target_set "$name" BISYNC_FORCE no
    fi
    log="$(mktemp)"
    if ! rclone_owner bisync "$LOCAL" "$REMOTE" "${options[@]}" "${RCLONE_OPTIONS[@]}" "${PROVIDER_OPTIONS[@]}" 2>&1 \
            | tee "$log"; then
        if grep -qi 'too many deletes' "$log"; then
            target_set "$name" TOO_MANY_DELETES yes
            ui_warn "$name: parou sem apagar nada: mais de $MAX_DELETE% dos arquivos seriam apagados"
            ui_warn "$name: para apagar mesmo assim, use \"Sincronizar agora\" no assistente"
            notify_problem "$name-exclusoes" "a sincronização do $name parou sem apagar nada: mais de $MAX_DELETE% dos arquivos seriam apagados. Se foi de propósito (ex.: pasta grande renomeada), libere as exclusões; se não, confira o que sumiu" \
                "Ver o que seria apagado|rclone:show-deletes|$name" "Liberar exclusões|rclone:allow-deletes|$name"
        else
            failures=$(( $(target_get "$name" FAILURES) + 1 ))
            target_set "$name" FAILURES "$failures"
            notify_problem "$name-falha" "a sincronização do $name falhou ($failures vez(es) seguida(s)). Veja \"Ver as últimas execuções\" no assistente do rclone" \
                "Tentar de novo|rclone:sync|"
        fi
        if grep -qiE 'must run --resync|cannot find prior' "$log"; then
            target_set "$name" BISYNC_READY no
            ui_warn "$name: o rclone perdeu o estado da sincronização; a próxima rodada junta os dois lados de novo"
            ui_warn "$name: nessa junção, arquivos apagados de um lado só voltam a aparecer"
            notify_problem "$name-estado" "o rclone perdeu o estado da sincronização do $name e vai juntar os dois lados de novo, sem apagar nada. Arquivos apagados de um lado só podem voltar a aparecer"
        fi
        rm -f "$log"
        ui_error "$name: sincronização falhou, a próxima rodada tenta de novo"
        return 1
    fi
    rm -f "$log"
    target_set "$name" BISYNC_READY yes
    target_set "$name" TOO_MANY_DELETES no
    target_set "$name" FAILURES 0
    notify_resolved "$name-exclusoes" "a sincronização do $name voltou a funcionar"
    notify_resolved "$name-falha" "a sincronização do $name voltou a funcionar"
    notify_resolved "$name-estado" "a sincronização do $name juntou os dois lados e voltou ao normal"
    ui_ok "$name: sincronização concluída"
}

preview_target() {
    local name=$1
    [[ -f $TARGETS/$name.env ]] || ui_fail "armazenamento desconhecido: $name"
    target_paths "$name"
    disk_ready "$DISK" || return 1
    [[ $(target_get "$name" BISYNC_READY) == yes ]] || ui_fail "$name ainda não tem uma sincronização completa para comparar"
    local log
    log="$(mktemp)"
    if ! rclone_owner bisync "$LOCAL" "$REMOTE" --dry-run --force --resilient --recover --max-lock 2h --exclude '*.partial' \
            --log-level NOTICE "${PROVIDER_OPTIONS[@]}" > "$log" 2>&1; then
        sed 's/\x1b\[[0-9;]*m//g' "$log" | grep -E 'ERROR|critical' | tail -5
        rm -f "$log"
        ui_error "o teste falhou"
        return 1
    fi
    sed 's/\x1b\[[0-9;]*m//g' "$log" | python3 -I -c '
import collections, re, sys
lado = {"Path1": "apagados no disco, seriam apagados na nuvem", "Path2": "apagados na nuvem, seriam apagados no disco"}
contagem = {k: collections.Counter() for k in lado}
for linha in sys.stdin:
    m = re.search(r"- (Path[12])\s+File was deleted\s+- (.+)$", linha.rstrip())
    if m:
        pasta = m.group(2).split("/")[0] if "/" in m.group(2) else "(raiz)"
        contagem[m.group(1)][pasta] += 1
for chave, titulo in lado.items():
    total = sum(contagem[chave].values())
    print(f"{titulo}: {total}")
    for pasta, n in contagem[chave].most_common(15):
        print(f"  {pasta}: {n}")
'
    rm -f "$log"
}

run_targets() {
    local mode=$1 name failed=0
    for name in $(target_names); do
        (
            target_paths "$name"
            disk_ready "$DISK" || exit 1
            if [[ $(target_get "$name" IMPORT_DONE) == yes ]]; then
                bisync_target "$name"
            elif [[ $mode == tick ]]; then
                import_target "$name"
            else
                ui_info "$name: sincronização só depois da primeira cópia"
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

local_run() {
    local failed=0
    if ! run_targets local; then
        failed=1
    fi
    if ! local_mirror; then
        failed=1
    fi
    return "$failed"
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
    dest="${ASTRO_BACKUP_DEST:-$(env_get CONFIG_BACKUP)}"
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
    if ((failed)); then
        ui_error "backup das configurações incompleto (salvos: ${saved[*]:-nenhum})"
        return 1
    fi
    config_prune "$dest" "$(env_get CONFIG_KEEP_DAYS 90)"
}

case "${1:-}" in
    tick)    lock skip; run_targets tick ;;
    local)   lock wait; routine "rodada das 03:00 (nuvem e espelho no disco de backup)" "" local_run ;;
    preview) lock wait; preview_target "${2:-}" ;;
    config)  lock wait "$CONFIG_LOCK"; routine "backup das configurações" rclone:backup-configs config_backup "${2:-}" ;;
    *)       ui_fail "uso: $0 tick | local | config [rótulo] | preview <armazenamento>" ;;
esac
