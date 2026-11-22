#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"

ASTROVERSO_PROJECT=discord
source ui.sh
source env.sh
source host.sh
source discord.sh

ROOT="$(dirname "$PWD")"
WORK="${XDG_STATE_HOME:-$HOME/.local/state}/astroverso/discord"
TIMEOUT=600
CONTAINER_OPS="start stop restart"
CHANNELS=(financeiro dados sistema)
PUBLISH_EVERY=300

project_containers() {
    podman ps -a --format '{{.Names}}' | grep -E "^astroverso-$1(-[a-z0-9-]+)?$" | sort -r || true
}

catalog_lines() {
    echo "machine:status|Máquina: estado (containers, discos e próximos agendamentos)|nao|host|status|host"
    [[ -z $(host_machines) ]] || echo "machine:wake|Máquina: ligar outra máquina da rede (argumento: o nome cadastrado; sem ele, botões)|nao|host|wake|host"
    local file name id description confirm
    for file in "$ROOT"/*/project.sh; do
        name="$(basename "$(dirname "$file")")"
        [[ -x $file ]] || continue
        "$file" status >/dev/null 2>&1 </dev/null || continue
        if [[ -n $(project_containers "$name") ]]; then
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
    local file
    for file in "$ROOT"/*/project.sh; do
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

write_manifest() {
    mkdir -p "$WORK"
    python3 -I - "$WORK/catalogo.lines" "$WORK/ajuda.lines" "${CHANNELS[@]}" > "$WORK/manifesto.tmp" <<'PY'
import json, sys
catalogo = []
for line in open(sys.argv[1]):
    parts = line.rstrip("\n").split("|")
    if len(parts) >= 6 and parts[0]:
        catalogo.append({"id": parts[0], "descricao": parts[1], "confirmar": parts[2] == "sim",
                         "projeto": parts[3], "op": parts[4], "tipo": parts[5]})
ajuda, grupos = [], []
for line in open(sys.argv[2]):
    parts = line.rstrip("\n").split("|")
    if len(parts) >= 5 and parts[1]:
        item = dict(zip(("grupo", "nome", "descricao", "quando", "comando"), parts[:5]))
        item["ordem"] = int(parts[5]) if len(parts) > 5 and parts[5].isdigit() else 50
        if item["grupo"] not in grupos:
            grupos.append(item["grupo"])
        ajuda.append(item)
ajuda.sort(key=lambda item: (grupos.index(item["grupo"]), item["ordem"]))
canais = [{"nome": nome, "escrita": False, "escuta": False} for nome in sys.argv[3:]]
print(json.dumps({"catalogo": catalogo, "ajuda": ajuda, "canais": canais, "botoes": []}, ensure_ascii=False))
PY
    mv "$WORK/manifesto.tmp" "$WORK/manifesto.json"
}

publish() {
    mkdir -p "$WORK"
    catalog_lines > "$WORK/catalogo.lines"
    help_lines > "$WORK/ajuda.lines"
    write_manifest
    local answer
    if answer="$(discord_api PUT /v1/cliente "$WORK/manifesto.json")"; then
        ui_ok "catálogo publicado: $(python3 -I -c 'import json,sys; d=json.load(sys.stdin); print(d.get("comandos", 0), "comandos")' <<< "$answer" 2>/dev/null)"
        return 0
    fi
    ui_warn "astroverso-discord não aceitou o catálogo ($(discord_url))"
    return 1
}

catalog_entry() {
    awk -F'|' -v id="$1" '$1 == id { printf "%s\x1f%s\x1f%s\n", $4, $5, $6; found = 1; exit } END { exit !found }' "$WORK/catalogo.lines"
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
    local id=$1 status=$2 output=$3 buttons=${4:-} file
    file="$WORK/resposta-$id.json"
    python3 -I -c '
import json, sys
dados = {"ok": sys.argv[1] == "0", "saida": sys.argv[2]}
botoes = [dict(zip(("rotulo", "acao", "arg"), linha.split("|"))) for linha in sys.argv[3].splitlines() if linha]
if botoes:
    dados["botoes"] = botoes
print(json.dumps(dados, ensure_ascii=False))
' "$status" "$output" "$buttons" > "$file"
    discord_api POST "/v1/eventos/$id/resposta" "$file" >/dev/null || ui_warn "resposta do pedido $id não entregue"
    rm -f "$file"
}

process() {
    local id=$1 action=$2 arg=$3 user=$4 name=$5 output="" buttons="" status=0 project op kind entry=""
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
    elif [[ $kind == container && " $CONTAINER_OPS " == *" $op "* ]]; then
        output="$(container_op "$project" "$op" 2>&1)" || status=$?
    else
        output="$(timeout "$TIMEOUT" "$ROOT/$project/project.sh" remote "$op" ${arg:+"$arg"} 2>&1 </dev/null)" || status=$?
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

events() {
    local answer
    answer="$(DISCORD_TIMEOUT=40 discord_api GET '/v1/eventos?espera=25')" || return 1
    python3 -I -c '
import json, sys
for e in json.loads(sys.stdin.read() or "{}").get("eventos", []):
    if e.get("tipo") != "comando":
        continue
    u = e.get("usuario") or {}
    campos = (e.get("id", ""), e.get("acao", ""), e.get("arg", ""), u.get("id", ""), u.get("nome", ""))
    print("\x1f".join(str(c).replace("\x1f", " ").replace("\n", " ") for c in campos))
' <<< "$answer"
}

run() {
    local last=0 waited=false id action arg user name
    mkdir -p "$WORK"
    ui_info "cliente $DISCORD_CLIENT do astroverso-discord"
    while true; do
        if ! discord_ready; then
            $waited || ui_info "astroverso-discord não configurado nesta máquina: tento de novo a cada minuto"
            waited=true
            sleep 60
            continue
        fi
        if (($(date +%s) - last >= PUBLISH_EVERY)); then
            if publish; then
                last=$(date +%s)
                ui_info "conectado a $(discord_url)"
            else
                sleep 30
                continue
            fi
        fi
        find "$DISCORD_SPOOL" -name '*.json' -mmin +4320 -delete 2>/dev/null || true
        discord_flush || true
        local list
        if ! list="$(events)"; then
            sleep 10
            continue
        fi
        while IFS=$'\x1f' read -r id action arg user name; do
            [[ $id =~ ^[a-f0-9]{32}$ ]] || continue
            process "$id" "$action" "$arg" "$user" "$name" &
        done <<< "$list"
    done
}

case "${1:-}" in
    run)     run ;;
    publish) publish ;;
    *)       ui_fail "uso: $0 run | publish" ;;
esac
