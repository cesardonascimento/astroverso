#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"

ASTROVERSO_PROJECT=discord
source ../lib/ui.sh
source ../lib/env.sh
source ../lib/host.sh

FILA="$STATE/fila"
TIMEOUT=600
SELF=discord
CONTAINER_OPS="start stop restart"

project_containers() {
    podman ps -a --format '{{.Names}}' | grep -E "^astroverso-$1(-[a-z0-9-]+)?$" | sort -r || true
}

catalog_lines() {
    echo "machine:status|Máquina: estado (containers, discos e próximos agendamentos)|nao|host|status|host"
    [[ -z $(host_machines) ]] || echo "machine:wake|Máquina: ligar outra máquina da rede (argumento: o nome cadastrado; sem ele, botões)|nao|host|wake|host"
    local file name id description confirm
    for file in ../*/project.sh; do
        name="$(basename "$(dirname "$file")")"
        [[ -x $file ]] || continue
        "$file" status >/dev/null 2>&1 </dev/null || continue
        if [[ $name != "$SELF" && -n $(project_containers "$name") ]]; then
            printf '%s\n' \
                "$name:start|Serviço: iniciar $name|nao|$name|start|container" \
                "$name:stop|Serviço: parar $name (fica parado até o start, mesmo depois de reiniciar a máquina)|sim|$name|stop|container" \
                "$name:restart|Serviço: reiniciar $name|sim|$name|restart|container"
        fi
        grep -q '^    remote-actions)' "$file" || continue
        while IFS='|' read -r id description confirm; do
            [[ -n $id ]] || continue
            if [[ $id == *:* ]]; then
                printf '%s|%s|%s|%s|%s|remote\n' "$id" "$description" "${confirm:-nao}" "$name" "$id"
            else
                printf '%s|%s|%s|%s|%s|remote\n' "$name:$id" "$description" "${confirm:-nao}" "$name" "$id"
            fi
        done < <("$file" remote-actions 2>/dev/null </dev/null || true)
    done
}

help_lines() {
    local file name
    for file in ../*/project.sh; do
        [[ -x $file ]] && grep -q '^    help)' "$file" || continue
        "$file" status >/dev/null 2>&1 </dev/null || continue
        "$file" help 2>/dev/null </dev/null || true
    done
    echo "Máquina e serviços|Máquina: estado|containers, discos e próximos agendamentos|quando quiser|machine:status"
    [[ -z $(host_machines) ]] || echo "Máquina e serviços|Máquina: ligar|liga pelo Wake-on-LAN uma máquina cadastrada em Administração → Máquinas da rede (sem o nome, mostra um botão por máquina)|quando quiser|machine:wake [nome]"
    printf '%s\n' \
        "Máquina e serviços|Serviço: iniciar|sobe os containers de um projeto|quando quiser|<projeto>:start" \
        "Máquina e serviços|Serviço: parar|para os containers (ficam parados até o start); pede confirmação|quando quiser|<projeto>:stop" \
        "Máquina e serviços|Serviço: reiniciar|reinicia os containers; pede confirmação|quando quiser|<projeto>:restart" \
        "Máquina e serviços|Painel|um botão para cada comando e um menu para os serviços|quando quiser|panel" \
        "Máquina e serviços|Ajuda|esta lista|quando quiser|help"
}

write_catalog() {
    mkdir -p "$FILA"/{pedidos,respostas,saida,tmp,andamento}
    catalog_lines | python3 -I -c '
import json, sys
items = []
for line in sys.stdin:
    parts = line.rstrip("\n").split("|")
    if len(parts) >= 6 and parts[0]:
        items.append({"id": parts[0], "descricao": parts[1], "confirmar": parts[2] == "sim",
                      "projeto": parts[3], "op": parts[4], "tipo": parts[5]})
print(json.dumps(items, ensure_ascii=False))
' > "$FILA/tmp/catalogo.json"
    mv "$FILA/tmp/catalogo.json" "$FILA/catalogo.json"
    help_lines | python3 -I -c '
import json, sys
items, groups = [], []
for line in sys.stdin:
    parts = line.rstrip("\n").split("|")
    if len(parts) >= 5 and parts[1]:
        item = dict(zip(("grupo", "nome", "descricao", "quando", "comando"), parts[:5]))
        item["ordem"] = int(parts[5]) if len(parts) > 5 and parts[5].isdigit() else 50
        if item["grupo"] not in groups:
            groups.append(item["grupo"])
        items.append(item)
items.sort(key=lambda item: (groups.index(item["grupo"]), item["ordem"]))
print(json.dumps(items, ensure_ascii=False))
' > "$FILA/tmp/ajuda.json"
    mv "$FILA/tmp/ajuda.json" "$FILA/ajuda.json"
}

catalog_entry() {
    python3 -I -c '
import json, sys
for a in json.load(open(sys.argv[1])):
    if a["id"] == sys.argv[2]:
        print("\x1f".join((a.get("projeto", ""), a.get("op", ""), a.get("tipo", ""))))
        break
else:
    sys.exit(1)
' "$FILA/catalogo.json" "$1"
}

next_run() {
    systemctl --user show -p NextElapseUSecRealtime --value "$1" 2>/dev/null || true
}

host_status() {
    local latest timer
    echo "$(hostname -s): ligada desde $(uptime -s)"
    if command -v rpm >/dev/null; then
        latest="$(rpm -q --last kernel-core 2>/dev/null | head -1 | awk '{ print $1 }')"
        if [[ -n $latest && $latest != "kernel-core-$(uname -r)" ]]; then
            echo "kernel novo instalado (${latest#kernel-core-}): falta reiniciar"
        fi
    fi
    echo
    echo "containers:"
    podman ps -a --format '{{.Names}}: {{.Status}}' | grep '^astroverso-' | sed 's/^/  /' || echo "  nenhum"
    echo
    echo "discos:"
    df -h --output=target,used,size,pcent / /home $(findmnt -rn -o TARGET | grep '^/srv/' | sort) 2>/dev/null \
        | tail -n +2 | awk '!seen[$1]++ { printf "  %s: %s de %s (%s)\n", $1, $2, $3, $4 }'
    echo
    echo "próximos agendamentos:"
    while read -r timer; do
        [[ -n $timer ]] && printf '  %s: %s\n' "${timer%.timer}" "$(next_run "$timer")"
    done < <(systemctl --user list-timers 'astroverso-*' --all --no-pager --no-legend --plain 2>/dev/null \
        | grep -oE 'astroverso-[A-Za-z0-9-]+\.timer' | sort -u)
    return 0
}

container_op() {
    local project=$1 op=$2 names=()
    mapfile -t names < <(project_containers "$project")
    if ((${#names[@]} == 0)); then
        echo "nenhum container do $project"
        return 1
    fi
    case $op in
        start)   podman start "${names[@]}" >/dev/null ;;
        stop)    podman stop "${names[@]}" >/dev/null ;;
        restart) podman restart "${names[@]}" >/dev/null ;;
    esac
    podman ps -a --format '{{.Names}}: {{.Status}}' | grep -E "^astroverso-$project(-[a-z0-9-]+)?:" || true
}

respond() {
    local id=$1 status=$2 output=$3 buttons=${4:-}
    python3 -I -c '
import json, sys
dados = {"id": sys.argv[1], "ok": sys.argv[2] == "0", "saida": sys.argv[3]}
botoes = [dict(zip(("rotulo", "acao", "arg"), linha.split("|"))) for linha in sys.argv[4].splitlines() if linha]
if botoes:
    dados["botoes"] = botoes
print(json.dumps(dados, ensure_ascii=False))
' "$id" "$status" "$output" "$buttons" > "$FILA/tmp/$id.json"
    mv "$FILA/tmp/$id.json" "$FILA/respostas/$id.json"
}

process() {
    local file=$1 work id="" action="" arg="" user="" name="" output="" buttons="" status=0 project op
    work="$FILA/andamento/${file##*/}"
    mv "$file" "$work" 2>/dev/null || return 0
    IFS=$'\x1f' read -r id action arg user name < <(python3 -I -c '
import json, sys
d = json.load(open(sys.argv[1]))
print("\x1f".join(str(d.get(k, "")).replace("\x1f", " ").replace("\n", " ") for k in ("id", "acao", "arg", "usuario", "nome")))
' "$work" 2>/dev/null) || true
    rm -f "$work"
    if [[ ! $id =~ ^[a-f0-9]{32}$ ]]; then
        ui_warn "pedido ilegível descartado"
        return 0
    fi
    local kind="" entry=""
    if [[ $arg =~ ^[A-Za-z0-9._-]{0,64}$ ]]; then
        entry="$(catalog_entry "$action")" || entry=""
    fi
    if [[ -z $entry ]]; then
        ui_warn "recusado: $name ($user) pediu \"$action $arg\", fora da lista permitida"
        respond "$id" 1 "comando fora da lista permitida"
        return 0
    fi
    ui_info "pedido de $name ($user): $action${arg:+ $arg}"
    IFS=$'\x1f' read -r project op kind <<< "$entry"
    if [[ $kind == host && $op == wake && -z $arg ]]; then
        output="🖥️ Qual máquina ligar?"
        buttons="$(host_machines | awk '{ print $1 "|machine:wake|" $1 }')"
    elif [[ $kind == host && $op == wake ]]; then
        output="$(ASTROVERSO_PROJECT=astroverso host_wake "$arg" 2>&1)" || status=$?
    elif [[ $kind == host ]]; then
        output="$(host_status 2>&1)" || status=$?
    elif [[ $kind == container && $project != "$SELF" && " $CONTAINER_OPS " == *" $op "* ]]; then
        output="$(container_op "$project" "$op" 2>&1)" || status=$?
    else
        output="$(timeout "$TIMEOUT" "../$project/project.sh" remote "$op" ${arg:+"$arg"} 2>&1 </dev/null)" || status=$?
        ((status == 124)) && output+=$'\n'"interrompido: passou de $((TIMEOUT / 60)) minutos"
    fi
    output="$(sed 's/\x1b\[[0-9;]*m//g' <<< "$output")"
    ((${#output} <= 4000)) || output="${output: -4000}"
    respond "$id" "$status" "$output" "$buttons"
    if ((status)); then
        ui_warn "$action${arg:+ $arg}: falhou ($status)"
    else
        ui_ok "$action${arg:+ $arg}: concluído"
    fi
}

run() {
    write_catalog
    local file
    while true; do
        for file in "$FILA"/pedidos/*.json; do
            [[ -f $file ]] || continue
            process "$file" &
        done
        if [[ -z $(jobs -rp) ]] && ! compgen -G "$FILA/pedidos/*.json" >/dev/null; then
            break
        fi
        sleep 1
    done
    find "$FILA/respostas" -type f -mmin +1440 -delete 2>/dev/null || true
}

case "${1:-}" in
    run)     run ;;
    catalog) write_catalog ;;
    *)       ui_fail "uso: $0 run | catalog" ;;
esac
