#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"

ASTRO_PROJECT=sunshine
source ../lib/ui.sh
source ../lib/host.sh
source ../lib/env.sh
source ../lib/proxy.sh

REPO=LizardByte/Sunshine
WEB_PORT=47990
STREAM_PORTS=(47984/tcp 47989/tcp 48010/tcp 47998-48000/udp 48002/udp 48010/udp)
GDM_CONFS=(/etc/gdm/custom.conf /etc/gdm3/custom.conf /etc/gdm3/daemon.conf)
UNITS=(/usr/lib/systemd/user/app-dev.lizardbyte.app.Sunshine.service /usr/lib/systemd/user/sunshine.service)
NVIDIA_VENDOR=0x10de
MUTTER_RULE=/etc/udev/rules.d/61-astro-mutter-primary-gpu.rules
DISPLAY_BIN=/usr/local/bin/astro-sunshine-display
PREP_CMD="[{\"do\":\"$DISPLAY_BIN do\",\"undo\":\"$DISPLAY_BIN undo\",\"elevated\":false}]"

cmd_describe() {
    echo "Sunshine: streaming de jogos para o Moonlight, em um usuário próprio com login automático"
}

gdm_conf() {
    local file
    for file in "${GDM_CONFS[@]}"; do
        if [[ -f $file ]]; then
            printf '%s' "$file"
            return 0
        fi
    done
    return 1
}

gdm_autologin_user() {
    local conf
    conf="$(gdm_conf)" || return 0
    sed -n 's/^AutomaticLogin=//p' "$conf"
}

cmd_status() {
    local user
    user="$(env_get GAMES_USER)"
    [[ -n $user ]] && command -v sunshine >/dev/null && [[ $(gdm_autologin_user) == "$user" ]]
}

as_user() {
    local user=$1
    shift
    (cd / && sudo -u "$user" -H "$@")
}

user_manager_running() {
    [[ $(loginctl show-user "$1" -P State 2>/dev/null) == @(active|online) ]]
}

user_session_active() {
    [[ $(loginctl show-user "$1" -P State 2>/dev/null) == active ]]
}

check_games_user() {
    local user=$1
    if [[ $user == "$USER" ]]; then
        ui_warn "use um usuário diferente de $USER, que cuida do homelab"
        return 1
    fi
    id "$user" >/dev/null 2>&1 || return 0
    if (($(id -u "$user") < 1000)); then
        ui_warn "$user é um usuário do sistema"
        return 1
    fi
    if id -nG "$user" | grep -qwE 'wheel|sudo|admin'; then
        ui_warn "$user tem acesso ao sudo; o login automático exige um usuário sem privilégios"
        return 1
    fi
}

configure() {
    ui_step "Configuração"
    if [[ -f .env ]] && ui_confirm "usar a configuração já salva em sunshine/.env?" y; then
        ui_ok "configuração existente mantida"
        return
    fi
    local user host domain
    domain="$(proxy_domain)"
    while true; do
        ui_input user "nome do usuário de jogos (criado se não existir)" "$(env_get GAMES_USER jogos)" is_username
        check_games_user "$user" && break
    done
    ui_input host "endereço do Sunshine no Caddy" "$(env_get SUNSHINE_HOST "sunshine.$(hostname -s)${domain:+.$domain}")" is_hostname
    (
        umask 077
        printf "GAMES_USER='%s'\nSUNSHINE_HOST='%s'\n" "$user" "$host" > .env.new
    )
    mv .env.new .env
    ui_ok "configuração salva em sunshine/.env"
}

create_user() {
    local user=$1
    if id "$user" >/dev/null 2>&1; then
        ui_ok "usuário $user já existe"
    else
        sudo useradd -m -c "Jogos" "$user"
        ui_ok "usuário $user criado, sem senha e sem sudo"
    fi
    as_user "$user" sh -c 'mkdir -p "$HOME/.config" && printf "yes\n" > "$HOME/.config/gnome-initial-setup-done"'
}

desktop_settings() {
    local user=$1
    if ! command -v gsettings >/dev/null || ! gsettings list-schemas 2>/dev/null | grep -qx org.gnome.desktop.lockdown; then
        ui_warn "GNOME não encontrado: desative o bloqueio de tela de $user manualmente"
        return
    fi
    as_user "$user" dbus-run-session -- sh -c '
        gsettings set org.gnome.desktop.screensaver lock-enabled false
        gsettings set org.gnome.desktop.lockdown disable-lock-screen true
        gsettings set org.gnome.desktop.session idle-delay 0
        gsettings set org.gnome.settings-daemon.plugins.power idle-dim false
        gsettings set org.gnome.settings-daemon.plugins.power sleep-inactive-ac-type nothing
        gsettings set org.gnome.settings-daemon.plugins.power sleep-inactive-battery-type nothing
    ' >/dev/null 2>&1
    ui_ok "bloqueio de tela, escurecimento e suspensão desativados para $user"
}

gdm_render() {
    awk -v user="$2" '
        /^AutomaticLogin(Enable)?=/ { next }
        { print }
        /^\[daemon\]/ && user != "" { print "AutomaticLoginEnable=True"; print "AutomaticLogin=" user; done = 1 }
        END { if (!done && user != "") { print "[daemon]"; print "AutomaticLoginEnable=True"; print "AutomaticLogin=" user } }
    ' "$1"
}

autologin() {
    local user=$1 conf wanted
    if ! conf="$(gdm_conf)"; then
        ui_warn "GDM não encontrado: configure o login automático de $user no gerenciador de login"
        return
    fi
    wanted="$(gdm_render "$conf" "$user")"
    if [[ $wanted == "$(cat "$conf")" ]]; then
        ui_ok "login automático já configurado para $user"
        return
    fi
    printf '%s\n' "$wanted" | sudo tee "$conf" >/dev/null
    ui_ok "login automático configurado para $user"
}

autologin_off() {
    local conf wanted
    conf="$(gdm_conf)" || return 0
    [[ -n $(gdm_autologin_user) ]] || return 0
    wanted="$(gdm_render "$conf" "")"
    printf '%s\n' "$wanted" | sudo tee "$conf" >/dev/null
    ui_ok "login automático desativado"
}

installed_version() {
    if rpm -q Sunshine >/dev/null 2>&1; then
        rpm -q --qf '%{VERSION}' Sunshine
    elif dpkg-query -W sunshine >/dev/null 2>&1; then
        dpkg-query -W -f '${Version}' sunshine | cut -d- -f1
    fi
    return 0
}

asset_pattern() {
    local ID VERSION_ID VERSION_CODENAME
    source /etc/os-release
    if command -v dnf >/dev/null && [[ $ID == fedora ]]; then
        printf '\\.fc%s\\.%s\\.rpm$' "$VERSION_ID" "$(uname -m)"
    elif command -v apt-get >/dev/null && [[ $ID == ubuntu ]]; then
        printf '\\+ubuntu%s_%s\\.deb$' "$VERSION_ID" "$(dpkg --print-architecture)"
    elif command -v apt-get >/dev/null && [[ $ID == debian ]]; then
        printf '\\+debian%s_%s\\.deb$' "$VERSION_CODENAME" "$(dpkg --print-architecture)"
    else
        return 1
    fi
}

latest_release() {
    curl -fsSL -m 30 "https://api.github.com/repos/$REPO/releases/latest" | python3 -I -c '
import json, re, sys
data = json.load(sys.stdin)
for asset in data["assets"]:
    if re.search(sys.argv[1], asset["name"]):
        digest = (asset.get("digest") or "").removeprefix("sha256:")
        print(data["tag_name"].lstrip("v"), asset["name"], asset["browser_download_url"], digest or "-")
        break
' "$1"
}

install_sunshine() {
    local pattern release version name url digest current tmp
    pattern="$(asset_pattern)" || ui_fail "sistema sem pacote oficial do Sunshine (Fedora, Ubuntu ou Debian)"
    release="$(latest_release "$pattern")" || ui_fail "não foi possível consultar as versões do Sunshine no GitHub"
    [[ -n $release ]] || ui_fail "a versão mais recente do Sunshine não tem pacote para este sistema"
    read -r version name url digest <<< "$release"
    current="$(installed_version)"
    if [[ $current == "$version" ]]; then
        ui_ok "Sunshine $version já instalado (versão mais recente)"
        return
    fi
    [[ $digest != - ]] || ui_fail "o GitHub não publicou o SHA-256 de $name"

    ui_info "baixando $name..."
    tmp="$(mktemp -d)"
    chmod 755 "$tmp"
    if ! curl -fsSL --retry 3 -o "$tmp/$name" "$url"; then
        rm -rf "$tmp"
        ui_fail "falha ao baixar $url"
    fi
    if ! printf '%s  %s\n' "$digest" "$tmp/$name" | sha256sum -c --status; then
        rm -rf "$tmp"
        ui_fail "o SHA-256 de $name não confere com o publicado no GitHub"
    fi
    ui_ok "SHA-256 conferido"
    if [[ $name == *.rpm ]]; then
        sudo dnf install -y -q "$tmp/$name"
    else
        sudo apt-get install -y -qq "$tmp/$name"
    fi
    rm -rf "$tmp"
    ui_ok "Sunshine $version instalado${current:+ (antes: $current)}"
}

grant_capture() {
    local bin
    bin="$(readlink -f "$(command -v sunshine)")"
    if getcap "$bin" | grep -q cap_sys_admin; then
        ui_ok "Sunshine já autorizado a capturar a tela"
        return
    fi
    sudo setcap cap_sys_admin+p "$bin"
    ui_ok "Sunshine autorizado a capturar a tela (KMS)"
}

sunshine_unit() {
    local unit
    for unit in "${UNITS[@]}"; do
        if [[ -f $unit ]]; then
            printf '%s' "$unit"
            return 0
        fi
    done
    ui_fail "serviço do Sunshine não encontrado em /usr/lib/systemd/user"
}

enable_service() {
    local user=$1 unit target
    unit="$(sunshine_unit)"
    target="$(sed -n 's/^WantedBy=//p' "$unit" | head -1)"
    as_user "$user" sh -c 'mkdir -p "$HOME/.config/systemd/user/$1.wants" && ln -sfn "$2" "$HOME/.config/systemd/user/$1.wants/"' \
        sh "${target:-graphical-session.target}" "$unit"
    ui_ok "Sunshine inicia com a sessão de $user (login automático no boot)"
    if user_manager_running "$user"; then
        sudo systemctl --user -M "$user@" daemon-reload
        sudo systemctl --user -M "$user@" restart "${unit##*/}"
        ui_ok "Sunshine reiniciado na sessão de $user"
    fi
}

disable_service() {
    local user=$1 unit
    unit="$(sunshine_unit)"
    if user_manager_running "$user"; then
        sudo systemctl --user -M "$user@" stop "${unit##*/}" || true
    fi
    as_user "$user" sh -c 'rm -f "$HOME"/.config/systemd/user/*.wants/"$1"' sh "${unit##*/}"
    ui_ok "Sunshine não inicia mais com a sessão de $user"
}

nvidia_pci() {
    local card
    for card in /sys/class/drm/card[0-9]*; do
        [[ ${card##*/} == *-* ]] && continue
        [[ $(cat "$card/device/vendor" 2>/dev/null) == "$NVIDIA_VENDOR" ]] || continue
        basename "$(readlink -f "$card/device")"
        return 0
    done
    return 1
}

nvidia_display() {
    local output name
    for output in /sys/class/drm/card*-*; do
        name="${output##*/}"
        [[ $(cat "/sys/class/drm/${name%%-*}/device/vendor" 2>/dev/null) == "$NVIDIA_VENDOR" ]] || continue
        [[ $(cat "$output/status" 2>/dev/null) == connected ]] || continue
        printf '%s' "${name#*-}"
        return 0
    done
    return 1
}

primary_gpu() {
    local pci rule
    pci="$(nvidia_pci)" || return 0
    if ! host_nvidia_version >/dev/null; then
        ui_warn "sem o driver proprietário, a NVIDIA não vira a placa principal do GNOME"
        return
    fi
    rule="SUBSYSTEM==\"drm\", KERNEL==\"card*\", KERNELS==\"$pci\", TAG+=\"mutter-device-preferred-primary\""
    if [[ $(cat "$MUTTER_RULE" 2>/dev/null) == "$rule" ]]; then
        ui_ok "NVIDIA já é a placa principal do GNOME"
        return
    fi
    printf '%s\n' "$rule" | sudo tee "$MUTTER_RULE" >/dev/null
    sudo udevadm control --reload
    sudo udevadm trigger --subsystem-match=drm
    HOST_REBOOT=true
    ui_ok "NVIDIA definida como placa principal do GNOME (desenha a tela e roda os jogos)"
}

sunshine_conf() {
    local user=$1
    shift
    as_user "$user" sh -c '
        file="$HOME/.config/sunshine/sunshine.conf"
        mkdir -p "${file%/*}"
        touch "$file"
        for pair; do
            key="${pair%%=*}"
            sed -i "/^$key *=/d" "$file"
            [ "$pair" = "$key" ] || printf "%s = %s\n" "$key" "${pair#*=}" >> "$file"
        done
    ' sh "$@"
}

sunshine_conf_get() {
    as_user "$1" sh -c 'sed -n "s/^$1 *= *//p" "$HOME/.config/sunshine/sunshine.conf" 2>/dev/null || true' sh "$2"
}

capture_settings() {
    local user=$1
    if [[ $(sunshine_conf_get "$user" capture) == kms ]]; then
        ui_ok "captura de tela pelo KMS já configurada"
        return
    fi
    sunshine_conf "$user" capture=kms
    ui_ok "captura de tela pelo KMS (sem a janela de permissão do portal do GNOME)"
}

origin_settings() {
    local user=$1 origin="https://$2" current
    current="$(sunshine_conf_get "$user" csrf_allowed_origins)"
    if [[ ,${current// /}, == *",$origin,"* ]]; then
        ui_ok "painel do Sunshine já aceita $origin"
        return
    fi
    sunshine_conf "$user" "csrf_allowed_origins=${current:+$current,}$origin"
    ui_ok "painel do Sunshine aceita alterações vindas de $origin (proteção CSRF)"
}

display_switch() {
    local user=$1 current
    if cmp -s scripts/display.py "$DISPLAY_BIN"; then
        ui_ok "ajuste de resolução já instalado"
    else
        sudo install -m 0755 scripts/display.py "$DISPLAY_BIN"
        if command -v restorecon >/dev/null; then
            sudo restorecon -q "$DISPLAY_BIN"
        fi
        ui_ok "ajuste de resolução instalado em $DISPLAY_BIN"
    fi
    current="$(sunshine_conf_get "$user" global_prep_cmd)"
    if [[ $current == "$PREP_CMD" ]]; then
        ui_ok "a tela já troca para a resolução de cada aparelho durante o stream"
    elif [[ -n $current && $current != *"$DISPLAY_BIN"* ]]; then
        ui_warn "o sunshine.conf de $user já tem um global_prep_cmd próprio, troca de resolução não ativada"
        ui_info "para ativar, inclua \"$DISPLAY_BIN do\" e \"$DISPLAY_BIN undo\" nos comandos globais do painel"
    else
        sunshine_conf "$user" "global_prep_cmd=$PREP_CMD"
        ui_ok "a tela troca para a resolução de cada aparelho durante o stream e volta ao final"
    fi
}

display_switch_off() {
    local user=$1
    if [[ $(sunshine_conf_get "$user" global_prep_cmd) == *"$DISPLAY_BIN"* ]]; then
        sunshine_conf "$user" global_prep_cmd
    fi
    if [[ -e $DISPLAY_BIN ]]; then
        sudo rm -f "$DISPLAY_BIN"
        ui_ok "ajuste de resolução removido"
    fi
}

display_check() {
    local output
    nvidia_pci >/dev/null || return 0
    if output="$(nvidia_display)"; then
        ui_ok "tela $output ligada na NVIDIA: o Sunshine escolhe o NVENC sozinho"
        return
    fi
    ui_warn "nenhuma tela no HDMI: o stream sai pela Intel (sem NVENC) e só com a tampa aberta"
    ui_info "ligue a TV ou um plugue HDMI fantasma na porta HDMI e feche a tampa; não precisa reinstalar"
}

cmd_install() {
    configure
    local user host
    user="$(env_get GAMES_USER)"
    host="$(env_get SUNSHINE_HOST)"

    ui_step "Host"
    host_base
    host_nvidia_driver
    host_intel_media

    ui_step "Usuário de jogos"
    create_user "$user"
    desktop_settings "$user"
    autologin "$user"
    primary_gpu

    ui_step "Sunshine"
    install_sunshine
    grant_capture
    display_check
    capture_settings "$user"
    origin_settings "$user" "$host"
    display_switch "$user"
    enable_service "$user"
    host_firewall "${STREAM_PORTS[@]}"
    host_firewall_block_lan "$WEB_PORT"

    ui_step "Caddy"
    proxy_publish "$host" "https+insecure://host.containers.internal:$WEB_PORT"

    ui_step "Acesso"
    ui_ok "painel: https://$host"
    ui_ok "Moonlight: $(host_lan_ip)"
    if $HOST_REBOOT || ! user_manager_running "$user"; then
        ui_warn "reinicie a máquina para concluir: sudo systemctl reboot"
    elif ! user_session_active "$user"; then
        ui_warn "a sessão de $user não está na tela: o Sunshine só transmite e recebe os controles dela"
        ui_info "encerre a outra sessão gráfica (Sair) para a de $user voltar, ou reinicie a máquina"
    fi
}

cmd_remove() {
    local purge=false user
    [[ ${1:-} == --purge ]] && purge=true
    user="$(env_get GAMES_USER)"

    ui_step "Remoção"
    if [[ -n $user ]] && id "$user" >/dev/null 2>&1; then
        if command -v sunshine >/dev/null; then
            disable_service "$user"
        fi
        display_switch_off "$user"
        if $purge; then
            as_user "$user" sh -c 'rm -rf "$HOME/.config/sunshine"'
            ui_ok "configuração do Sunshine apagada (credenciais e aparelhos pareados)"
        fi
    fi
    autologin_off
    if [[ -f $MUTTER_RULE ]]; then
        sudo rm -f "$MUTTER_RULE"
        sudo udevadm control --reload
        ui_ok "a Intel volta a ser a placa principal do GNOME no próximo login"
    fi
    proxy_unpublish
    ui_info "mantidos: pacote do Sunshine, driver da NVIDIA e o usuário${user:+ $user} com os jogos"
}

case "${1:-}" in
    describe) cmd_describe ;;
    status)   cmd_status ;;
    actions)  ;;
    install)  cmd_install ;;
    remove)   shift; cmd_remove "$@" ;;
    *)        ui_fail "uso: $0 describe | status | actions | install | remove [--purge]" ;;
esac
