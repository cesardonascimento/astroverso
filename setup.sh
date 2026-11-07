#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"

ASTRO_PROJECT=astro
source lib/ui.sh

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

    ui_checklist chosen "Quais projetos instalar?" "${labels[@]}"
    ((${#chosen[@]})) || { ui_warn "nenhum projeto selecionado"; return; }
    for name in "${chosen[@]}"; do picked+=("${PROJECTS[name]}"); done
    run_all install "" "${picked[@]}"
}

reinstall_all() {
    ui_confirm "isso apaga os dados de TODOS os projetos e reinstala do zero. confirma?" n \
        || { ui_warn "cancelado"; return; }
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

ui_step "Astro: ${#PROJECTS[@]} projeto(s) encontrado(s): ${PROJECTS[*]}"
ui_menu choice "O que você quer fazer?" \
    "Instalar todos (pula os já instalados)" \
    "Escolher quais instalar" \
    "Reinstalar tudo do zero (apaga os dados)" \
    "Remover todos os containers" \
    "Sair"

case $choice in
    0) install_all ;;
    1) install_selected ;;
    2) reinstall_all ;;
    3) remove_all ;;
    *) ui_info "até mais!" ;;
esac
