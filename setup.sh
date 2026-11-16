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

ORDER=(caddy adguard cockpit nextcloud mailserver discord n8n sunshine samba desktop rclone)
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
    [[ -z ${skipped[*]:-} ]] || ui_info "pulados: $(join "${skipped[@]}")"
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
    if [[ $redo != *" $step "* ]]; then
        ui_step "$(step_label "$step")"
        if step_done "$step"; then
            ui_info "concluída em $(step_date "$step"), pulada"
        else
            ui_info "não marcada, pulada"
        fi
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
    local name step label status first=true redo=" " i chosen=() steps=(maquina discos "${PROJECTS[@]}") labels=() preset=""
    local failed=() succeeded=() skipped=() any_done=false
    for i in "${!steps[@]}"; do
        step=${steps[i]}
        label="$(step_label "$step")"
        if step_done "$step"; then
            any_done=true
            status="concluída em $(step_date "$step")"
        else
            status="pendente"
            preset+="$i "
        fi
        labels+=("$(printf '%s%*s %s' "$label" $((18 - ${#label})) '' "$status")")
    done
    if $any_done; then
        ui_checklist chosen "Quais etapas rodar? (as pendentes já vêm marcadas)" --all --esc --selected "$preset" "${labels[@]}"
        if ((UI_CANCELLED)); then
            return 0
        fi
        if ((${#chosen[@]} == 0)); then
            ui_info "nenhuma etapa marcada, nada a fazer"
            return 0
        fi
        for i in "${chosen[@]}"; do
            redo+="${steps[i]} "
        done
    else
        redo+="${steps[*]} "
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
    local answer i name failed=() succeeded=()
    ui_step "Implodir Astro"
    ui_warn "isto desfaz tudo o que o Astro criou nesta máquina:"
    ui_info "  containers, imagens, serviços e a configuração de todos os projetos ($ASTRO_HOME)"
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

domain_before() {
    local new=$1
    ui_step "Antes de trocar (na Cloudflare)"
    ui_info "1. o domínio $new precisa estar na sua conta da Cloudflare (comprado lá, já está; se não, aponte os"
    ui_info "   nameservers dele para a Cloudflare e espere a zona ficar ativa)"
    ui_info "2. o token do Caddy precisa enxergar a zona nova: https://dash.cloudflare.com/profile/api-tokens →"
    ui_info "   o token do Caddy → Edit → Zone Resources → Include → Specific zone → $new (Zone:Read e DNS:Edit)"
    ui_info "   (se ele não enxergar, a reinstalação do Caddy pede um token novo)"
    if [[ -f $ASTRO_HOME/mailserver/.env ]]; then
        ui_info "3. o mesmo vale para o token do mailserver, se ele já estiver instalado"
    fi
}

domain_after() {
    local new=$1 lan_ip
    lan_ip="$(host_lan_ip)"
    ui_step "Depois de trocar (fora da máquina)"
    ui_info "- Tailscale: https://login.tailscale.com/admin/dns → Nameservers: um Split DNS $new → $lan_ip"
    ui_info "  e apague o do domínio antigo (sem isso, os endereços novos não abrem de fora de casa)"
    ui_info "- apps do Nextcloud (celular e computador) e agendas/contatos: entre de novo com o endereço novo"
    ui_info "- favoritos e senhas salvas no navegador ou no gerenciador de senhas: atualize os endereços"
    ui_info "- o Moonlight não muda (usa o IP); o painel do Sunshine passa a ter o endereço novo"
    if [[ -f $ASTRO_HOME/mailserver/.env ]]; then
        ui_info "- mailserver: ative o Email Routing em $new pela Cloudflare (o assistente do mailserver mostra como)"
        ui_info "  e troque o encaminhamento no seu e-mail para $(env_get MAIL_ADDRESS "" "$ASTRO_HOME/mailserver/.env")"
    fi
    ui_info "- o domínio antigo continua com o que já tinha fora do astro (site, e-mail): nada muda nele"
}

domain_rewrite() {
    python3 -I -c '
import os, re, sys
home, old, new = sys.argv[1:]
keys = {"CADDY_DOMAIN", "PANEL_HOST", "ADGUARD_REWRITES", "COCKPIT_HOST", "NEXTCLOUD_HOST", "SUNSHINE_HOST", "N8N_HOST"}

def host(value):
    if value == old:
        return new
    if value.endswith("." + old):
        return value[: -len(old)] + new
    return value

for name in sorted(os.listdir(home)):
    path = os.path.join(home, name, ".env")
    if name.startswith(".") or not os.path.isfile(path):
        continue
    lines, changed = [], False
    for line in open(path, encoding="utf-8").read().splitlines():
        match = re.match(r"^([A-Z0-9_]+)=\x27(.*)\x27$", line)
        if match:
            key, value = match.groups()
            result = value
            if key in keys:
                result = ",".join(host(item) for item in value.split(","))
            elif key == "MAIL_ADDRESS" and "@" in value:
                result = value.split("@")[0] + "@" + new
            if result != value:
                print(f"{name}\x1f{key}\x1f{value}\x1f{result}")
                line = f"{key}=\x27{result}\x27"
                changed = True
        lines.append(line)
    if changed:
        with open(path + ".new", "w", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")
        os.chmod(path + ".new", 0o600)
        os.replace(path + ".new", path)

def routes(path, label):
    if not os.path.isfile(path):
        return
    lines = []
    for line in open(path, encoding="utf-8").read().splitlines():
        parts = line.split(" ", 1)
        if parts and parts[0] and host(parts[0]) != parts[0]:
            if label:
                print(f"caddy\x1f{label}\x1f{parts[0]}\x1f{host(parts[0])}")
            parts[0] = host(parts[0])
        lines.append(" ".join(parts))
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + ("\n" if lines else ""))

routes(os.path.join(home, "caddy", ".routes"), "rota manual")
for name in os.listdir(home):
    routes(os.path.join(home, name, ".proxy"), "")
' "$ASTRO_HOME" "$1" "$2"
}

change_domain() {
    local old new name key before after backup affected=() failed=() succeeded=() skipped=() redo
    ui_step "Trocar o domínio"
    old="$(env_get CADDY_DOMAIN "" "$ASTRO_HOME/caddy/.env")"
    [[ -n $old ]] || { ui_warn "o Caddy não está configurado: não há domínio para trocar"; return 0; }
    ui_info "domínio atual: $old"
    ui_input new "domínio novo" "" is_hostname
    if [[ $new == "$old" ]]; then
        ui_warn "é o mesmo domínio, nada mudou"
        return 0
    fi
    domain_before "$new"
    ui_confirm "trocar $old por $new em todos os serviços?" n || { ui_warn "cancelado, nada mudou"; return 0; }

    backup="$ASTRO_HOME/.troca-de-dominio/$(date +%Y-%m-%d_%H%M%S)"
    mkdir -p "$backup"
    chmod 700 "$ASTRO_HOME/.troca-de-dominio" "$backup"
    for name in "$ASTRO_HOME"/*/.env; do
        cp -p "$name" "$backup/$(basename "$(dirname "$name")").env"
    done
    [[ ! -f $ASTRO_HOME/caddy/.routes ]] || cp -p "$ASTRO_HOME/caddy/.routes" "$backup/caddy.routes"
    ui_ok "configuração atual guardada em $backup"

    ui_step "Endereços"
    while IFS=$'\x1f' read -r name key before after; do
        ui_ok "$name: $key $before → $after"
        [[ " ${affected[*]} " == *" $name "* ]] || affected+=("$name")
    done < <(domain_rewrite "$old" "$new")

    redo=" ${affected[*]} "
    for name in "${PROJECTS[@]}"; do
        [[ $redo == *" $name "* ]] || continue
        if ! project "$name" status; then
            ui_info "$name: não instalado, o endereço novo vale na próxima instalação"
            continue
        fi
        if grep -q '^    domain)' "$name/project.sh"; then
            run_step "$name" project "$name" domain "$old" "$new"
        else
            run_step "$name" env ASTRO_REUSE_CONFIG=1 "./$name/project.sh" install
        fi
    done
    summary || true
    domain_after "$new"
}

administration() {
    local index globals name id
    while true; do
        global_actions
        globals=${#GLOBAL_IDS[@]}
        ui_menu index "Administração" "Discos da máquina" "Trocar o domínio" "${GLOBAL_LABELS[@]}" "Implodir Astro" "Voltar"
        if ((index == 0)); then
            disk_manage || true
        elif ((index == 1)); then
            change_domain || true
        elif ((index <= globals + 1)); then
            read -r name id <<< "${GLOBAL_IDS[index - 2]}"
            project "$name" action "$id" || true
        elif ((index == globals + 2)); then
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
