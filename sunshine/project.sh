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
FLATPAK_GL_BRANCH=1.4
MUTTER_RULE=/etc/udev/rules.d/61-astro-mutter-primary-gpu.rules
GDM_WAIT=/etc/systemd/system/gdm.service.d/astro-nvidia.conf
DISPLAY_BIN=/usr/local/bin/astro-sunshine-display
PREP_CMD="[{\"do\":\"$DISPLAY_BIN do\",\"undo\":\"$DISPLAY_BIN undo\",\"elevated\":false}]"
CONFIG_DIR="$STATE/config"
CONFIG_LINK="$HOME/.config/sunshine"
LOCK_UNIT=astro-sunshine-lock.service
USER_UNITS="$HOME/.config/systemd/user"
LOCK_FILE="$USER_UNITS/$LOCK_UNIT"
AWAKE_UNIT=astro-sunshine-awake.service
AWAKE_FILE="$USER_UNITS/$AWAKE_UNIT"
IDLE_LOCK=300

cmd_describe() {
    echo "Sunshine: acesso remoto à tela da máquina pelo Moonlight"
}

cmd_status() {
    [[ -f $ENV_FILE ]] && command -v sunshine >/dev/null
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

session_active() {
    [[ $(loginctl show-user "$USER" -P State 2>/dev/null) == active ]]
}

configure() {
    ui_step "Configuração"
    if config_reuse; then
        ui_ok "configuração existente mantida"
        return
    fi
    local host domain
    domain="$(proxy_domain)"
    ui_input host "endereço do Sunshine no Caddy" "$(env_get SUNSHINE_HOST "sunshine.$(hostname -s)${domain:+.$domain}")" is_hostname
    (
        umask 077
        printf "SUNSHINE_HOST='%s'\n" "$host" > "$ENV_FILE"
    )
    ui_ok "configuração salva em $ENV_FILE"
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
    if getcap "$bin" | grep -q cap_sys_admin && getcap "$bin" | grep -q cap_sys_nice; then
        ui_ok "Sunshine já autorizado a capturar a tela, com prioridade alta na placa de vídeo"
        return
    fi
    sudo setcap cap_sys_admin,cap_sys_nice+p "$bin"
    ui_ok "Sunshine autorizado a capturar a tela (KMS) e com prioridade alta na placa de vídeo"
}

sunshine_unit() {
    local unit
    for unit in "${UNITS[@]}"; do
        if [[ -f $unit ]]; then
            printf '%s' "${unit##*/}"
            return 0
        fi
    done
    ui_fail "serviço do Sunshine não encontrado em /usr/lib/systemd/user"
}

config_link() {
    mkdir -p "$CONFIG_DIR" "${CONFIG_LINK%/*}"
    chmod 700 "$CONFIG_DIR"
    if [[ -d $CONFIG_LINK && ! -L $CONFIG_LINK ]]; then
        if [[ -n $(ls -A "$CONFIG_DIR") ]]; then
            ui_warn "$CONFIG_LINK e $CONFIG_DIR existem: mantido o segundo, confira o primeiro à mão"
            return
        fi
        rmdir "$CONFIG_DIR"
        mv "$CONFIG_LINK" "$CONFIG_DIR"
        ui_ok "$CONFIG_LINK movido para $CONFIG_DIR"
    fi
    ln -sfn "$CONFIG_DIR" "$CONFIG_LINK"
    ui_ok "configuração do Sunshine em $CONFIG_DIR ($CONFIG_LINK é um atalho)"
}

sunshine_conf() {
    local file="$CONFIG_DIR/sunshine.conf" pair key
    touch "$file"
    for pair; do
        key="${pair%%=*}"
        sed -i "/^$key *=/d" "$file"
        [[ $pair == "$key" ]] || printf '%s = %s\n' "$key" "${pair#*=}" >> "$file"
    done
}

sunshine_conf_get() {
    sed -n "s/^$1 *= *//p" "$CONFIG_DIR/sunshine.conf" 2>/dev/null || true
}

capture_settings() {
    if [[ $(sunshine_conf_get capture) == kms ]]; then
        ui_ok "captura de tela pelo KMS já configurada"
        return
    fi
    sunshine_conf capture=kms
    ui_ok "captura de tela pelo KMS (sem a janela de permissão do portal do GNOME)"
}

origin_settings() {
    local origin="https://$1" current
    current="$(sunshine_conf_get csrf_allowed_origins)"
    if [[ ,${current// /}, == *",$origin,"* ]]; then
        ui_ok "painel do Sunshine já aceita $origin"
        return
    fi
    sunshine_conf "csrf_allowed_origins=${current:+$current,}$origin"
    ui_ok "painel do Sunshine aceita alterações vindas de $origin (proteção CSRF)"
}

display_switch() {
    local current
    if cmp -s scripts/display.py "$DISPLAY_BIN"; then
        ui_ok "ajuste de resolução já instalado"
    else
        sudo install -m 0755 scripts/display.py "$DISPLAY_BIN"
        if command -v restorecon >/dev/null; then
            sudo restorecon -q "$DISPLAY_BIN"
        fi
        ui_ok "ajuste de resolução instalado em $DISPLAY_BIN"
    fi
    current="$(sunshine_conf_get global_prep_cmd)"
    if [[ $current == "$PREP_CMD" ]]; then
        ui_ok "a tela já troca para a resolução de cada aparelho durante o stream"
    elif [[ -n $current && $current != *"$DISPLAY_BIN"* ]]; then
        ui_warn "o sunshine.conf já tem um global_prep_cmd próprio, troca de resolução não ativada"
        ui_info "para ativar, inclua \"$DISPLAY_BIN do\" e \"$DISPLAY_BIN undo\" nos comandos globais do painel"
    else
        sunshine_conf "global_prep_cmd=$PREP_CMD"
        ui_ok "a tela troca para a resolução de cada aparelho durante o stream e volta ao final"
    fi
}

apps() {
    local kind text
    while read -r kind text; do
        case $kind in
            ok) ui_ok "$text" ;;
            *)  ui_info "$text" ;;
        esac
    done < <(python3 -I scripts/apps.py "$CONFIG_DIR/apps.json")
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
    else
        printf '%s\n' "$rule" | sudo tee "$MUTTER_RULE" >/dev/null
        sudo udevadm control --reload
        sudo udevadm trigger --subsystem-match=drm
        HOST_REBOOT=true
        ui_ok "NVIDIA definida como placa principal do GNOME (desenha a tela e roda os aplicativos)"
    fi
    gdm_wait "$pci"
    flatpak_gl
}

flatpak_gl() {
    local version ref old log
    command -v flatpak >/dev/null || return 0
    version="$(cat /sys/module/nvidia/version 2>/dev/null)" || version=""
    [[ -n $version ]] || version="$(host_nvidia_version)" || return 0
    ref="org.freedesktop.Platform.GL.nvidia-${version//./-}"
    if flatpak info --system "$ref//$FLATPAK_GL_BRANCH" >/dev/null 2>&1; then
        ui_ok "apps Flatpak já usam o driver da NVIDIA $version"
    elif ! flatpak remotes --system --columns=name | grep -qx flathub; then
        ui_warn "sem o Flathub, os apps Flatpak não abrem com a NVIDIA como placa principal: instale $ref"
        return 0
    else
        ui_info "instalando no Flatpak o driver da NVIDIA $version, igual ao da máquina..."
        if ! log="$(sudo flatpak install -y --noninteractive --system flathub "$ref//$FLATPAK_GL_BRANCH" 2>&1)"; then
            printf '%s\n' "$log" | ui_prefix >&2
            ui_warn "falha ao instalar $ref: os apps Flatpak não abrem com a NVIDIA como placa principal"
            return 0
        fi
        ui_ok "apps Flatpak usam o driver da NVIDIA $version (sem ele, não abrem com a NVIDIA como placa principal)"
    fi
    while read -r old; do
        [[ -n $old && $old != "$ref" ]] || continue
        sudo flatpak uninstall -y --noninteractive --system "$old//$FLATPAK_GL_BRANCH" >/dev/null 2>&1 || true
        ui_ok "driver antigo da NVIDIA tirado do Flatpak (${old#org.freedesktop.Platform.GL.nvidia-})"
    done < <(flatpak list --system --runtime --columns=application 2>/dev/null | grep '^org\.freedesktop\.Platform\.GL\.nvidia-[0-9]' || true)
}

gdm_wait() {
    local wanted
    wanted="$(printf '[Service]\nExecStartPre=-/usr/bin/udevadm wait --timeout=30 /dev/dri/by-path/pci-%s-card\n' "$1")"
    if [[ $(cat "$GDM_WAIT" 2>/dev/null) == "$wanted" ]]; then
        ui_ok "a tela de login já espera a NVIDIA no boot"
        return
    fi
    sudo mkdir -p "${GDM_WAIT%/*}"
    printf '%s\n' "$wanted" | sudo tee "$GDM_WAIT" >/dev/null
    sudo systemctl daemon-reload
    HOST_REBOOT=true
    ui_ok "a tela de login espera a NVIDIA aparecer no boot (até 30s), para o GNOME escolhê-la como principal"
}

display_check() {
    local output
    nvidia_pci >/dev/null || return 0
    if output="$(nvidia_display)"; then
        ui_ok "tela $output ligada na NVIDIA: o Sunshine escolhe o NVENC sozinho"
        return
    fi
    ui_warn "nenhuma tela no HDMI: o stream sai pela Intel (sem NVENC) e só com a tampa aberta"
    ui_info "ligue um monitor ou um plugue HDMI fantasma na porta HDMI e feche a tampa; não precisa reinstalar"
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
    local conf wanted
    if ! conf="$(gdm_conf)"; then
        ui_warn "GDM não encontrado: configure o login automático de $USER no gerenciador de login"
        return
    fi
    wanted="$(gdm_render "$conf" "$USER")"
    if [[ $wanted == "$(cat "$conf")" ]]; then
        ui_ok "login automático já configurado para $USER"
        return
    fi
    printf '%s\n' "$wanted" | sudo tee "$conf" >/dev/null
    HOST_REBOOT=true
    ui_ok "login automático configurado para $USER"
}

autologin_off() {
    local conf
    conf="$(gdm_conf)" || return 0
    [[ $(gdm_autologin_user) == "$USER" ]] || return 0
    gdm_render "$conf" "" | sudo tee "$conf" >/dev/null
    ui_ok "login automático de $USER desativado"
}

session_gsettings() {
    local runtime="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
    local bus="unix:path=$runtime/bus"
    if [[ -S $runtime/bus ]]; then
        DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-$bus}" sh -c "$1"
    else
        dbus-run-session -- sh -c "$1"
    fi
}

screen_lock() {
    if ! command -v gsettings >/dev/null || ! gsettings list-schemas 2>/dev/null | grep -qx org.gnome.desktop.lockdown; then
        ui_warn "GNOME não encontrado: configure o bloqueio de tela de $USER manualmente"
        return
    fi
    session_gsettings "
        gsettings set org.gnome.desktop.screensaver lock-enabled true
        gsettings set org.gnome.desktop.screensaver lock-delay 0
        gsettings set org.gnome.desktop.lockdown disable-lock-screen false
        gsettings set org.gnome.desktop.session idle-delay $IDLE_LOCK
        gsettings set org.gnome.settings-daemon.plugins.power idle-dim false
    " >/dev/null 2>&1
    ui_ok "tela de $USER bloqueia depois de $((IDLE_LOCK / 60)) minutos parada"
    lock_unit | user_file "$LOCK_FILE"
    systemctl --user daemon-reload
    systemctl --user enable -q "$LOCK_UNIT"
    ui_ok "a sessão de $USER bloqueia logo depois do login automático ($LOCK_UNIT)"
}

user_file() {
    mkdir -p "${1%/*}"
    cat > "$1.new"
    if cmp -s "$1.new" "$1"; then
        rm -f "$1.new"
    else
        mv "$1.new" "$1"
    fi
}

awake_unit() {
    printf '%s\n' \
        "[Unit]" \
        "Description=astro sunshine: mantém a tela acesa para a captura" \
        "After=graphical-session.target" \
        "PartOf=graphical-session.target" \
        "" \
        "[Service]" \
        "ExecStart=$DISPLAY_BIN awake" \
        "Restart=on-failure" \
        "RestartSec=5" \
        "" \
        "[Install]" \
        "WantedBy=graphical-session.target"
}

sunshine_dropin() {
    printf '%s\n' \
        "[Unit]" \
        "Wants=$AWAKE_UNIT" \
        "After=$AWAKE_UNIT $LOCK_UNIT"
}

lock_unit() {
    printf '%s\n' \
        "[Unit]" \
        "Description=astro sunshine: bloqueia a tela depois do login" \
        "After=graphical-session.target" \
        "PartOf=graphical-session.target" \
        "" \
        "[Service]" \
        "Type=oneshot" \
        "ExecStart=/bin/sh -c 's=\$\$(loginctl show-user \"\$\$USER\" -p Display --value); for i in \$\$(seq 30); do sleep 2; [ \"\$\$(loginctl show-session \"\$\$s\" -p LockedHint --value)\" = yes ] && exit 0; loginctl lock-session \"\$\$s\"; done; echo \"[sunshine] erro: a tela não bloqueou\"; exit 1'" \
        "" \
        "[Install]" \
        "WantedBy=graphical-session.target"
}

enable_service() {
    local unit
    unit="$(sunshine_unit)"
    awake_unit | user_file "$AWAKE_FILE"
    sunshine_dropin | user_file "$USER_UNITS/$unit.d/astro.conf"
    systemctl --user daemon-reload
    systemctl --user enable -q "$AWAKE_UNIT" "$unit"
    ui_ok "tela mantida acesa durante a sessão ($AWAKE_UNIT): com ela apagada, o Sunshine não captura nada"
    ui_ok "Sunshine inicia com a sessão gráfica de $USER, depois do bloqueio"
    if session_active; then
        systemctl --user restart "$AWAKE_UNIT"
        systemctl --user restart "$unit"
        ui_ok "Sunshine reiniciado na sessão de $USER"
    fi
}

cmd_install() {
    state_setup
    configure
    local host
    host="$(env_get SUNSHINE_HOST)"

    ui_step "Host"
    host_nvidia_driver
    host_intel_media
    primary_gpu

    ui_step "Sessão de $USER"
    autologin
    screen_lock

    ui_step "Sunshine"
    install_sunshine
    grant_capture
    display_check
    config_link
    capture_settings
    origin_settings "$host"
    display_switch
    apps
    enable_service
    host_firewall "${STREAM_PORTS[@]}"
    host_firewall_block_lan "$WEB_PORT"

    ui_step "Caddy"
    proxy_publish "$host" "https+insecure://host.containers.internal:$WEB_PORT"

    ui_step "Acesso"
    ui_ok "painel do Sunshine: https://$host"
    ui_ok "Moonlight: $(host_lan_ip)"
    ui_info "o Moonlight mostra a tela bloqueada: destrave com a senha de $USER"
    ui_info "com o login automático, o chaveiro do GNOME não abre no boot: programas que guardam senhas nele pedem a senha"
    if $HOST_REBOOT || ! session_active; then
        ui_warn "reinicie a máquina para concluir: sudo systemctl reboot"
    fi
}

cmd_actions() {
    return 0
}

cmd_action() {
    ui_fail "ação desconhecida: ${1:-}"
}

cmd_domain() {
    local old=$1 new=$2 host current item origins=() unit
    host="$(env_get SUNSHINE_HOST)"
    [[ -n $host ]] || return 0
    ui_step "Sunshine"
    current="$(sunshine_conf_get csrf_allowed_origins)"
    for item in ${current//,/ }; do
        [[ $item == "https://"*".$old" ]] && item="${item%."$old"}.$new"
        [[ " ${origins[*]} " == *" $item "* ]] || origins+=("$item")
    done
    [[ " ${origins[*]} " == *" https://$host "* ]] || origins+=("https://$host")
    sunshine_conf "csrf_allowed_origins=$(IFS=,; echo "${origins[*]}")"
    ui_ok "painel do Sunshine aceita alterações vindas de https://$host"
    if session_active; then
        unit="$(sunshine_unit)"
        ui_warn "o Sunshine reinicia agora: um stream em andamento cai"
        systemctl --user restart "$unit"
        ui_ok "Sunshine reiniciado"
    fi

    ui_step "Caddy"
    proxy_publish "$host" "https+insecure://host.containers.internal:$WEB_PORT"
}

cmd_remove() {
    local unit bin
    ui_step "Remoção"
    autologin_off
    if [[ -f $LOCK_FILE ]]; then
        systemctl --user disable -q "$LOCK_UNIT" 2>/dev/null || true
        rm -f "$LOCK_FILE"
        systemctl --user daemon-reload
        ui_ok "a sessão de $USER não bloqueia mais sozinha no login"
    fi
    for unit in "${UNITS[@]}"; do
        rm -rf "$USER_UNITS/${unit##*/}.d"
        [[ -f $unit ]] || continue
        systemctl --user disable -q --now "${unit##*/}" 2>/dev/null || true
    done
    if [[ -f $AWAKE_FILE ]]; then
        systemctl --user disable -q --now "$AWAKE_UNIT" 2>/dev/null || true
        rm -f "$AWAKE_FILE"
    fi
    systemctl --user daemon-reload
    ui_ok "Sunshine não inicia mais com a sessão de $USER"
    if command -v sunshine >/dev/null; then
        bin="$(readlink -f "$(command -v sunshine)")"
        if getcap "$bin" | grep -q cap_sys_admin; then
            sudo setcap -r "$bin"
            ui_ok "permissão de captura de tela tirada do Sunshine"
        fi
    fi
    if [[ -e $DISPLAY_BIN ]]; then
        sudo rm -f "$DISPLAY_BIN"
        ui_ok "ajuste de resolução removido"
    fi
    if [[ -f $MUTTER_RULE ]]; then
        sudo rm -f "$MUTTER_RULE"
        sudo udevadm control --reload
        ui_ok "a Intel volta a ser a placa principal do GNOME no próximo login"
    fi
    if [[ -f $GDM_WAIT ]]; then
        sudo rm -f "$GDM_WAIT"
        sudo rmdir "${GDM_WAIT%/*}" 2>/dev/null || true
        sudo systemctl daemon-reload
        ui_ok "a tela de login não espera mais a NVIDIA"
    fi
    host_firewall_remove "${STREAM_PORTS[@]}"
    host_firewall_unblock_lan "$WEB_PORT"
    proxy_unpublish
    [[ -L $CONFIG_LINK ]] && rm -f "$CONFIG_LINK"
    state_purge
    ui_info "mantidos: pacote do Sunshine e driver da NVIDIA"
}

cmd_backup() {
    printf 'exclude %s\n' "$CONFIG_DIR/sunshine.log*"
}

cmd_restore() {
    local unit
    state_restore "$1"
    ln -sfn "$CONFIG_DIR" "$CONFIG_LINK"
    if session_active; then
        unit="$(sunshine_unit)"
        systemctl --user restart "$unit"
        ui_ok "Sunshine reiniciado com a configuração restaurada (pareamentos e painel)"
    fi
}

case "${1:-}" in
    describe) cmd_describe ;;
    status)   cmd_status ;;
    actions)  cmd_actions ;;
    action)   shift; cmd_action "$@" ;;
    install)  cmd_install ;;
    domain)   shift; cmd_domain "$1" "$2" ;;
    remove)   cmd_remove ;;
    backup)   cmd_backup ;;
    restore)  shift; cmd_restore "$1" ;;
    *)        ui_fail "uso: $0 describe | status | actions | action <id> | install | domain <antigo> <novo> | remove | backup | restore <pasta>" ;;
esac
