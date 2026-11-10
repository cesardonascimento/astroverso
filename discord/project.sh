#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"

ASTRO_PROJECT=discord
source ../lib/ui.sh
source ../lib/host.sh
source ../lib/env.sh
source ../lib/notify.sh

CONTAINER=astro-discord
FILA="$STATE/fila"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
RUNNER=astro-discord-runner
DISCORD_API=https://discord.com/api/v10
PERMISSIONS=84992

cmd_describe() {
    echo "Discord: avisos do servidor e comandos /astro por um bot"
}

cmd_status() {
    podman container exists "$CONTAINER"
}

cmd_actions() {
    printf '%s\n' \
        "test|Enviar uma mensagem de teste" \
        "commands|Listar os comandos disponíveis no Discord"
}

remove_container() {
    compose down >/dev/null 2>&1 || true
    podman rm -f "$CONTAINER" >/dev/null 2>&1 || true
}

stop_all() {
    systemctl --user disable -q --now "$RUNNER.path" 2>/dev/null || true
    remove_container
}

is_snowflake() {
    [[ $1 =~ ^[0-9]{17,20}$ ]] && printf '%s' "$1"
}

is_snowflakes() {
    local item out=()
    for item in ${1//,/ }; do
        is_snowflake "$item" >/dev/null || return 1
        out+=("$item")
    done
    ((${#out[@]})) && printf '%s' "${out[*]}"
}

discord_get() {
    curl -s -m 15 -o "$3" -w '%{http_code}' -H @- "$DISCORD_API/$2" <<< "Authorization: Bot $1"
}

json_field() {
    python3 -I -c 'import json, sys; print(json.load(open(sys.argv[1])).get(sys.argv[2], ""))' "$1" "$2" 2>/dev/null || true
}

token_instructions() {
    ui_info "o bot é uma conta do Discord que só o astro usa. Como criar (2 minutos):"
    ui_info "  1. abra https://discord.com/developers/applications → New Application (ex.: astro)"
    ui_info "  2. menu Bot → Reset Token → copie o token (ele só aparece uma vez)"
    ui_info "  3. ainda em Bot, deixe \"Public Bot\" desligado (só você pode convidá-lo)"
    ui_info "o token é a senha do bot: não aparece na tela e fica só em $ENV_FILE (só $USER lê)"
}

check_token() {
    local token=$1 body code
    body="$(mktemp)"
    code="$(discord_get "$token" users/@me "$body")" || code=000
    if [[ $code != 200 ]]; then
        rm -f "$body"
        ui_warn "o Discord recusou o token (HTTP $code)"
        return 1
    fi
    BOT_ID="$(json_field "$body" id)"
    BOT_NAME="$(json_field "$body" username)"
    rm -f "$body"
    ui_ok "token válido: bot $BOT_NAME"
}

check_channel() {
    local token=$1 channel=$2 body code
    body="$(mktemp)"
    code="$(discord_get "$token" "channels/$channel" "$body")" || code=000
    CHANNEL_NAME="$(json_field "$body" name)"
    rm -f "$body"
    [[ $code == 200 ]]
}

configure() {
    ui_step "Configuração"
    local token channel users
    if [[ -f $ENV_FILE ]] && ui_confirm "usar a configuração já salva em $ENV_FILE?" y; then
        token="$(env_get DISCORD_TOKEN)"
        channel="$(env_get DISCORD_CHANNEL)"
        users="$(env_get DISCORD_USERS)"
        if check_token "$token" && check_channel "$token" "$channel"; then
            ui_ok "configuração existente mantida (canal #$CHANNEL_NAME)"
            return
        fi
        ui_warn "a configuração salva não funciona mais: responda de novo"
    fi

    token_instructions
    while true; do
        ui_secret token "token do bot"
        check_token "$token" && break
    done

    ui_info "no Discord, ligue o Modo desenvolvedor (Configurações → Avançado) para copiar IDs com o botão direito"
    ui_info "convide o bot para o seu servidor por este link (permissões: ver o canal e enviar mensagens):"
    ui_info "  https://discord.com/oauth2/authorize?client_id=$BOT_ID&scope=bot+applications.commands&permissions=$PERMISSIONS"
    while true; do
        ui_input channel "ID do canal dos avisos (botão direito no canal → Copiar ID do canal)" "$(env_get DISCORD_CHANNEL)" is_snowflake
        if check_channel "$token" "$channel"; then
            ui_ok "o bot enxerga o canal #$CHANNEL_NAME"
            break
        fi
        ui_warn "o bot não enxerga esse canal: confira o ID e se ele já foi convidado (link acima)"
    done
    ui_info "só estes usuários podem usar os comandos e os botões"
    ui_input users "IDs dos usuários autorizados, separados por espaço (botão direito no seu nome → Copiar ID do usuário)" \
        "$(env_get DISCORD_USERS)" is_snowflakes

    (
        umask 077
        printf "DISCORD_TOKEN='%s'\nDISCORD_CHANNEL='%s'\nDISCORD_USERS='%s'\n" "$token" "$channel" "$users" > "$ENV_FILE.new"
    )
    mv "$ENV_FILE.new" "$ENV_FILE"
    ui_ok "configuração salva em $ENV_FILE"
}

write_unit() {
    local file="$UNIT_DIR/$1"
    if [[ $(cat "$file" 2>/dev/null) != "$2" ]]; then
        printf '%s\n' "$2" > "$file"
    fi
}

runner_units() {
    mkdir -p "$UNIT_DIR" "$FILA"/{pedidos,respostas,saida,tmp,andamento}
    write_unit "$RUNNER.service" "$(printf '[Unit]\nDescription=astro discord: executa os comandos pedidos pelo bot\n\n[Service]\nType=oneshot\nTimeoutStartSec=1h\nEnvironment=ASTRO_PLAIN=1\nExecStart=%s run\n' "$PWD/runner.sh")"
    write_unit "$RUNNER.path" "$(printf '[Unit]\nDescription=astro discord: fila de comandos do bot\n\n[Path]\nDirectoryNotEmpty=%s\nMakeDirectory=yes\n\n[Install]\nWantedBy=default.target\n' "$FILA/pedidos")"
    systemctl --user daemon-reload
    systemctl --user enable -q --now "$RUNNER.path"
    ui_ok "executor de comandos ativo ($RUNNER): roda só as ações da lista, com o seu usuário"
}

action_test() {
    ui_step "Mensagem de teste"
    cmd_status || ui_fail "o bot não está instalado"
    notify_send "🔔 mensagem de teste: o botão abaixo pede o estado da máquina" "Estado da máquina|host:status|" \
        || ui_fail "a fila de avisos não existe: reinstale o projeto discord"
    ui_ok "mensagem na fila: ela aparece no canal em alguns segundos"
}

action_commands() {
    ui_step "Comandos no Discord"
    ./runner.sh catalog
    python3 -I -c '
import json, sys
for a in json.load(open(sys.argv[1])):
    extra = "  (pede confirmação)" if a["confirmar"] else ""
    print("/astro " + a["id"] + extra + ": " + a["descricao"])
' "$FILA/catalogo.json" | ui_prefix
}

cmd_install() {
    state_setup stop_all .env
    configure

    ui_step "Host"
    host_base

    ui_step "Container"
    local log
    ui_info "construindo a imagem do bot (Python + discord.py)..."
    if ! log="$(compose build 2>&1)"; then
        printf '%s\n' "$log" | ui_prefix >&2
        ui_fail "falha ao construir a imagem"
    fi

    ui_step "Executor de comandos"
    runner_units
    ./runner.sh catalog
    ui_ok "catálogo de comandos gerado"

    remove_container
    if ! log="$(compose up -d 2>&1)"; then
        printf '%s\n' "$log" | ui_prefix >&2
        ui_fail "falha ao subir o container"
    fi
    if ! timeout 60 bash -c "until podman logs $CONTAINER 2>&1 | grep -q 'conectado como'; do sleep 2; done"; then
        podman logs --tail 20 "$CONTAINER" 2>&1 | ui_prefix >&2
        ui_fail "o bot não conectou ao Discord em 60s"
    fi
    podman logs "$CONTAINER" 2>&1 | grep 'conectado como' | tail -1 | ui_prefix
    ui_ok "container $CONTAINER rodando"

    action_test
    ui_info "no Discord, digite /astro e escolha um comando (comece por \"help\")"
    ui_info "no celular, deixe as notificações do canal em \"Todas as mensagens\""
}

cmd_backup() {
    printf 'exclude %s\n' "$FILA"
}

cmd_restore() {
    local log
    stop_all
    state_restore "$1"
    runner_units
    ./runner.sh catalog
    if ! log="$(compose up -d 2>&1)"; then
        printf '%s\n' "$log" | ui_prefix >&2
        ui_fail "falha ao subir o container depois de restaurar"
    fi
    ui_ok "container $CONTAINER rodando com a configuração restaurada"
}

cmd_action() {
    case "${1:-}" in
        test)     action_test ;;
        commands) action_commands ;;
        *)        ui_fail "ação desconhecida: ${1:-}" ;;
    esac
}

cmd_remove() {
    local purge=false
    [[ ${1:-} == --purge ]] && purge=true

    ui_step "Remoção"
    stop_all
    rm -f "$UNIT_DIR/$RUNNER.path" "$UNIT_DIR/$RUNNER.service"
    systemctl --user daemon-reload
    rm -rf -- "$FILA/saida"
    ui_ok "bot e executor de comandos removidos (os avisos deixam de ser enviados)"
    if $purge && [[ -d $FILA ]]; then
        podman unshare rm -rf "$FILA"
        ui_ok "fila apagada ($FILA)"
    fi
    ui_info "token e canal mantidos em $ENV_FILE"
}

case "${1:-}" in
    describe) cmd_describe ;;
    status)   cmd_status ;;
    actions)  cmd_actions ;;
    action)   shift; cmd_action "$@" ;;
    install)  cmd_install ;;
    remove)   shift; cmd_remove "$@" ;;
    backup)   cmd_backup ;;
    restore)  shift; cmd_restore "$1" ;;
    *)        ui_fail "uso: $0 describe | status | actions | action <id> | install | remove [--purge] | backup | restore <pasta>" ;;
esac
