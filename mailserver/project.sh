#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"

ASTRO_PROJECT=mailserver
source ../lib/ui.sh
source ../lib/host.sh
source ../lib/env.sh
source ../lib/proxy.sh
source ../lib/notify.sh

CONTAINER=astro-mailserver
NEXTCLOUD=astro-nextcloud
CLOUDFLARE_API=https://api.cloudflare.com/client/v4
WORKER=astro-mailserver
KV_TITLE=astro-mailserver
COMPATIBILITY_DATE=2026-10-01
MAIL_USER=inbox
IMAP_PORT=31143
SMTP_PORT=31587
QUARANTINE=Quarentena
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
FETCH_UNIT=astro-mailserver-fetch
FETCH_CALENDAR=("*-*-* 08..19:00/5:00" "*-*-* 20:00:00")
DOORBELL=campainha
LOCK="$STATE/.fetch.lock"
TOKEN=""
ROUTING_MX=""

cmd_describe() {
    echo "Mailserver: caixa de e-mail só de entrada, para automações (Cloudflare Email Routing + Dovecot)"
}

cmd_status() {
    podman container exists "$CONTAINER"
}

cmd_actions() {
    printf '%s\n' \
        "domains|Domínios autorizados (ver, adicionar, remover)" \
        "fetch|Buscar os e-mails agora" \
        "access|Mostrar os dados de acesso à caixa (IMAP)"
}

cmd_remote_actions() {
    echo "fetch|Mailserver: buscar os e-mails agora|nao"
}

cmd_help() {
    echo "Automações|Mailserver: buscar e-mails|traz para a caixa local os e-mails recebidos na Cloudflare|de 5 em 5 minutos, das 08:00 às 20:00 (só quando a campainha tocou)|mailserver:fetch|10"
}

remove_container() {
    compose down >/dev/null 2>&1 || true
    podman rm -f "$CONTAINER" >/dev/null 2>&1 || true
}

is_domains() {
    local item out=()
    for item in ${1//,/ }; do
        item="$(is_hostname "${item#@}")" || return 1
        [[ " ${out[*]} " == *" $item "* ]] || out+=("$item")
    done
    ((${#out[@]})) || return 1
    local IFS=,
    printf '%s' "${out[*]}"
}

domains_from_senders() {
    local item out=()
    for item in ${1//,/ }; do
        item="${item##*@}"
        [[ -n $item && " ${out[*]} " != *" ${item,,} "* ]] && out+=("${item,,}")
    done
    local IFS=,
    printf '%s' "${out[*]}"
}


cf() {
    local method=$1 path=$2
    shift 2
    curl -sS -m 120 -X "$method" -H @- "$@" "$CLOUDFLARE_API/$path" <<< "Authorization: Bearer $TOKEN"
}

CF_PARSE='
import json, sys
try:
    data = json.load(sys.stdin)
except ValueError:
    print("resposta inválida"); sys.exit(1)
if not data.get("success"):
    print("; ".join(str(e.get("message", e)) for e in data.get("errors") or []) or "resposta inesperada")
    sys.exit(1)
r = data.get("result")
value = eval(sys.argv[1])
if value is not None:
    print(value)
'

cf_call() {
    local -n __cf_out=$1
    local expr=$2 method=$3 path=$4 __cf_resp
    shift 4
    if ! __cf_resp="$(cf "$method" "$path" "$@" 2>&1)"; then
        ui_warn "sem resposta da Cloudflare ($method ${path%%\?*}): $__cf_resp"
        return 1
    fi
    if ! __cf_out="$(printf '%s' "$__cf_resp" | python3 -I -c "$CF_PARSE" "$expr")"; then
        ui_warn "a Cloudflare recusou $method ${path%%\?*}: $__cf_out"
        return 1
    fi
}

cf_json() {
    python3 -I -c 'import json, sys; print(json.dumps(dict(zip(sys.argv[1::2], sys.argv[2::2]))))' "$@"
}

token_instructions() {
    ui_info "a instalação usa um token de API da Cloudflare só deste projeto (o do Caddy não serve)"
    ui_info "como criar (2 minutos):"
    ui_info "  1. abra https://dash.cloudflare.com/profile/api-tokens → Create Token → Custom token (Get started)"
    ui_info "  2. nome: astro mailserver; permissões (Add more para cada linha):"
    ui_info "       Account → Workers Scripts → Edit"
    ui_info "       Account → Workers KV Storage → Edit"
    ui_info "       Zone → Email Routing Rules → Edit"
    ui_info "       Zone → Zone Settings → Edit"
    ui_info "       Zone → Zone → Read"
    ui_info "       Zone → DNS → Read"
    ui_info "  3. Account Resources: Include → a sua conta; Zone Resources: Include → Specific zone → $1"
    ui_info "  4. deixe sem expiração (se expirar, os e-mails param de chegar)"
    ui_info "  5. Continue to summary → Create Token, copie o token (ele só aparece uma vez)"
}

zone_lookup() {
    local domain=$1 zone=$1 found
    while [[ $zone == *.* ]]; do
        if cf_call found '" ".join([r[0]["id"], r[0]["account"]["id"], r[0]["name"]]) if r else ""' GET "zones?name=$zone" \
            && [[ -n $found ]]; then
            read -r ZONE_ID ACCOUNT_ID ZONE_NAME <<< "$found"
            return 0
        fi
        zone="${zone#*.}"
    done
    ui_warn "o token não enxerga a zona de $domain: ele precisa de Zone → Zone → Read nessa zona"
    return 1
}

check_token() {
    local domain=$1 status
    if ! cf_call status 'r.get("status")' GET user/tokens/verify || [[ $status != active ]]; then
        ui_warn "token inválido ou inativo na Cloudflare"
        return 1
    fi
    zone_lookup "$domain" || return 1
    ui_ok "token válido com acesso à zona $ZONE_NAME"
}

configure() {
    ui_step "Configuração"
    local address domains nc_user="" password domain
    if config_reuse; then
        address="$(env_get MAIL_ADDRESS)"
        domains="$(env_get ALLOWED_DOMAINS "$(domains_from_senders "$(env_get ALLOWED_SENDERS)")")"
        nc_user="$(env_get NEXTCLOUD_USER)"
        TOKEN="$(env_get CLOUDFLARE_API_TOKEN)"
        ui_ok "configuração existente mantida"
    else
        domain="$(proxy_domain)"
        ui_info "endereço que vai receber os e-mails encaminhados, num domínio sem outro e-mail (ex.: o domínio do astro)"
        ui_input address "endereço da caixa" "$(env_get MAIL_ADDRESS "${domain:+inbox@$domain}")" is_email
        ui_info "só os e-mails destes domínios (com SPF ou DMARC válidos) vão para a entrada; os outros vão para a pasta $QUARANTINE"
        ui_input domains "domínios autorizados, separados por vírgula (ex.: o domínio do seu e-mail)" \
            "$(env_get ALLOWED_DOMAINS "$(domains_from_senders "$(env_get ALLOWED_SENDERS)")")" is_domains
        if [[ -x ../nextcloud/project.sh ]] && ../nextcloud/project.sh status; then
            ui_input nc_user "usuário do Nextcloud que recebe a caixa no app Mail" \
                "$(env_get NEXTCLOUD_USER "$(env_get ADMIN_USER "" "$ASTRO_HOME/nextcloud/.env")")" is_name
        fi
        TOKEN=""
    fi

    if [[ -z $TOKEN ]] || ! check_token "${address#*@}"; then
        token_instructions "${address#*@}"
        while true; do
            ui_secret TOKEN "token de API da Cloudflare"
            check_token "${address#*@}" && break
        done
    fi

    password="$(env_get IMAP_PASSWORD)"
    [[ -n $password ]] || password="$(openssl rand -base64 30 | tr -dc 'A-Za-z0-9')"

    (
        umask 077
        printf "MAIL_ADDRESS='%s'\nALLOWED_DOMAINS='%s'\nNEXTCLOUD_USER='%s'\nCLOUDFLARE_API_TOKEN='%s'\nIMAP_PASSWORD='%s'\nZONE_ID='%s'\nZONE_NAME='%s'\nACCOUNT_ID='%s'\n" \
            "$address" "$domains" "$nc_user" "$TOKEN" "$password" "$ZONE_ID" "$ZONE_NAME" "$ACCOUNT_ID" > "$ENV_FILE.new"
        grep '^KV_ID=' "$ENV_FILE" >> "$ENV_FILE.new" 2>/dev/null || true
    )
    mv "$ENV_FILE.new" "$ENV_FILE"
    ui_ok "configuração salva em $ENV_FILE"
}

env_put() {
    sed -i "/^$1=/d" "$ENV_FILE"
    printf "%s='%s'\n" "$1" "$2" >> "$ENV_FILE"
}

routing_mx() {
    cf_call ROUTING_MX '" ".join(x["content"] for x in r)' GET "zones/$2/dns_records?type=MX&name=$1"
}

routing_body() {
    if [[ $1 == "$2" ]]; then
        printf '{}'
    else
        cf_json name "$1"
    fi
}

routing_ensure() {
    local domain=$1 zone=$2 zone_name=$3 ignored i
    routing_mx "$domain" "$zone" || ui_fail "não foi possível ler os registros MX de $domain"
    if [[ $ROUTING_MX == *mx.cloudflare.net* ]]; then
        ui_ok "Email Routing ativo em $domain (MX da Cloudflare)"
        return 0
    fi
    if [[ -n $ROUTING_MX ]]; then
        ui_error "$domain já recebe e-mail por $ROUTING_MX"
        ui_fail "ativar o Email Routing desviaria esse e-mail: use um endereço num domínio sem e-mail (ex.: o domínio do astro)"
    fi
    ui_info "ativando o Email Routing em $domain (a Cloudflare cria e trava os registros MX e SPF)..."
    if ! cf_call ignored 'None' POST "zones/$zone/email/routing/dns" \
            -H 'Content-Type: application/json' --data-binary "$(routing_body "$domain" "$zone_name")"; then
        ui_fail "não foi possível ativar o Email Routing (se a Cloudflare falou em permissão, o token precisa de Zone → Zone Settings → Edit)"
    fi
    for ((i = 0; i < 24; i++)); do
        routing_mx "$domain" "$zone" || true
        if [[ $ROUTING_MX == *mx.cloudflare.net* ]]; then
            ui_ok "Email Routing ativo em $domain (MX da Cloudflare)"
            return 0
        fi
        sleep 5
    done
    ui_fail "o Email Routing foi pedido, mas os MX da Cloudflare não apareceram em 2 minutos: rode a instalação de novo"
}

worker_publish() {
    local kv=$1 metadata ignored
    metadata="$(python3 -I -c '
import json, sys
kv, domains, date = sys.argv[1:]
print(json.dumps({
    "main_module": "worker.js",
    "compatibility_date": date,
    "bindings": [
        {"type": "kv_namespace", "name": "MAIL", "namespace_id": kv},
        {"type": "plain_text", "name": "ALLOWED_DOMAINS", "text": domains},
    ],
}))' "$kv" "$(env_get ALLOWED_DOMAINS)" "$COMPATIBILITY_DATE")"
    cf_call ignored 'None' PUT "accounts/$ACCOUNT_ID/workers/scripts/$WORKER" \
        -F "metadata=$metadata;type=application/json" \
        -F "worker.js=@worker.js;type=application/javascript+module" || ui_fail "não foi possível publicar o Worker"
    ui_ok "Worker $WORKER publicado (domínios autorizados: $(env_get ALLOWED_DOMAINS))"
}

cloudflare_setup() {
    ui_step "Cloudflare"
    local address sub kv rules rule_id body
    address="$(env_get MAIL_ADDRESS)"
    sub="${address#*@}"
    TOKEN="$(env_get CLOUDFLARE_API_TOKEN)"
    ZONE_ID="$(env_get ZONE_ID)"
    ACCOUNT_ID="$(env_get ACCOUNT_ID)"

    routing_ensure "$sub" "$ZONE_ID" "$(env_get ZONE_NAME)"

    cf_call kv "next((x[\"id\"] for x in r if x[\"title\"] == \"$KV_TITLE\"), \"\")" GET \
        "accounts/$ACCOUNT_ID/storage/kv/namespaces?per_page=100" || ui_fail "não foi possível listar os KV"
    if [[ -z $kv ]]; then
        cf_call kv 'r["id"]' POST "accounts/$ACCOUNT_ID/storage/kv/namespaces" \
            -H 'Content-Type: application/json' --data-binary "$(cf_json title "$KV_TITLE")" || ui_fail "não foi possível criar o KV"
        ui_ok "KV $KV_TITLE criado (guarda cada e-mail até o astro buscar)"
    else
        ui_ok "KV $KV_TITLE já existe"
    fi
    env_put KV_ID "$kv"

    worker_publish "$kv"

    cf_call rule_id "next((x[\"id\"] for x in r if any(m.get(\"value\") == \"$address\" for m in x.get(\"matchers\", []))), \"\")" \
        GET "zones/$ZONE_ID/email/routing/rules?per_page=50" || ui_fail "não foi possível listar as regras do Email Routing"
    body="$(python3 -I -c '
import json, sys
address, worker = sys.argv[1:]
print(json.dumps({
    "name": "astro mailserver",
    "enabled": True,
    "matchers": [{"type": "literal", "field": "to", "value": address}],
    "actions": [{"type": "worker", "value": [worker]}],
}))' "$address" "$WORKER")"
    if [[ -n $rule_id ]]; then
        cf_call rules 'None' PUT "zones/$ZONE_ID/email/routing/rules/$rule_id" \
            -H 'Content-Type: application/json' --data-binary "$body" || ui_fail "não foi possível atualizar a regra"
    else
        cf_call rules 'None' POST "zones/$ZONE_ID/email/routing/rules" \
            -H 'Content-Type: application/json' --data-binary "$body" || ui_fail "não foi possível criar a regra"
    fi
    ui_ok "regra do Email Routing: $address → Worker $WORKER"
}

write_users() {
    local hash
    mkdir -p "$STATE/data/vmail"
    hash="$(printf '%s' "$(env_get IMAP_PASSWORD)" | openssl passwd -6 -stdin)"
    (
        umask 077
        printf '%s:{SHA512-CRYPT}%s\n' "$MAIL_USER" "$hash" > "$STATE/data/users"
    )
    podman unshare chown 0:0 "$STATE/data/users"
    chmod 644 "$STATE/data/users"
}

start_container() {
    local log
    remove_container
    write_users
    if ! log="$(compose up -d 2>&1)"; then
        printf '%s\n' "$log" | ui_prefix >&2
        ui_fail "falha ao subir o container"
    fi
    if ! timeout 60 bash -c "until podman logs $CONTAINER 2>&1 | grep -q 'starting up'; do sleep 1; done"; then
        podman logs --tail 20 "$CONTAINER" 2>&1 | ui_prefix >&2
        ui_fail "o Dovecot não iniciou em 60s"
    fi
    sleep 2
    podman exec "$CONTAINER" doveadm mailbox create -u "$MAIL_USER" "$QUARANTINE" >/dev/null 2>&1 || true
    ui_ok "container $CONTAINER rodando (IMAP só na rede interna dos containers)"
}

fetch_units() {
    mkdir -p "$UNIT_DIR"
    printf '[Unit]\nDescription=astro mailserver: busca os e-mails na Cloudflare\nAfter=network-online.target\n\n[Service]\nType=oneshot\nEnvironment=ASTRO_PLAIN=1\nExecStart=%s fetch\n' \
        "$PWD/project.sh" > "$UNIT_DIR/$FETCH_UNIT.service"
    {
        printf '[Unit]\nDescription=astro mailserver: confere a campainha de 5 em 5 minutos, das 08:00 às 20:00\n\n[Timer]\n'
        printf 'OnCalendar=%s\n' "${FETCH_CALENDAR[@]}"
        printf '\n[Install]\nWantedBy=timers.target\n'
    } > "$UNIT_DIR/$FETCH_UNIT.timer"
    systemctl --user daemon-reload
    systemctl --user enable -q --now "$FETCH_UNIT.timer"
    ui_ok "campainha conferida de 5 em 5 minutos, das 08:00 às 20:00; fora desse horário, os e-mails esperam na Cloudflare ($FETCH_UNIT.timer)"
}

nc_occ_secret() {
    local secret=$1
    shift
    MAILSERVER_SECRET="$secret" podman exec -i -e MAILSERVER_SECRET -u www-data "$NEXTCLOUD" php < <(python3 -I -c '
import json, sys
args = json.dumps(["occ", *sys.argv[1:]])
print(f"""<?php
$_SERVER["argv"] = array_map(fn($a) => $a === "@secret" ? getenv("MAILSERVER_SECRET") : $a, json_decode({json.dumps(args)}, true));
$argv = $_SERVER["argv"];
$argc = count($argv);
chdir("/var/www/html");
require "/var/www/html/console.php";
""")' "$@")
}

nc_account_id() {
    podman exec -u www-data "$NEXTCLOUD" php occ mail:account:export "$1" --output=json 2>/dev/null | python3 -I -c '
import json, sys
try:
    accounts = json.load(sys.stdin)
except ValueError:
    accounts = []
print(next((str(a["id"]) for a in accounts if str(a.get("email", "")).lower() == sys.argv[1].lower()), ""))
' "$2" || true
}

nextcloud_mail() {
    local user address command log
    user="$(env_get NEXTCLOUD_USER)"
    [[ -n $user ]] || return 0
    ui_step "Nextcloud Mail"
    if ! podman container exists "$NEXTCLOUD"; then
        ui_warn "Nextcloud não está rodando: a conta no app Mail fica para a próxima instalação"
        return 0
    fi
    address="$(env_get MAIL_ADDRESS)"
    if ! podman exec -u www-data "$NEXTCLOUD" php occ app:list --output=json 2>/dev/null | grep -q '"mail":'; then
        ui_info "instalando o app Mail no Nextcloud..."
        if ! log="$(podman exec -u www-data "$NEXTCLOUD" php occ app:install mail 2>&1)"; then
            printf '%s\n' "$log" | ui_prefix >&2
            ui_warn "não foi possível instalar o app Mail"
            return 0
        fi
    fi
    podman exec -u www-data "$NEXTCLOUD" php occ app:enable mail >/dev/null
    if [[ -n $(nc_account_id "$user" "$address") ]]; then
        ui_ok "conta $address já existe no Mail de $user"
        return 0
    fi
    command=mail:account:create
    if podman exec -u www-data "$NEXTCLOUD" php occ list mail 2>/dev/null | grep -q 'mail:account:create-imap'; then
        command=mail:account:create-imap
    fi
    if ! log="$(nc_occ_secret "$(env_get IMAP_PASSWORD)" "$command" "$user" "Astro Inbox" "$address" \
            "$CONTAINER" "$IMAP_PORT" none "$MAIL_USER" @secret \
            "$CONTAINER" "$SMTP_PORT" none "$MAIL_USER" @secret 2>&1)"; then
        printf '%s\n' "$log" | ui_prefix >&2
        ui_warn "não foi possível criar a conta no app Mail de $user"
        return 0
    fi
    ui_ok "conta \"Astro Inbox\" ($address) criada no app Mail de $user (só leitura: não envia e-mails)"
}

cmd_install() {
    state_setup
    configure
    cloudflare_setup

    ui_step "Caixa de e-mail"
    start_container
    fetch_units
    cmd_fetch force || true

    nextcloud_mail

    ui_step "Próximo passo"
    ui_info "encaminhe os e-mails para $(env_get MAIL_ADDRESS) (no Proton: filtro com encaminhamento automático)"
    ui_info "e-mails de domínios fora da lista ficam na pasta $QUARANTINE (ex.: a confirmação do encaminhamento)"
}

kv_path() {
    printf 'accounts/%s/storage/kv/namespaces/%s' "$(env_get ACCOUNT_ID)" "$(env_get KV_ID)"
}

mail_subject() {
    python3 -I -c '
import email, email.policy, sys
with open(sys.argv[1], "rb") as f:
    message = email.message_from_binary_file(f, policy=email.policy.default)
print(str(message.get("subject", "(sem assunto)")).replace("\n", " ")[:120])
' "$1" 2>/dev/null || echo "(assunto ilegível)"
}

fetch_one() {
    local key=$1 file=$2 code folder=()
    code="$(cf GET "$(kv_path)/values/$key" -o "$file" -w '%{http_code}')" || code=000
    [[ $code == 200 ]] || { ui_warn "não foi possível baixar $key (HTTP $code)"; return 1; }
    [[ $key == quarentena.* ]] && folder=(-m "$QUARANTINE")
    if ! podman exec -i "$CONTAINER" doveadm save -u "$MAIL_USER" "${folder[@]}" < "$file" >/dev/null 2>&1; then
        ui_warn "o Dovecot não aceitou $key"
        return 1
    fi
    local done_
    cf_call done_ 'None' DELETE "$(kv_path)/values/$key" || return 1
    ui_ok "entregue${folder[*]:+ na $QUARANTINE}: $(mail_subject "$file")"
}

cmd_fetch() {
    [[ -f $ENV_FILE ]] || ui_fail "mailserver não instalado"
    TOKEN="$(env_get CLOUDFLARE_API_TOKEN)"
    exec 7>"$LOCK"
    if ! flock -n 7; then
        ui_info "outra busca em andamento"
        return 0
    fi
    local keys key tmp failed=0 count=0 code ignored
    if [[ ${1:-} != force ]]; then
        code="$(cf GET "$(kv_path)/values/$DOORBELL" -o /dev/null -w '%{http_code}' 2>/dev/null)" || code=000
        if [[ $code == 404 ]]; then
            notify_resolved fetch "e-mails voltaram a chegar na caixa local"
            return 0
        fi
        if [[ $code != 200 ]]; then
            notify_problem fetch "não foi possível consultar a Cloudflare (HTTP $code: token, rede ou KV)"
            return 1
        fi
        cf_call ignored 'None' DELETE "$(kv_path)/values/$DOORBELL" || true
    fi
    if ! cmd_status; then
        notify_problem fetch "a caixa de e-mail ($CONTAINER) não está rodando: os e-mails ficam guardados na Cloudflare"
        ui_fail "container $CONTAINER parado"
    fi
    if ! cf_call keys '"\n".join(x["name"] for x in r)' GET "$(kv_path)/keys?limit=1000"; then
        notify_problem fetch "não foi possível consultar os e-mails na Cloudflare (token, rede ou KV)"
        return 1
    fi
    tmp="$(mktemp -d "$STATE/.fetch.XXXXXX")"
    while read -r key; do
        [[ $key =~ ^(inbox|quarentena)\.[0-9]+\.[0-9a-f-]+$ ]] || continue
        if fetch_one "$key" "$tmp/mail"; then
            count=$((count + 1))
        else
            failed=$((failed + 1))
        fi
    done <<< "$keys"
    rm -rf "$tmp"
    if ((failed)); then
        notify_problem fetch "$failed e-mail(s) não chegaram à caixa local (ficam na Cloudflare e são tentados de novo)"
        return 1
    fi
    notify_resolved fetch "e-mails voltaram a chegar na caixa local"
    ((count == 0)) || ui_ok "$count e-mail(s) novo(s)"
}

quarantine_release() {
    local domain=$1 count
    count="$({ podman exec "$CONTAINER" doveadm search -u "$MAIL_USER" mailbox "$QUARANTINE" header X-Astro-Mailserver "@$domain" 2>/dev/null || true; } | wc -l)"
    ((count > 0)) || return 0
    ui_confirm "mover da $QUARANTINE para a entrada os $count e-mail(s) de @$domain?" y || return 0
    podman exec "$CONTAINER" doveadm move -u "$MAIL_USER" INBOX mailbox "$QUARANTINE" header X-Astro-Mailserver "@$domain" >/dev/null 2>&1
    ui_ok "$count e-mail(s) de @$domain movidos para a entrada"
}

action_domains() {
    local index list=() chosen=() domain i kept=() added=()
    TOKEN="$(env_get CLOUDFLARE_API_TOKEN)"
    ACCOUNT_ID="$(env_get ACCOUNT_ID)"
    while true; do
        ui_step "Domínios autorizados"
        IFS=, read -ra list <<< "$(env_get ALLOWED_DOMAINS "$(domains_from_senders "$(env_get ALLOWED_SENDERS)")")"
        if ((${#list[@]})); then
            for domain in "${list[@]}"; do ui_info "@$domain"; done
        else
            ui_warn "nenhum domínio autorizado: tudo vai para a $QUARANTINE"
        fi
        ui_menu index "O que fazer?" "Adicionar domínio" "Remover domínios" "Voltar"
        case $index in
            0)
                ui_input domain "domínio (ex.: empresa.com.br)" "" is_hostname
                if [[ " ${list[*]} " == *" $domain "* ]]; then
                    ui_info "@$domain já está autorizado"
                    continue
                fi
                list+=("$domain")
                added+=("$domain")
                ;;
            1)
                ((${#list[@]})) || continue
                ui_checklist chosen "Quais domínios remover?" --esc "${list[@]/#/@}"
                ((${#chosen[@]})) || continue
                kept=()
                for i in "${!list[@]}"; do
                    [[ " ${chosen[*]} " == *" $i "* ]] || kept+=("${list[i]}")
                done
                list=("${kept[@]}")
                ;;
            *) return 0 ;;
        esac
        env_put ALLOWED_DOMAINS "$(IFS=,; echo "${list[*]}")"
        worker_publish "$(env_get KV_ID)"
        for domain in "${added[@]}"; do quarantine_release "$domain"; done
        added=()
    done
}

action_access() {
    ui_step "Dados de acesso (IMAP)"
    ui_info "servidor: $CONTAINER, porta $IMAP_PORT, sem criptografia (só na rede interna dos containers)"
    ui_info "usuário: $MAIL_USER"
    ui_info "senha: em $ENV_FILE (IMAP_PASSWORD)"
}

cmd_action() {
    case "${1:-}" in
        fetch)   ui_step "Busca"; cmd_fetch force ;;
        domains) action_domains ;;
        access) action_access ;;
        *)      ui_fail "ação desconhecida: ${1:-}" ;;
    esac
}

cmd_remote() {
    case "${1:-}" in
        fetch) cmd_fetch force ;;
        *)     echo "ação desconhecida: ${1:-}"; return 1 ;;
    esac
}

cmd_restore() {
    remove_container
    state_restore "$1"
    start_container
    fetch_units
}

cloudflare_remove() {
    TOKEN="$(env_get CLOUDFLARE_API_TOKEN)"
    [[ -n $TOKEN ]] || return 0
    local zone account kv address rule_id ignored
    zone="$(env_get ZONE_ID)"
    account="$(env_get ACCOUNT_ID)"
    kv="$(env_get KV_ID)"
    address="$(env_get MAIL_ADDRESS)"
    if [[ -n $zone ]] && cf_call rule_id "next((x[\"id\"] for x in r if any(m.get(\"value\") == \"$address\" for m in x.get(\"matchers\", []))), \"\")" \
            GET "zones/$zone/email/routing/rules?per_page=50" && [[ -n $rule_id ]]; then
        cf_call ignored 'None' DELETE "zones/$zone/email/routing/rules/$rule_id" && ui_ok "regra do Email Routing removida"
    fi
    if [[ -n $account ]] && cf_call ignored 'None' DELETE "accounts/$account/workers/scripts/$WORKER" 2>/dev/null; then
        ui_ok "Worker $WORKER removido"
    fi
    if [[ -n $account && -n $kv ]] && cf_call ignored 'None' DELETE "accounts/$account/storage/kv/namespaces/$kv"; then
        ui_ok "KV $KV_TITLE removido (com os e-mails ainda não buscados)"
    fi
    if [[ -n $zone ]] && cf_call ignored 'None' DELETE "zones/$zone/email/routing/dns" \
            -H 'Content-Type: application/json' --data-binary "$(routing_body "${address#*@}" "$(env_get ZONE_NAME)")"; then
        ui_ok "Email Routing desligado em ${address#*@} (registros MX e SPF removidos)"
    else
        ui_warn "desligue o Email Routing de ${address#*@} pelo painel: Email → Email Routing → Settings"
    fi
}

cmd_remove() {
    ui_step "Remoção"
    systemctl --user disable -q --now "$FETCH_UNIT.timer" 2>/dev/null || true
    rm -f "$UNIT_DIR/$FETCH_UNIT.timer" "$UNIT_DIR/$FETCH_UNIT.service"
    systemctl --user daemon-reload
    remove_container
    images_remove
    ui_ok "caixa de e-mail e busca removidas"
    if [[ -f $ENV_FILE ]]; then
        cloudflare_remove || true
    fi
    local user id
    user="$(env_get NEXTCLOUD_USER)"
    if [[ -n $user ]] && podman container exists "$NEXTCLOUD"; then
        id="$(nc_account_id "$user" "$(env_get MAIL_ADDRESS)")"
        if [[ -n $id ]] && podman exec -u www-data "$NEXTCLOUD" php occ mail:account:delete "$id" >/dev/null 2>&1; then
            ui_ok "conta \"Astro Inbox\" removida do app Mail de $user"
        fi
    fi
    state_purge
}

case "${1:-}" in
    describe)       cmd_describe ;;
    status)         cmd_status ;;
    actions)        cmd_actions ;;
    action)         shift; cmd_action "$@" ;;
    remote-actions) cmd_remote_actions ;;
    remote)         shift; cmd_remote "$@" ;;
    help)           cmd_help ;;
    install)        cmd_install ;;
    remove)         cmd_remove ;;
    restore)        shift; cmd_restore "$1" ;;
    fetch)          cmd_fetch ;;
    *)              ui_fail "uso: $0 describe | status | actions | action <id> | remote-actions | remote <id> | help | install | remove | restore <pasta> | fetch" ;;
esac
