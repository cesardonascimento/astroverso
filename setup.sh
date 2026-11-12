#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"

ASTRO_PROJECT=astro
source lib/ui.sh
source lib/host.sh
source lib/env.sh
source lib/disk.sh

trap '_ui_cursor_show; echo; ui_warn "cancelado"; exit 130' INT

[[ -t 0 ]] || ui_fail "execute em um terminal interativo"

ORDER=(caddy adguard cockpit nextcloud mailserver arcade rclone discord)
IMPLODE_WORD=IMPLODIR
DONE_DIR="$ASTRO_HOME/.concluidas"

PROJECTS=()
for name in "${ORDER[@]}"; do
    [[ -x $name/project.sh ]] && PROJECTS+=("$name")
done
for file in */project.sh; do
    name="${file%/*}"
    [[ -x $file && " ${ORDER[*]} " != *" $name "* ]] && PROJECTS+=("$name")
done
((${#PROJECTS[@]})) || ui_fail "nenhum projeto encontrado"

project() {
    local name=$1
    shift
    "./$name/project.sh" "$@"
}

installed_any() {
    local name
    for name in "${PROJECTS[@]}"; do
        project "$name" status && return 0
    done
    return 1
}

join() {
    local IFS=$'\x1f' text
    text="$*"
    printf '%s' "${text//$'\x1f'/, }"
}

summary() {
    ui_step "Resumo"
    [[ -z ${skipped[*]:-} ]] || ui_info "pulados (já concluídos): $(join "${skipped[@]}")"
    ((${#succeeded[@]} == 0)) || ui_ok "concluído: $(join "${succeeded[@]}")"
    ((${#failed[@]} == 0)) || ui_error "falhou: $(join "${failed[@]}")"
    ((${#failed[@]} == 0))
}

step_label() {
    case $1 in
        maquina) printf 'Máquina' ;;
        discos)  printf 'Discos da máquina' ;;
        *)       printf '%s' "$1" ;;
    esac
}

step_done() {
    [[ -f $DONE_DIR/$1 ]] || return 1
    case $1 in
        maquina|discos) return 0 ;;
        *)              project "$1" status ;;
    esac
}

step_date() {
    date -d "@$(stat -c %Y "$DONE_DIR/$1")" '+%d/%m %H:%M'
}

step_machine() {
    if $1; then
        ui_step "Sistema"
        host_upgrade
    fi
    ui_step "Máquina"
    host_base
}

run_step() {
    local step=$1 status
    shift
    if step_done "$step" && [[ $redo != *" $step "* ]]; then
        ui_step "$(step_label "$step")"
        ui_info "concluída em $(step_date "$step"), pulada"
        skipped+=("$(step_label "$step")")
        return 0
    fi
    rm -f "$DONE_DIR/$step"
    set +e
    (set -e; "$@")
    status=$?
    set -e
    if ((status == 0)); then
        mkdir -p "$DONE_DIR"
        chmod 700 "$ASTRO_HOME" "$DONE_DIR"
        touch "$DONE_DIR/$step"
        succeeded+=("$(step_label "$step")")
    else
        failed+=("$(step_label "$step")")
    fi
}

install_astro() {
    local name step label first=true redo=" " i chosen=() pending=() done_steps=() labels=() failed=() succeeded=() skipped=()
    for step in maquina discos "${PROJECTS[@]}"; do
        if ! step_done "$step"; then
            pending+=("$(step_label "$step")")
            continue
        fi
        done_steps+=("$step")
        label="$(step_label "$step")"
        labels+=("$(printf '%s%*s concluída em %s' "$label" $((18 - ${#label})) '' "$(step_date "$step")")")
    done
    if ((${#done_steps[@]})); then
        ((${#pending[@]} == 0)) || ui_info "pendentes (sempre rodam): $(join "${pending[@]}")"
        ui_checklist chosen "Quais etapas concluídas reinstalar? (as não concluídas sempre rodam)" --all "${labels[@]}"
        for i in "${chosen[@]}"; do
            redo+="${done_steps[i]} "
        done
    fi
    if [[ -f $DONE_DIR/maquina ]] || installed_any; then
        first=false
    fi
    run_step maquina step_machine "$first"
    run_step discos disk_manage
    for name in "${PROJECTS[@]}"; do
        run_step "$name" project "$name" install
    done
    summary
}

project_actions() {
    local name=$1 index id label ids=() labels=()
    while IFS='|' read -r id label; do
        ids+=("$id")
        labels+=("$label")
    done < <(project "$name" actions)
    ui_menu index "O que fazer no $name?" "${labels[@]}" "Voltar"
    ((index < ${#ids[@]})) || return 0
    project "$name" action "${ids[index]}"
}

global_actions() {
    local name id label
    GLOBAL_IDS=()
    GLOBAL_LABELS=()
    for name in "${PROJECTS[@]}"; do
        grep -q '^    global-actions)' "$name/project.sh" || continue
        project "$name" status || continue
        while IFS='|' read -r id label; do
            [[ -n $id ]] || continue
            GLOBAL_IDS+=("$name $id")
            GLOBAL_LABELS+=("$label")
        done < <(project "$name" global-actions)
    done
}

backup_default() {
    local mount
    mount="$(disk_mounts | awk 'NR == 1 { print $1 }')"
    if [[ -n $mount ]]; then
        printf '%s/Astro/Configurações' "$mount"
    else
        printf '%s/astro-backup' "$HOME"
    fi
}

implode_backup() {
    local dest key password status=0
    ui_step "Backup antes de implodir"
    command -v zstd >/dev/null && command -v gpg >/dev/null || ui_fail "o backup precisa do zstd e do gpg: sudo dnf install -y zstd gnupg2"
    dest="$(env_get CONFIG_BACKUP "" "$ASTRO_HOME/rclone/.env")"
    key="$ASTRO_HOME/rclone/data/config-backup.key"
    if [[ -n $dest && -s $key ]]; then
        ui_info "usando a pasta e a senha do backup das configurações do rclone: $dest"
        ./rclone/run.sh config antes-de-implodir
        return
    fi
    ui_info "o backup das configurações do rclone não está ligado: escolha uma pasta e uma senha para este backup"
    ui_info "depois de reinstalar, use essa pasta como \"pasta do backup das configurações\" do rclone para restaurar"
    while true; do
        ui_input dest "pasta do backup" "$(backup_default)" is_path
        if [[ $dest == "$ASTRO_HOME" || $dest == "$ASTRO_HOME"/* ]]; then
            ui_warn "$ASTRO_HOME é apagada na implosão: escolha outra pasta"
        elif mkdir -p "$dest" 2>/dev/null && [[ -w $dest ]]; then
            break
        else
            ui_warn "não foi possível gravar em $dest: escolha outra pasta"
        fi
    done
    ui_warn "guarde esta senha fora da máquina (ex.: gerenciador de senhas): sem ela, o backup não abre"
    ui_secret password "senha do backup"
    key="$(mktemp -p /var/tmp astro-key.XXXXXX)"
    printf '%s' "$password" > "$key"
    ASTRO_BACKUP_DEST="$dest" ASTRO_BACKUP_KEY="$key" ./rclone/run.sh config antes-de-implodir || status=$?
    rm -f "$key"
    return "$status"
}

implode() {
    local answer games i name failed=() succeeded=()
    games="$(env_get GAMES_USER "" "$ASTRO_HOME/arcade/.env")"
    ui_step "Implodir Astro"
    ui_warn "isto desfaz tudo o que o Astro criou nesta máquina:"
    ui_info "  containers, imagens, serviços e a configuração de todos os projetos ($ASTRO_HOME)"
    [[ -z $games ]] || ui_info "  o usuário de jogos $games, com a home inteira (saves, states, BIOS e núcleos)"
    ui_info "  a pasta local de arquivos do Nextcloud"
    ui_info "  as montagens dos discos em $DISK_ROOT e o TPM dos discos criptografados"
    ui_info "  os ajustes da máquina: suspensão, firewall, DNS, portas, rede anunciada no Tailscale e início no boot"
    ui_info "ficam: os pacotes instalados (sistema, Tailscale, driver da NVIDIA...), os dados dos discos e o SSH"
    ui_info "antes de tudo, as configurações vão para um backup criptografado"
    answer="$(_ui_ask "para confirmar, digite $IMPLODE_WORD: ")"
    if [[ $answer != "$IMPLODE_WORD" ]]; then
        ui_warn "cancelado, nada mudou"
        return 0
    fi
    IMPLODED=true

    if ! implode_backup; then
        ui_error "o backup falhou: nada foi desfeito"
        return 1
    fi
    rm -rf "$DONE_DIR"

    for ((i = ${#PROJECTS[@]} - 1; i >= 0; i--)); do
        name=${PROJECTS[i]}
        if project "$name" remove; then
            succeeded+=("$name")
        else
            failed+=("$name")
        fi
    done

    ui_step "Discos da máquina"
    disk_release_all

    ui_step "Máquina"
    host_undo
    if podman network exists astro_default 2>/dev/null; then
        podman network rm -f astro_default >/dev/null
        ui_ok "rede astro_default apagada"
    fi
    podman image prune -f >/dev/null 2>&1 || true
    rm -rf "${XDG_STATE_HOME:-$HOME/.local/state}/astro"
    if ((${#failed[@]})); then
        ui_warn "$ASTRO_HOME mantida, porque algum projeto falhou: corrija e rode a implosão de novo"
    elif [[ -e $ASTRO_HOME ]]; then
        podman unshare rm -rf "$ASTRO_HOME"
        ui_ok "$ASTRO_HOME apagada"
    fi
    summary
    ui_info "o repositório continua aqui: para instalar de novo, rode o setup.sh"
}

administration() {
    local index globals name id
    while true; do
        global_actions
        globals=${#GLOBAL_IDS[@]}
        ui_menu index "Administração" "Discos da máquina" "${GLOBAL_LABELS[@]}" "Implodir Astro" "Voltar"
        if ((index == 0)); then
            disk_manage || true
        elif ((index <= globals)); then
            read -r name id <<< "${GLOBAL_IDS[index - 1]}"
            project "$name" action "$id" || true
        elif ((index == globals + 1)); then
            implode || true
            $IMPLODED && return 0
        else
            return 0
        fi
        echo
    done
}

manage() {
    local name index candidates labels
    while true; do
        candidates=()
        labels=()
        for name in "${PROJECTS[@]}"; do
            project "$name" status || continue
            [[ -n "$(project "$name" actions 2>/dev/null)" ]] || continue
            candidates+=("$name")
            labels+=("$(printf '%-14s %s' "$name" "$(project "$name" describe)")")
        done
        ui_menu index "Gerenciar Astro" "${labels[@]}" "Administração" "Voltar"
        if ((index < ${#candidates[@]})); then
            project_actions "${candidates[index]}" || true
        elif ((index == ${#candidates[@]})); then
            IMPLODED=false
            administration
            $IMPLODED && return 0
        else
            return 0
        fi
        echo
    done
}

dev_mode() {
    local history="$HOME/.claude/projects/${PWD//[^A-Za-z0-9]/-}"
    ui_step "Modo desenvolvimento"
    ui_info "abrindo o Claude Code em $PWD (para sair: /exit; para voltar ao assistente: astro)"
    if compgen -G "$history/*.jsonl" >/dev/null; then
        exec claude --continue
    fi
    exec claude
}

ui_step "Astro: ${#PROJECTS[@]} projeto(s): ${PROJECTS[*]}"
while true; do
    if installed_any; then
        install_label="Reinstalar Astro"
    else
        install_label="Instalar Astro"
    fi
    options=("$install_label" "Gerenciar Astro")
    command -v claude >/dev/null && options+=("Modo desenvolvimento")
    options+=("Sair")
    ui_menu choice "O que você quer fazer?" "${options[@]}"
    case ${options[choice]} in
        "Gerenciar Astro")      manage || true ;;
        "Modo desenvolvimento") dev_mode ;;
        "Sair")                 ui_info "até mais!"; break ;;
        *)                      install_astro || true ;;
    esac
    echo
done
