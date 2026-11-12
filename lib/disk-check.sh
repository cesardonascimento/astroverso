#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"

ASTRO_PROJECT=discos
source ui.sh
source env.sh
source disk.sh
source notify.sh

problems=0
while read -r target type; do
    label="${target##*/}"
    if ! mountpoint -q "$target"; then
        problems=$((problems + 1))
        ui_warn "$target não está montado"
        notify_problem "$label" "o disco $label não está montado: confira se ele está ligado e conectado (os serviços que usam esse disco param de encontrá-lo)"
    elif ! disk_responds "$target"; then
        problems=$((problems + 1))
        ui_warn "$target não responde"
        notify_problem "$label" "o disco $label parou de responder (a conexão caiu e voltou?): ele fica inacessível até a máquina ser reiniciada"
    else
        notify_resolved "$label" "o disco $label voltou a responder"
    fi
done < <(disk_mounts)
((problems == 0)) && ui_ok "todos os discos da máquina respondem"
exit 0
