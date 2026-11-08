#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"

ASTRO_PROJECT=caddy
source ../lib/ui.sh
source ../lib/host.sh
source ../lib/env.sh

CONTAINER=astro-caddy
ROUTES=.routes
CADDYFILE=data/etc/Caddyfile
CLOUDFLARE_API=https://api.cloudflare.com/client/v4

cmd_describe() {
    echo "Caddy: proxy reverso com HTTPS (Let's Encrypt) para os serviços da rede"
}

cmd_status() {
    podman container exists "$CONTAINER"
}

cmd_actions() {
    printf '%s\n' \
        "list|Listar rotas" \
        "add|Adicionar rotas" \
        "remove|Remover rotas" \
        "reload|Recarregar rotas (inclui as declaradas por outros projetos)"
}

remove_container() {
    podman compose down >/dev/null 2>&1 || true
    podman rm -f "$CONTAINER" >/dev/null 2>&1 || true
}

normalize_host() {
    local host=$1
    [[ $host == *.* ]] || host="$host.$(env_get CADDY_DOMAIN)"
    is_hostname "$host"
}

normalize_upstream() {
    local upstream=$1
    [[ $upstream == http://* || $upstream == https://* ]] || upstream="http://$upstream"
    [[ $upstream =~ ^https?://[A-Za-z0-9.-]+(:[0-9]{1,5})?(/.*)?$ ]] || return 1
    printf '%s' "$upstream"
}

route_lines() {
    [[ -f $ROUTES ]] && grep -v '^\s*$' "$ROUTES" || true
}

project_route_lines() {
    local file
    for file in ../*/.proxy; do
        [[ -f $file && $file != ../caddy/.proxy ]] || continue
        grep -v '^\s*$' "$file" | sed "s|\$| ${file#../}|; s|/\.proxy\$||"
    done
}

all_route_lines() {
    { project_route_lines; route_lines; } | awk '!seen[$1]++ { print $1, $2 }'
}

cloudflare_get() {
    curl -s -m 15 -H @- "$CLOUDFLARE_API/$2" <<< "Authorization: Bearer $1"
}

cloudflare_check() {
    local token=$1 domain=$2 zone=$2
    if ! cloudflare_get "$token" user/tokens/verify | grep -q '"status":"active"'; then
        ui_warn "token inválido ou inativo na Cloudflare"
        return 1
    fi
    while [[ $zone == *.* ]]; do
        if cloudflare_get "$token" "zones?name=$zone" | grep -q '"count":1'; then
            ui_ok "token válido com acesso à zona $zone"
            return 0
        fi
        zone="${zone#*.}"
    done
    ui_warn "o token não enxerga a zona de $domain: ele precisa de Zone → Zone → Read nessa zona"
    return 1
}

token_instructions() {
    ui_info "o Caddy precisa de um token de API da Cloudflare para provar ao Let's Encrypt que $1 é seu"
    ui_info "como criar (1 minuto):"
    ui_info "  1. abra https://dash.cloudflare.com/profile/api-tokens → Create Token"
    ui_info "  2. use o modelo \"Edit zone DNS\" e edite a política (lápis) para ter as duas permissões:"
    ui_info "       Zone → Zone → Read   e   Zone → DNS → Edit (ou Write)"
    ui_info "  3. restrinja a política à zona: Include → Specific zone → $1"
    ui_info "  4. deixe sem expiração (se expirar, o certificado para de renovar)"
    ui_info "  5. Continue to summary → Create Token"
    ui_info "  6. copie o token e guarde no seu gerenciador de senhas (ele só aparece uma vez)"
}

configure() {
    ui_step "Configuração"
    local domain http_port https_port token
    if [[ -f .env ]] && ui_confirm "usar a configuração já salva em caddy/.env?" y; then
        domain="$(env_get CADDY_DOMAIN)"
        http_port="$(env_get HTTP_PORT 80)"
        https_port="$(env_get HTTPS_PORT 443)"
        token="$(env_get CLOUDFLARE_API_TOKEN)"
        ui_ok "configuração existente mantida"
    else
        ui_input domain     "domínio base dos serviços (ex: casa.com)" "$(env_get CADDY_DOMAIN)" is_hostname
        ui_input http_port  "porta HTTP no host" "$(env_get HTTP_PORT 80)" is_port
        ui_input https_port "porta HTTPS no host" "$(env_get HTTPS_PORT 443)" is_port
        token=""
    fi

    if [[ -n $token ]] && cloudflare_check "$token" "$domain"; then
        :
    else
        token_instructions "$domain"
        while true; do
            ui_secret token "token de API da Cloudflare"
            cloudflare_check "$token" "$domain" && break
        done
    fi

    (
        umask 077
        printf "CADDY_DOMAIN='%s'\nHTTP_PORT='%s'\nHTTPS_PORT='%s'\nCLOUDFLARE_API_TOKEN='%s'\n" \
            "$domain" "$http_port" "$https_port" "$token" > .env.new
    )
    mv .env.new .env
    ui_ok "configuração salva em caddy/.env"
}

render_upstream() {
    local indent=$1 upstream=$2
    if [[ $upstream == https+insecure://* ]]; then
        printf '%sreverse_proxy https://%s {\n%s\ttransport http {\n%s\t\ttls_insecure_skip_verify\n%s\t}\n%s}\n' \
            "$indent" "${upstream#https+insecure://}" "$indent" "$indent" "$indent" "$indent"
    else
        printf '%sreverse_proxy %s\n' "$indent" "$upstream"
    fi
}

render_caddyfile() {
    local domain host upstream index=0 others=()
    domain="$(env_get CADDY_DOMAIN)"
    mkdir -p "$(dirname "$CADDYFILE")"
    {
        printf '{\n\tacme_dns cloudflare {env.CLOUDFLARE_API_TOKEN}\n}\n\n*.%s {\n' "$domain"
        while read -r host upstream; do
            if [[ $host == *".$domain" && ${host%".$domain"} != *.* ]]; then
                index=$((index + 1))
                printf '\t@route%d host %s\n\thandle @route%d {\n' "$index" "$host" "$index"
                render_upstream $'\t\t' "$upstream"
                printf '\t}\n\n'
            else
                others+=("$host $upstream")
            fi
        done < <(all_route_lines)
        printf '\thandle {\n\t\tabort\n\t}\n}\n'
        for host in "${others[@]}"; do
            printf '\n%s {\n' "${host%% *}"
            render_upstream $'\t' "${host#* }"
            printf '}\n'
        done
    } > "$CADDYFILE"
}

apply_routes() {
    render_caddyfile
    cmd_status || return 0
    local log
    if ! log="$(podman exec "$CONTAINER" caddy reload --config /etc/caddy/Caddyfile 2>&1)"; then
        printf '%s\n' "$log" | ui_prefix >&2
        ui_fail "o Caddy recusou a configuração"
    fi
    ui_ok "Caddy recarregado sem reiniciar"
}

wait_certificate() {
    local domain https_port
    domain="$(env_get CADDY_DOMAIN)"
    https_port="$(env_get HTTPS_PORT 443)"
    ui_info "aguardando o certificado *.$domain do Let's Encrypt (até 3 minutos)..."
    if timeout 180 bash -c "until openssl s_client -connect 127.0.0.1:$https_port -servername astro-check.$domain \
            -verify_return_error </dev/null >/dev/null 2>&1; do sleep 3; done"; then
        ui_ok "certificado válido do Let's Encrypt para *.$domain"
    else
        podman logs --tail 50 "$CONTAINER" 2>&1 | grep -iE 'error|fail' | tail -5 | ui_prefix >&2
        ui_fail "o certificado não foi emitido em 3 minutos"
    fi
}

print_routes() {
    local host upstream owner count=0
    while read -r host upstream owner; do
        ui_info "https://$host → $upstream${owner:+  (do projeto $owner)}"
        count=$((count + 1))
    done < <({ project_route_lines; route_lines; } | awk '!seen[$1]++')
    ((count)) || ui_info "nenhuma rota cadastrada"
}

cmd_install() {
    configure

    ui_step "Host"
    local http_port https_port
    http_port="$(env_get HTTP_PORT 80)"
    https_port="$(env_get HTTPS_PORT 443)"
    host_unprivileged_ports "$((http_port < https_port ? http_port : https_port))"
    host_firewall "$http_port/tcp" "$https_port/tcp" "$https_port/udp"
    host_base

    ui_step "Container"
    local log
    ui_info "construindo a imagem com o módulo da Cloudflare (alguns minutos na primeira vez)..."
    if ! log="$(podman compose build 2>&1)"; then
        printf '%s\n' "$log" | ui_prefix >&2
        ui_fail "falha ao construir a imagem"
    fi
    mkdir -p data/caddy data/config
    render_caddyfile
    remove_container
    if ! log="$(podman compose up -d 2>&1)"; then
        printf '%s\n' "$log" | ui_prefix >&2
        ui_fail "falha ao subir o container"
    fi
    if ! timeout 60 bash -c "until podman exec $CONTAINER wget -q --spider http://127.0.0.1:2019/config/ 2>/dev/null; do sleep 1; done"; then
        podman compose logs --tail 20 2>&1 | ui_prefix >&2
        ui_fail "o Caddy não respondeu em 60s"
    fi
    ui_ok "container $CONTAINER rodando"

    ui_step "Certificado HTTPS"
    wait_certificate

    ui_step "Rotas"
    print_routes
}

action_add() {
    ui_step "Adicionar rotas"
    local host upstream added=0
    while true; do
        host="$(_ui_ask "subdomínio ou endereço completo (Enter vazio para terminar): ")"
        [[ -z $host ]] && break
        if ! host="$(normalize_host "$host")"; then
            ui_warn "endereço inválido"
            continue
        fi
        if all_route_lines | awk -v h="$host" '$1 == h { found = 1 } END { exit !found }'; then
            ui_warn "$host já existe, remova antes para alterar"
            continue
        fi
        while true; do
            upstream="$(_ui_ask "destino de $host (ex: $(host_lan_ip):3000): ")"
            upstream="$(normalize_upstream "$upstream")" && break
            ui_warn "destino inválido"
        done
        echo "$host $upstream" >> "$ROUTES"
        ui_ok "https://$host → $upstream"
        added=$((added + 1))
    done
    if ((added)); then
        apply_routes
    else
        ui_info "nenhuma rota adicionada"
    fi
}

action_remove() {
    ui_step "Remover rotas"
    local lines=() chosen=() i
    mapfile -t lines < <(route_lines)
    ((${#lines[@]})) || { ui_info "nenhuma rota cadastrada"; return; }
    ui_checklist chosen "Quais rotas remover?" "${lines[@]}"
    ((${#chosen[@]})) || { ui_info "nenhuma rota removida"; return; }
    for i in "${chosen[@]}"; do
        ui_ok "removida: ${lines[i]%% *}"
        unset 'lines[i]'
    done
    printf '%s\n' "${lines[@]}" > "$ROUTES"
    apply_routes
}

cmd_action() {
    case "${1:-}" in
        list)   ui_step "Rotas"; print_routes ;;
        add)    action_add ;;
        remove) action_remove ;;
        reload) ui_step "Rotas"; apply_routes ;;
        *)      ui_fail "ação desconhecida: ${1:-}" ;;
    esac
}

cmd_remove() {
    local purge=false
    [[ ${1:-} == --purge ]] && purge=true

    ui_step "Remoção"
    if cmd_status; then
        remove_container
        ui_ok "container $CONTAINER removido"
    else
        ui_info "nenhum container para remover"
    fi

    if $purge; then
        if [[ -d data ]]; then
            podman unshare rm -rf data
            ui_ok "dados apagados (caddy/data); o certificado será emitido de novo na próxima instalação"
        else
            ui_info "nenhum dado para apagar"
        fi
    else
        ui_info "dados mantidos em caddy/data"
    fi
    ui_info "rotas e token mantidos em caddy/$ROUTES e caddy/.env"
}

case "${1:-}" in
    describe) cmd_describe ;;
    status)   cmd_status ;;
    actions)  cmd_actions ;;
    action)   shift; cmd_action "$@" ;;
    install)  cmd_install ;;
    remove)   shift; cmd_remove "$@" ;;
    *)        ui_fail "uso: $0 describe | status | actions | action <id> | install | remove [--purge]" ;;
esac
