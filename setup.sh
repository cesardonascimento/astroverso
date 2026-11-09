#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"

ASTRO_PROJECT=astro
source lib/ui.sh
source lib/host.sh

trap '_ui_cursor_show; echo; ui_warn "cancelado"; exit 130' INT

[[ -t 0 ]] || ui_fail "execute em um terminal interativo"

mapfile -t PROJECTS < <(for f in */project.sh; do [[ -x $f ]] && dirname "$f"; done)
((${#PROJECTS[@]})) || ui_fail "nenhum projeto encontrado"

project() {
    local name=$1
    shift
    "./$name/project.sh" "$@"
}

run_all() {
    local action=$1
    shift
    local name failed=() succeeded=()
    for name in "${@:2}"; do
        if project "$name" $action ${1:+"$1"}; then
            succeeded+=("$name")
        else
            failed+=("$name")
        fi
    done
    summary
}

system_upgrade() {
    ui_step "Sistema"
    host_upgrade
}

summary() {
    ui_step "Resumo"
    ((${#succeeded[@]} == 0)) || ui_ok "concluído: ${succeeded[*]}"
    ((${#failed[@]} == 0)) || ui_error "falhou: ${failed[*]}"
    ((${#failed[@]} == 0))
}

install_all() {
    local name pending=()
    ui_step "Verificando projetos"
    for name in "${PROJECTS[@]}"; do
        if project "$name" status; then
            ui_info "$name já instalado, pulando"
        else
            ui_info "$name será instalado"
            pending+=("$name")
        fi
    done
    if ((${#pending[@]} == 0)); then
        ui_ok "tudo já está instalado"
        return
    fi
    system_upgrade
    run_all install "" "${pending[@]}"
}

install_selected() {
    local name labels=() chosen=() picked=()
    for name in "${PROJECTS[@]}"; do
        local label
        label="$(printf '%-12s %s' "$name" "$(project "$name" describe)")"
        project "$name" status && label+=$' \033[2m(instalado, será recriado)\033[0m'
        labels+=("$label")
    done

    ui_checklist chosen "Quais projetos instalar?" --all "${labels[@]}"
    ((${#chosen[@]})) || { ui_warn "nenhum projeto selecionado"; return; }
    for name in "${chosen[@]}"; do picked+=("${PROJECTS[name]}"); done
    system_upgrade
    run_all install "" "${picked[@]}"
}

reinstall_all() {
    ui_confirm "isso apaga os dados de TODOS os projetos e reinstala do zero. confirma?" n \
        || { ui_warn "cancelado"; return; }
    system_upgrade
    local name failed=() succeeded=()
    for name in "${PROJECTS[@]}"; do
        if project "$name" remove --purge && project "$name" install; then
            succeeded+=("$name")
        else
            failed+=("$name")
        fi
    done
    summary
}

remove_all() {
    local mode
    ui_menu mode "Como remover os containers de todos os projetos?" \
        "Manter os dados (os volumes continuam no disco)" \
        "Apagar tudo (containers e volumes)" \
        "Cancelar"
    case $mode in
        0) run_all remove "" "${PROJECTS[@]}" ;;
        1)
            ui_confirm "isso apaga os dados de TODOS os projetos. confirma?" n || { ui_warn "cancelado"; return; }
            run_all remove --purge "${PROJECTS[@]}"
            ;;
        *) ui_warn "cancelado" ;;
    esac
}

configure_project() {
    local name index candidates=() labels=()
    for name in "${PROJECTS[@]}"; do
        project "$name" status || continue
        [[ -n "$(project "$name" actions 2>/dev/null)" ]] || continue
        candidates+=("$name")
        labels+=("$(printf '%-12s %s' "$name" "$(project "$name" describe)")")
    done
    if ((${#candidates[@]} == 0)); then
        ui_warn "nenhum projeto instalado tem configurações extras"
        return
    fi

    ui_menu index "Qual projeto configurar?" "${labels[@]}" "Voltar"
    ((index < ${#candidates[@]})) || return 0
    name=${candidates[index]}

    local id label ids=() action_labels=()
    while IFS='|' read -r id label; do
        ids+=("$id")
        action_labels+=("$label")
    done < <(project "$name" actions)

    ui_menu index "O que fazer no $name?" "${action_labels[@]}" "Voltar"
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

ui_step "Astro: ${#PROJECTS[@]} projeto(s) encontrado(s): ${PROJECTS[*]}"
while true; do
    global_actions
    ui_menu choice "O que você quer fazer?" \
        "Instalar todos (pula os já instalados)" \
        "Escolher quais instalar" \
        "Configurar um projeto instalado" \
        "${GLOBAL_LABELS[@]}" \
        "Reinstalar tudo do zero (apaga os dados)" \
        "Remover todos os containers" \
        "Sair"

    globals=${#GLOBAL_IDS[@]}
    if ((choice >= 3 && choice < 3 + globals)); then
        read -r name id <<< "${GLOBAL_IDS[choice - 3]}"
        project "$name" action "$id" || true
        echo
        continue
    fi
    ((choice >= 3 + globals)) && choice=$((choice - globals))
    case $choice in
        0) install_all || true ;;
        1) install_selected || true ;;
        2) configure_project || true ;;
        3) reinstall_all || true ;;
        4) remove_all || true ;;
        *) ui_info "até mais!"; break ;;
    esac
    echo
done
