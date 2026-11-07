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
ROOT_CA=data/caddy/caddy/pki/authorities/local/root.crt
PUBLIC_CA=data/etc/public/astro-ca.crt

cmd_describe() {
    echo "Caddy: proxy reverso com HTTPS para os serviços da rede"
}

cmd_status() {
    podman container exists "$CONTAINER"
}

cmd_actions() {
    printf '%s\n' \
        "list|Listar rotas" \
        "add|Adicionar rotas" \
        "remove|Remover rotas" \
        "ca|Instalar o certificado HTTPS em outros aparelhos"
}

remove_container() {
    podman compose down >/dev/null 2>&1 || true
    podman rm -f "$CONTAINER" >/dev/null 2>&1 || true
}

normalize_host() {
    local host="${1,,}" domain
    domain="$(env_get CADDY_DOMAIN)"
    [[ $host == *.* ]] || host="$host.$domain"
    [[ $host =~ ^([a-z0-9]([a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,}$ ]] || return 1
    printf '%s' "$host"
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

configure() {
    ui_step "Configuração"
    if [[ -f .env ]] && ui_confirm "usar a configuração já salva em caddy/.env?" y; then
        ui_ok "configuração existente mantida"
    else
        local domain http_port https_port
        ui_input domain     "domínio base dos serviços (ex: casa.com)" "$(env_get CADDY_DOMAIN)"
        ui_input http_port  "porta HTTP no host" "$(env_get HTTP_PORT 80)"
        ui_input https_port "porta HTTPS no host" "$(env_get HTTPS_PORT 443)"
        cat > .env <<EOF
CADDY_DOMAIN='${domain,,}'
HTTP_PORT='$http_port'
HTTPS_PORT='$https_port'
EOF
        ui_ok "configuração salva em caddy/.env"
    fi

    if [[ ! -f $ROUTES && -x ../adguard/project.sh ]]; then
        echo "adguard.$(env_get CADDY_DOMAIN) http://astro-adguard:80" > "$ROUTES"
        ui_ok "rota padrão criada: adguard.$(env_get CADDY_DOMAIN) → astro-adguard:80"
    fi
}

render_caddyfile() {
    local host upstream
    mkdir -p "$(dirname "$CADDYFILE")" "$(dirname "$PUBLIC_CA")"
    {
        printf '{\n\tlocal_certs\n\tskip_install_trust\n}\n\n'
        printf 'http://ca.%s {\n\troot * /etc/caddy/public\n\tfile_server browse\n}\n' "$(env_get CADDY_DOMAIN)"
        while read -r host upstream; do
            printf '\n%s {\n\treverse_proxy %s\n}\n' "$host" "$upstream"
        done < <(route_lines)
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

publish_root_ca() {
    timeout 30 bash -c "until test -f '$ROOT_CA'; do sleep 1; done" \
        || ui_fail "o certificado raiz não foi gerado"
    cp "$ROOT_CA" "$PUBLIC_CA"
    chmod 0644 "$PUBLIC_CA"
}

trust_root_ca_here() {
    local ca_file
    if [[ -d /etc/pki/ca-trust/source/anchors ]]; then
        ca_file=/etc/pki/ca-trust/source/anchors/astro-caddy.crt
        sudo tee "$ca_file" < "$PUBLIC_CA" >/dev/null
        sudo update-ca-trust
    elif [[ -d /usr/local/share/ca-certificates ]]; then
        ca_file=/usr/local/share/ca-certificates/astro-caddy.crt
        sudo tee "$ca_file" < "$PUBLIC_CA" >/dev/null
        sudo update-ca-certificates >/dev/null
    else
        ui_warn "não sei instalar certificados neste sistema, use o arquivo $PUBLIC_CA"
        return
    fi
    ui_ok "certificado raiz confiável nesta máquina"
}

print_routes() {
    local host upstream count=0
    while read -r host upstream; do
        ui_info "https://$host → $upstream"
        count=$((count + 1))
    done < <(route_lines)
    ((count)) || ui_info "nenhuma rota cadastrada"
}

cmd_install() {
    configure

    ui_step "Host"
    host_unprivileged_ports "$(env_get HTTP_PORT 80)"
    host_firewall "$(env_get HTTP_PORT 80)/tcp" "$(env_get HTTPS_PORT 443)/tcp" "$(env_get HTTPS_PORT 443)/udp"
    host_compose
    host_autostart
    host_tailscale

    ui_step "Container"
    mkdir -p data/caddy data/config
    render_caddyfile
    remove_container
    local log
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
    publish_root_ca
    ui_ok "certificado raiz próprio gerado (válido só na sua rede)"
    if ui_confirm "confiar nesse certificado nesta máquina?" y; then
        trust_root_ca_here
    fi

    ui_step "Rotas"
    print_routes
    ui_info "instale o certificado nos outros aparelhos abrindo http://ca.$(env_get CADDY_DOMAIN)"
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
        if route_lines | awk -v h="$host" '$1 == h { found = 1 } END { exit !found }'; then
            ui_warn "$host já existe, remova antes para alterar"
            continue
        fi
        while true; do
            upstream="$(_ui_ask "destino de $host (ex: 192.168.3.43:3000): ")"
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

action_ca() {
    ui_step "Certificado HTTPS"
    ui_info "em cada aparelho, abra http://ca.$(env_get CADDY_DOMAIN) e baixe astro-ca.crt"
    ui_info "Android: Configurações → Segurança → Criptografia → Instalar certificado → Certificado de CA"
    ui_info "iPhone: instale o perfil baixado e ative em Ajustes → Geral → Sobre → Confiança de Certificados"
    ui_info "Windows: abra o arquivo → Instalar → Máquina Local → Autoridades de Certificação Raiz Confiáveis"
    ui_info "macOS: abra no Acesso às Chaves (Sistema) e marque \"Sempre Confiar\""
    ui_info "arquivo local: $(pwd)/$PUBLIC_CA"
}

cmd_action() {
    case "${1:-}" in
        list)   ui_step "Rotas"; print_routes ;;
        add)    action_add ;;
        remove) action_remove ;;
        ca)     action_ca ;;
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
            ui_ok "dados apagados (caddy/data); um novo certificado raiz será gerado na próxima instalação"
        else
            ui_info "nenhum dado para apagar"
        fi
    else
        ui_info "dados mantidos em caddy/data"
    fi
    ui_info "rotas mantidas em caddy/$ROUTES"
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
