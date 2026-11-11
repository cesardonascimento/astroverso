#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"

ASTRO_PROJECT=arcade
source ../lib/ui.sh
source ../lib/host.sh
source ../lib/env.sh
source ../lib/proxy.sh
source ../lib/disk.sh

GAMES_DEFAULT=ristar
REPO=LizardByte/Sunshine
WEB_PORT=47990
STREAM_PORTS=(47984/tcp 47989/tcp 48010/tcp 47998-48000/udp 48002/udp 48010/udp)
GDM_CONFS=(/etc/gdm/custom.conf /etc/gdm3/custom.conf /etc/gdm3/daemon.conf)
UNITS=(/usr/lib/systemd/user/app-dev.lizardbyte.app.Sunshine.service /usr/lib/systemd/user/sunshine.service)
NVIDIA_VENDOR=0x10de
MUTTER_RULE=/etc/udev/rules.d/61-astro-mutter-primary-gpu.rules
GDM_WAIT=/etc/systemd/system/gdm.service.d/astro-nvidia.conf
DISPLAY_BIN=/usr/local/bin/astro-sunshine-display
SPEAKERS_BIN=/usr/local/bin/astro-arcade-speakers
SPEAKERS_UNIT=astro-arcade-speakers.service
PREP_CMD="[{\"do\":\"$DISPLAY_BIN do\",\"undo\":\"$DISPLAY_BIN undo\",\"elevated\":false}]"
ESDE_API="https://gitlab.com/api/v4/projects/es-de%2Femulationstation-de"
ESDE_DOWNLOAD="https://gitlab.com/es-de/emulationstation-de/-/package_files"
ESDE_BIN=/usr/local/bin/es-de
ESDE_SHARE=/usr/local/share/astro-arcade
ESDE_DESKTOP=/usr/local/share/applications/org.es_de.frontend.desktop
ESDE_ICON=/usr/local/share/icons/hicolor/scalable/apps/org.es_de.frontend.svg
ESDE_FILES=(usr/share/es-de/resources/systems/linux/es_systems.xml
    usr/share/applications/org.es_de.frontend.desktop
    usr/share/icons/hicolor/scalable/apps/org.es_de.frontend.svg)
RETROARCH_APP=org.libretro.RetroArch
RETROARCH_GL_BRANCH=1.4
BROWSE_ROOTS=()
ARCADE_BACKUP_FILTER=(
    "+ /retroarch/retroarch.cfg" "+ /retroarch/saves/**" "+ /retroarch/states/**" "+ /retroarch/system/**"
    "+ /retroarch/config/**" "+ /retroarch/playlists/**" "+ /retroarch/screenshots/**" "+ /retroarch/records/**"
    "+ /es-de/settings/**" "+ /es-de/collections/**" "+ /es-de/gamelists/**" "+ /es-de/themes/**"
    "- *"
)

cmd_describe() {
    echo "Arcade: ES-DE e RetroArch num usuário de jogos próprio, transmitidos pelo Sunshine para o Moonlight"
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
    [[ -n $user ]] && command -v sunshine >/dev/null && [[ -x $ESDE_BIN ]] && id "$user" >/dev/null 2>&1
}

as_user() {
    local user=$1
    shift
    (cd / && sudo -u "$user" -H "$@")
}

games_home() {
    getent passwd "$1" | cut -d: -f6
}

user_manager_running() {
    [[ $(loginctl show-user "$1" -P State 2>/dev/null) == @(active|online) ]]
}

user_session_active() {
    [[ $(loginctl show-user "$1" -P State 2>/dev/null) == active ]]
}

env_put() {
    sed -i "/^$1=/d" "$ENV_FILE"
    printf "%s='%s'\n" "$1" "$2" >> "$ENV_FILE"
}

rom_dirs() {
    local -n __roms=$1
    IFS='|' read -ra __roms <<< "$(env_get ROM_DIRS)"
}

browse_roots() {
    local mount type others=()
    BROWSE_ROOTS=()
ARCADE_BACKUP_FILTER=(
    "+ /retroarch/retroarch.cfg" "+ /retroarch/saves/**" "+ /retroarch/states/**" "+ /retroarch/system/**"
    "+ /retroarch/config/**" "+ /retroarch/playlists/**" "+ /retroarch/screenshots/**" "+ /retroarch/records/**"
    "+ /es-de/settings/**" "+ /es-de/collections/**" "+ /es-de/gamelists/**" "+ /es-de/themes/**"
    "- *"
)
    while read -r mount type; do
        if [[ $type == compartilhado ]]; then
            BROWSE_ROOTS+=("$mount")
        else
            others+=("$mount")
        fi
    done < <(disk_mounts | sort)
    BROWSE_ROOTS+=("${others[@]}")
    ((${#BROWSE_ROOTS[@]})) || BROWSE_ROOTS=(/)
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
        ui_warn "$user tem acesso ao sudo; o usuário de jogos não pode ter privilégios"
        return 1
    fi
}

choose_autologin() {
    local answer=n
    ui_confirm "entrar sozinho com o usuário de jogos no boot, sem bloqueio de tela?" "$(env_get AUTOLOGIN yes | sed 's/yes/y/;s/no/n/')" && answer=yes
    [[ $answer == yes ]] || answer=no
    env_put AUTOLOGIN "$answer"
}

choose_media() {
    local force=${1:-false} current path
    current="$(env_get MEDIA_DIR)"
    if ! $force && [[ -n $current ]] && ui_confirm "manter a pasta de mídias do ES-DE em $current?" y; then
        return
    fi
    while true; do
        ui_browse path "Onde está a pasta de mídias do ES-DE (imagens e vídeos)?" "${BROWSE_ROOTS[@]}"
        path="$(is_path "$path")" && break
        ui_warn "use uma pasta cujo caminho tenha só letras, números, espaço, ponto, hífen e sublinhado"
    done
    env_put MEDIA_DIR "$path"
}

choose_roms() {
    local force=${1:-false} current path item dirs=() repeated
    current="$(env_get ROM_DIRS)"
    if ! $force && [[ -n $current ]] && ui_confirm "manter as pastas de ROMs (${current//|/, })?" y; then
        return
    fi
    ui_info "cada pasta de ROMs tem uma subpasta por sistema (snes, psx...); a primeira é a principal do ES-DE"
    while true; do
        ui_browse path "Onde estão as ROMs?" "${BROWSE_ROOTS[@]}"
        if ! path="$(is_path "$path")"; then
            ui_warn "use uma pasta cujo caminho tenha só letras, números, espaço, ponto, hífen e sublinhado"
            continue
        fi
        repeated=false
        for item in "${dirs[@]}"; do [[ $item == "$path" ]] && repeated=true; done
        if $repeated; then
            ui_warn "$path já está na lista"
        else
            dirs+=("$path")
        fi
        ui_confirm "adicionar outra pasta de ROMs?" n || break
    done
    env_put ROM_DIRS "$(IFS='|'; printf '%s' "${dirs[*]}")"
}

backup_default() {
    local dest disk
    dest="$(env_get CONFIG_BACKUP "" "$ASTRO_HOME/rclone/.env")"
    if [[ -n $dest ]]; then
        printf '%s/Arcade' "${dest%/*}"
        return 0
    fi
    disk="$(disk_mounts | awk '$2 == "privado" { print $1; exit }')"
    [[ -z $disk ]] || printf '%s/Astro/Arcade' "$disk"
    return 0
}

choose_backup() {
    local dest default
    default="$(env_get ARCADE_BACKUP "$(backup_default)")"
    ui_info "toda noite, à 01:00, o RetroArch (configuração, saves, states, BIOS, capturas e gravações) e o ES-DE"
    ui_info "(configuração, coleções, gamelists e temas) são copiados para uma pasta, que também serve para restaurar"
    if ! ui_confirm "guardar o RetroArch e o ES-DE todas as noites?" y; then
        env_put ARCADE_BACKUP ""
        ui_info "sem backup do RetroArch e do ES-DE"
        return
    fi
    while true; do
        ui_input dest "pasta do backup do RetroArch e do ES-DE" "$default" is_path
        if mkdir -p "$dest" 2>/dev/null && [[ -w $dest ]]; then
            break
        fi
        ui_warn "não foi possível gravar em $dest: escolha outra pasta"
    done
    env_put ARCADE_BACKUP "$dest"
    ui_ok "backup do RetroArch e do ES-DE em $dest"
}

backup_folder() {
    local dir
    dir="$(env_get ARCADE_BACKUP)"
    if [[ -n $dir ]] && has_files "$dir/$1"; then
        printf '%s' "$dir/$1"
    fi
    return 0
}

configure() {
    ui_step "Configuração"
    local saved default user host domain autologin_current
    saved="$(env_get GAMES_USER)"
    if [[ -f $ENV_FILE && -n $saved ]] && ! id "$saved" >/dev/null 2>&1; then
        ui_warn "o usuário de jogos $saved não existe nesta máquina: responda a configuração de novo"
    elif [[ -f $ENV_FILE ]] && ui_confirm "usar a configuração já salva em $ENV_FILE?" y; then
        ui_ok "configuração existente mantida"
        grep -q '^ARCADE_BACKUP=' "$ENV_FILE" || choose_backup
        return
    fi
    default=$GAMES_DEFAULT
    [[ -n $saved ]] && id "$saved" >/dev/null 2>&1 && default=$saved
    autologin_current="$(env_get AUTOLOGIN yes)"
    domain="$(proxy_domain)"
    while true; do
        ui_input user "nome do usuário de jogos (criado se não existir)" "$default" is_username
        check_games_user "$user" && break
    done
    ui_input host "endereço do Sunshine no Caddy" "$(env_get SUNSHINE_HOST "sunshine.$(hostname -s)${domain:+.$domain}")" is_hostname
    local media roms backup
    media="$(env_get MEDIA_DIR)"
    roms="$(env_get ROM_DIRS)"
    backup="$(env_get ARCADE_BACKUP)"
    (
        umask 077
        printf "GAMES_USER='%s'\nSUNSHINE_HOST='%s'\nAUTOLOGIN='%s'\n" "$user" "$host" "$autologin_current" > "$ENV_FILE.new"
        [[ -z $media ]] || printf "MEDIA_DIR='%s'\n" "$media" >> "$ENV_FILE.new"
        [[ -z $roms ]] || printf "ROM_DIRS='%s'\n" "$roms" >> "$ENV_FILE.new"
        [[ -z $backup ]] || printf "ARCADE_BACKUP='%s'\n" "$backup" >> "$ENV_FILE.new"
    )
    mv "$ENV_FILE.new" "$ENV_FILE"
    choose_autologin
    choose_media
    choose_roms
    choose_backup
    ui_ok "configuração salva em $ENV_FILE"
}

install_packages() {
    local package missing=()
    for package in flatpak fuse3; do
        rpm -q "$package" >/dev/null 2>&1 || dpkg -s "$package" >/dev/null 2>&1 || missing+=("$package")
    done
    if ((${#missing[@]} == 0)); then
        ui_ok "flatpak e fuse3 já instalados"
    elif command -v dnf >/dev/null; then
        sudo dnf install -y -q "${missing[@]}"
        ui_ok "instalados via dnf: ${missing[*]}"
    elif command -v apt-get >/dev/null; then
        sudo apt-get install -y -qq "${missing[@]}"
        ui_ok "instalados via apt: ${missing[*]}"
    else
        ui_fail "instale manualmente: ${missing[*]}"
    fi
}

create_user() {
    local user=$1
    if id "$user" >/dev/null 2>&1; then
        ui_ok "usuário $user já existe"
    else
        sudo useradd -m -c "Jogos" "$user"
        ui_ok "usuário $user criado, sem sudo"
    fi
    as_user "$user" sh -c 'mkdir -p "$HOME/.config" && printf "yes\n" > "$HOME/.config/gnome-initial-setup-done"'
}

stop_sunshine() {
    local unit
    for unit in "${UNITS[@]}"; do
        if [[ -f $unit ]] && user_manager_running "$1"; then
            sudo systemctl --user -M "$1@" "${2:-stop}" "${unit##*/}" 2>/dev/null || true
        fi
    done
}

games_acl() {
    local home
    home="$(games_home "$1")"
    sudo setfacl -m "u:$USER:x" "$home"
    sudo setfacl -R -m "u:$USER:rX" "$home/.astro"
    sudo find "$home/.astro" -type d -exec setfacl -m "d:u:$USER:rX" {} +
}

games_state() {
    local user=$1 home kind name other
    home="$(games_home "$user")"
    stop_sunshine "$user"
    while read -r kind name other; do
        case $kind in
            moved)    ui_ok "$name movido para $home/.astro/arcade" ;;
            conflict) ui_warn "$home/$name e $home/.astro/arcade/$other existem: mantido o segundo, confira o primeiro à mão" ;;
        esac
    done < <(as_user "$user" sh -c '
        base="$HOME/.astro/arcade"
        mkdir -p "$base"
        chmod 700 "$HOME/.astro"
        link() {
            new="$base/$1"
            old="$HOME/$2"
            if [ -d "$old" ] && [ ! -L "$old" ]; then
                if [ -e "$new" ]; then
                    echo "conflict $2 $1"
                else
                    mv "$old" "$new"
                    echo "moved $2"
                fi
            fi
            mkdir -p "$new" "$(dirname "$old")"
            if [ ! -d "$old" ] || [ -L "$old" ]; then
                ln -sfn "$new" "$old"
            fi
        }
        link sunshine .config/sunshine
        link es-de ES-DE
        link retroarch .var/app/org.libretro.RetroArch/config/retroarch
    ')
    ui_ok "configuração do usuário de jogos em $home/.astro/arcade (sunshine, es-de, retroarch)"
    games_acl "$user"
    ui_ok "$USER pode ler $home/.astro (só leitura, para o backup das configurações)"
}

games_password() {
    local user=$1 password status
    status="$(sudo passwd -S "$user" 2>/dev/null | awk '{ print $2 }')"
    if [[ $status == P* ]] && ui_confirm "manter a senha atual de $user?" y; then
        ui_ok "senha de $user mantida"
        return
    fi
    ui_info "a senha serve para entrar na tela, trocar de usuário e desbloquear; ela não dá acesso ao sudo"
    ui_secret password "senha de $user"
    printf '%s:%s\n' "$user" "$password" | sudo chpasswd
    ui_ok "senha de $user definida"
}

desktop_settings() {
    local user=$1 autologin=$2 lock=true idle=300
    if ! command -v gsettings >/dev/null || ! gsettings list-schemas 2>/dev/null | grep -qx org.gnome.desktop.lockdown; then
        ui_warn "GNOME não encontrado: ajuste o bloqueio de tela de $user manualmente"
        return
    fi
    if [[ $autologin == yes ]]; then
        lock=false
        idle=0
    fi
    as_user "$user" dbus-run-session -- sh -c '
        gsettings set org.gnome.desktop.screensaver lock-enabled "$1"
        gsettings set org.gnome.desktop.lockdown disable-lock-screen false
        gsettings set org.gnome.desktop.session idle-delay "$2"
        gsettings set org.gnome.settings-daemon.plugins.power idle-dim false
        gsettings set org.gnome.settings-daemon.plugins.power sleep-inactive-ac-type nothing
        gsettings set org.gnome.settings-daemon.plugins.power sleep-inactive-battery-type nothing
        gsettings set org.gnome.software download-updates false
        gsettings set org.gnome.software download-updates-notify false
    ' sh "$lock" "$idle" >/dev/null 2>&1
    if [[ $autologin == yes ]]; then
        ui_ok "$user sem bloqueio automático de tela (bloquear e trocar de usuário à mão continuam funcionando)"
    else
        ui_ok "$user com bloqueio de tela depois de 5 minutos parado"
    fi
    ui_ok "escurecimento e suspensão desativados para $user"
    ui_ok "Central de Programas de $user sem downloads automáticos (ele não instala atualizações)"
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
        ui_ok "NVIDIA definida como placa principal do GNOME (desenha a tela e roda os jogos)"
    fi
    gdm_wait "$pci"
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

speakers_setup() {
    local user=$1
    if ! cmp -s scripts/speakers.py "$SPEAKERS_BIN"; then
        sudo install -m 0755 scripts/speakers.py "$SPEAKERS_BIN"
        if command -v restorecon >/dev/null; then
            sudo restorecon -q "$SPEAKERS_BIN"
        fi
    fi
    as_user "$user" sh -c '
        dir="$HOME/.config/systemd/user"
        mkdir -p "$dir/graphical-session.target.wants"
        printf "%s\n" "[Unit]" "Description=astro arcade: alto-falantes internos mudos" "After=wireplumber.service" "" \
            "[Service]" "Type=oneshot" "ExecStart=$1" "" "[Install]" "WantedBy=graphical-session.target" > "$dir/$2"
        ln -sfn "$dir/$2" "$dir/graphical-session.target.wants/$2"
    ' sh "$SPEAKERS_BIN" "$SPEAKERS_UNIT"
    ui_ok "alto-falantes do notebook mudos a cada sessão de $user (o som do stream não é afetado)"
    if user_session_active "$user"; then
        as_user "$user" env XDG_RUNTIME_DIR="/run/user/$(id -u "$user")" "$SPEAKERS_BIN"
    fi
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

install_retroarch() {
    local log
    if ! flatpak remotes --system --columns=name | grep -qx flathub; then
        sudo flatpak remote-add --system --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo
        sudo flatpak remote-modify --system --enable flathub
        ui_ok "repositório Flathub ativado"
    fi
    if flatpak info --system "$RETROARCH_APP" >/dev/null 2>&1; then
        ui_ok "RetroArch já instalado (Flatpak $RETROARCH_APP)"
        return
    fi
    ui_info "instalando o RetroArch pelo Flathub (alguns minutos na primeira vez)..."
    if ! log="$(sudo flatpak install -y --noninteractive --system flathub "$RETROARCH_APP" 2>&1)"; then
        printf '%s\n' "$log" | ui_prefix >&2
        ui_fail "falha ao instalar o RetroArch pelo Flathub"
    fi
    ui_ok "RetroArch instalado (Flatpak $RETROARCH_APP)"
}

retroarch_gl() {
    local version ref old log
    nvidia_pci >/dev/null || return 0
    version="$(cat /sys/module/nvidia/version 2>/dev/null)" || version=""
    [[ -n $version ]] || version="$(host_nvidia_version)" || return 0
    ref="org.freedesktop.Platform.GL.nvidia-${version//./-}"
    if flatpak info --system "$ref//$RETROARCH_GL_BRANCH" >/dev/null 2>&1; then
        ui_ok "RetroArch já usa o driver da NVIDIA $version (Flatpak)"
    else
        ui_info "instalando no Flatpak o driver da NVIDIA $version, igual ao da máquina..."
        if ! log="$(sudo flatpak install -y --noninteractive --system flathub "$ref//$RETROARCH_GL_BRANCH" 2>&1)"; then
            printf '%s\n' "$log" | ui_prefix >&2
            ui_warn "falha ao instalar $ref: o RetroArch não vai usar a NVIDIA"
            return 0
        fi
        ui_ok "RetroArch usa o driver da NVIDIA $version (Flatpak)"
    fi
    while read -r old; do
        [[ -n $old && $old != "$ref" ]] || continue
        sudo flatpak uninstall -y --noninteractive --system "$old//$RETROARCH_GL_BRANCH" >/dev/null 2>&1 || true
        ui_ok "driver antigo da NVIDIA tirado do Flatpak (${old#org.freedesktop.Platform.GL.nvidia-})"
    done < <(flatpak list --system --runtime --columns=application 2>/dev/null | grep '^org\.freedesktop\.Platform\.GL\.nvidia-[0-9]' || true)
}

update_retroarch() {
    local log
    if ! log="$(sudo flatpak update -y --noninteractive --system "$RETROARCH_APP" 2>&1)"; then
        printf '%s\n' "$log" | ui_prefix >&2
        ui_warn "falha ao atualizar o RetroArch"
        return
    fi
    ui_ok "RetroArch atualizado (Flatpak)"
}

esde_latest() {
    curl -fsSL -m 30 "$ESDE_API/packages?package_name=ES-DE_Stable&order_by=created_at&sort=desc&per_page=1" | python3 -I -c '
import json, sys
package = json.load(sys.stdin)[0]
print(package["id"], package["version"])
'
}

esde_file() {
    curl -fsSL -m 30 "$ESDE_API/packages/$1/package_files?per_page=100" | python3 -I -c '
import json, sys
for item in json.load(sys.stdin):
    if item["file_name"] == "ES-DE_x64.AppImage":
        print(item["id"], item["file_sha256"])
        break
'
}

install_esde() {
    local release package version file id sha current tmp entry
    release="$(esde_latest)" || ui_fail "não foi possível consultar as versões do ES-DE no GitLab"
    read -r package version <<< "$release"
    current="$(cat "$ESDE_SHARE/version" 2>/dev/null || true)"
    if [[ $current == "$version" && -x $ESDE_BIN && -f $ESDE_SHARE/es_systems.xml ]]; then
        ui_ok "ES-DE $version já instalado (versão mais recente)"
        return
    fi
    file="$(esde_file "$package")" || ui_fail "não foi possível consultar os arquivos do ES-DE $version"
    [[ -n $file ]] || ui_fail "o ES-DE $version não tem o ES-DE_x64.AppImage"
    read -r id sha <<< "$file"

    ui_info "baixando o ES-DE $version..."
    tmp="$(mktemp -d)"
    if ! curl -fsSL --retry 3 -o "$tmp/es-de" "$ESDE_DOWNLOAD/$id/download"; then
        rm -rf "$tmp"
        ui_fail "falha ao baixar o ES-DE $version"
    fi
    if ! printf '%s  %s\n' "$sha" "$tmp/es-de" | sha256sum -c --status; then
        rm -rf "$tmp"
        ui_fail "o SHA-256 do ES-DE $version não confere com o publicado no GitLab"
    fi
    ui_ok "SHA-256 conferido"
    chmod 755 "$tmp/es-de"
    for entry in "${ESDE_FILES[@]}"; do
        (cd "$tmp" && ./es-de --appimage-extract "$entry" >/dev/null 2>&1) || true
    done
    if [[ ! -f $tmp/squashfs-root/${ESDE_FILES[0]} ]]; then
        rm -rf "$tmp"
        ui_fail "não foi possível ler a lista de sistemas de dentro do ES-DE $version"
    fi
    sudo install -D -m 0755 "$tmp/es-de" "$ESDE_BIN"
    sudo install -D -m 0644 "$tmp/squashfs-root/${ESDE_FILES[0]}" "$ESDE_SHARE/es_systems.xml"
    [[ -f $tmp/squashfs-root/${ESDE_FILES[1]} ]] && sudo install -D -m 0644 "$tmp/squashfs-root/${ESDE_FILES[1]}" "$ESDE_DESKTOP"
    [[ -f $tmp/squashfs-root/${ESDE_FILES[2]} ]] && sudo install -D -m 0644 "$tmp/squashfs-root/${ESDE_FILES[2]}" "$ESDE_ICON"
    printf '%s\n' "$version" | sudo tee "$ESDE_SHARE/version" >/dev/null
    if command -v restorecon >/dev/null; then
        sudo restorecon -q "$ESDE_BIN" "$ESDE_DESKTOP" "$ESDE_ICON" 2>/dev/null || true
        sudo restorecon -qR "$ESDE_SHARE"
    fi
    rm -rf "$tmp"
    ui_ok "ES-DE $version instalado em $ESDE_BIN, com atalho no menu${current:+ (antes: $current)}"
}

remove_esde() {
    [[ -e $ESDE_BIN || -d $ESDE_SHARE ]] || return 0
    sudo rm -f "$ESDE_BIN" "$ESDE_DESKTOP" "$ESDE_ICON"
    sudo rm -rf "$ESDE_SHARE"
    ui_ok "ES-DE removido (programa e atalho do menu)"
}

emulation() {
    local user=$1 kind text
    shift
    while read -r kind text; do
        case $kind in
            ok)   ui_ok "$text" ;;
            warn) ui_warn "$text" ;;
            *)    ui_info "$text" ;;
        esac
    done < <(as_user "$user" python3 -I - "$@" < scripts/emulation.py)
}

import_folder() {
    local user=$1 source=$2 target=$3 pattern excludes=()
    shift 3
    for pattern; do excludes+=(--exclude="$pattern"); done
    ui_info "copiando $source para $target (pode demorar)..."
    sudo mkdir -p "$target"
    sudo tar -C "$source" "${excludes[@]}" -cf - . | sudo tar -C "$target" --no-same-owner -xf -
    sudo chown -R "$user:$(id -gn "$user")" "$target"
    sudo chmod -R u+rwX,go-w "$target"
}

has_files() {
    [[ -n $(ls -A "$1" 2>/dev/null) ]]
}

load_retroarch() {
    local user=$1 force=${2:-false} target source="" backup
    target="$(games_home "$user")/.astro/arcade/retroarch"
    backup="$(backup_folder retroarch)"
    if ! $force; then
        [[ -e $target/retroarch.cfg ]] && return 0
        if [[ -n $backup ]] && ui_confirm "restaurar o RetroArch do backup em $backup?" y; then
            source=$backup
        elif ! ui_confirm "carregar uma configuração existente do RetroArch (retroarch.cfg, saves, states, BIOS...)?" n; then
            return 0
        fi
    elif [[ -n $backup ]] && ui_confirm "carregar o RetroArch do backup em $backup?" y; then
        source=$backup
    fi
    [[ -n $source ]] || ui_browse source "Qual a pasta de configuração do RetroArch?" "${BROWSE_ROOTS[@]}"
    [[ -e $source/retroarch.cfg ]] || ui_warn "$source não tem retroarch.cfg: copiando o resto assim mesmo"
    import_folder "$user" "$source" "$target" '*.dll' '*.exe'
    ui_ok "configuração do RetroArch carregada de $source (sem os .dll e .exe do Windows)"
}

load_esde() {
    local user=$1 force=${2:-false} target source="" backup
    target="$(games_home "$user")/.astro/arcade/es-de"
    backup="$(backup_folder es-de)"
    if ! $force; then
        [[ -e $target/settings/es_settings.xml ]] && return 0
        if [[ -n $backup ]] && ui_confirm "restaurar o ES-DE do backup em $backup (com gamelists e temas)?" y; then
            source=$backup
        elif ! ui_confirm "carregar uma configuração existente do ES-DE (settings, temas, coleções...)?" n; then
            return 0
        fi
    elif [[ -n $backup ]] && ui_confirm "carregar o ES-DE do backup em $backup (com gamelists e temas)?" y; then
        source=$backup
    fi
    if [[ -z $source ]]; then
        ui_info "é a pasta de dados do ES-DE, com settings/ dentro (no Windows, a pasta ES-DE ao lado do ES-DE.exe)"
        ui_browse source "Qual a pasta de configuração do ES-DE?" "${BROWSE_ROOTS[@]}"
    fi
    if [[ ! -d $source/settings && -d $source/ES-DE/settings ]]; then
        source="$source/ES-DE"
        ui_info "usando $source, que tem a pasta settings/"
    fi
    [[ -d $source/settings ]] || ui_warn "$source não tem settings/: copiando assim mesmo"
    import_folder "$user" "$source" "$target" 'logs'
    ui_ok "configuração do ES-DE carregada de $source"
}

load_gamelists() {
    local user=$1 force=${2:-false} target source
    target="$(games_home "$user")/.astro/arcade/es-de/gamelists"
    if ! $force; then
        has_files "$target" && return 0
        ui_confirm "carregar gamelists existentes (uma pasta por sistema, com gamelist.xml)?" n || return 0
    fi
    ui_browse source "Onde estão as gamelists?" "${BROWSE_ROOTS[@]}"
    import_folder "$user" "$source" "$target"
    ui_ok "gamelists carregadas de $source"
}

check_folders() {
    local user=$1 path roms=()
    rom_dirs roms
    for path in "$(env_get MEDIA_DIR)" "${roms[@]}"; do
        [[ -n $path ]] || continue
        if ! as_user "$user" test -r "$path" -a -x "$path"; then
            ui_warn "$user não lê $path: use uma pasta de um disco compartilhado (\"Discos da máquina\")"
        fi
    done
}

apply_esde() {
    local user=$1 home roms=()
    home="$(games_home "$user")"
    rom_dirs roms
    check_folders "$user"
    emulation "$user" settings "$home/.astro/arcade/es-de/settings/es_settings.xml" "${roms[0]}" "$(env_get MEDIA_DIR)"
    emulation "$user" systems "$ESDE_SHARE/es_systems.xml" "$home/.astro/arcade/es-de/custom_systems" "${roms[@]}"
}

apply_retroarch() {
    local user=$1 update=${2:-0} home roms=()
    home="$(games_home "$user")"
    rom_dirs roms
    emulation "$user" retroarch-cfg "$home/.astro/arcade/retroarch/retroarch.cfg"
    ui_info "conferindo os núcleos do RetroArch dos sistemas encontrados (o primeiro download demora)..."
    emulation "$user" cores "$ESDE_SHARE/es_systems.xml" "$home/.astro/arcade/retroarch/cores" "$update" "${roms[@]}"
}

cmd_install() {
    state_setup
    browse_roots
    configure
    local user host autologin_mode
    user="$(env_get GAMES_USER)"
    host="$(env_get SUNSHINE_HOST)"
    autologin_mode="$(env_get AUTOLOGIN yes)"

    ui_step "Host"
    host_nvidia_driver
    host_intel_media
    install_packages

    ui_step "Usuário de jogos"
    create_user "$user"
    games_state "$user"
    games_password "$user"
    desktop_settings "$user" "$autologin_mode"
    if [[ $autologin_mode == yes ]]; then
        autologin "$user"
    elif [[ $(gdm_autologin_user) == "$user" ]]; then
        autologin_off
    else
        ui_ok "$user entra pela tela de login, com a senha"
    fi
    primary_gpu

    ui_step "ES-DE e RetroArch"
    install_retroarch
    retroarch_gl
    install_esde
    load_retroarch "$user"
    load_esde "$user"
    load_gamelists "$user"
    apply_esde "$user"
    apply_retroarch "$user"
    games_acl "$user"

    ui_step "Sunshine"
    install_sunshine
    grant_capture
    display_check
    capture_settings "$user"
    origin_settings "$user" "$host"
    display_switch "$user"
    emulation "$user" sunshine-apps "$(games_home "$user")/.astro/arcade/sunshine/apps.json" "$ESDE_BIN"
    speakers_setup "$user"
    enable_service "$user"
    host_firewall "${STREAM_PORTS[@]}"
    host_firewall_block_lan "$WEB_PORT"

    ui_step "Caddy"
    proxy_publish "$host" "https+insecure://host.containers.internal:$WEB_PORT"

    ui_step "Acesso"
    ui_ok "painel do Sunshine: https://$host"
    ui_ok "Moonlight: $(host_lan_ip)"
    ui_ok "ES-DE: no menu de aplicativos de $user (o RetroArch abre pelo ES-DE)"
    if [[ $autologin_mode != yes ]] && ! user_session_active "$user"; then
        $HOST_REBOOT && ui_warn "reinicie a máquina para concluir: sudo systemctl reboot"
        ui_info "o Sunshine roda dentro da sessão de $user: entre com $user na tela para ele começar a transmitir"
    elif $HOST_REBOOT || ! user_manager_running "$user"; then
        ui_warn "reinicie a máquina para concluir: sudo systemctl reboot"
    elif ! user_session_active "$user"; then
        ui_warn "a sessão de $user não está na tela: o Sunshine só transmite e recebe os controles dela"
        ui_info "encerre a outra sessão gráfica (Sair) para a de $user voltar, ou reinicie a máquina"
    fi
}

cmd_actions() {
    printf '%s\n' \
        "retroarch|Carregar uma configuração do RetroArch" \
        "esde|Carregar uma configuração do ES-DE" \
        "gamelists|Carregar gamelists" \
        "folders|Trocar as pastas de ROMs e de mídias" \
        "update|Atualizar ES-DE, RetroArch e núcleos"
}

cmd_action() {
    local user
    cmd_status || ui_fail "instale o arcade antes"
    user="$(env_get GAMES_USER)"
    browse_roots
    case "${1:-}" in
        retroarch)
            ui_step "RetroArch"
            load_retroarch "$user" true
            emulation "$user" retroarch-cfg "$(games_home "$user")/.astro/arcade/retroarch/retroarch.cfg"
            ;;
        esde)
            ui_step "ES-DE"
            load_esde "$user" true
            apply_esde "$user"
            ;;
        gamelists)
            ui_step "Gamelists"
            load_gamelists "$user" true
            ;;
        folders)
            ui_step "Pastas"
            choose_media true
            choose_roms true
            apply_esde "$user"
            apply_retroarch "$user"
            ;;
        update)
            ui_step "Atualização"
            install_esde
            update_retroarch
            retroarch_gl
            apply_esde "$user"
            apply_retroarch "$user" 1
            ;;
        *)
            ui_fail "ação desconhecida: ${1:-}"
            ;;
    esac
    games_acl "$user"
}

remove_games_user() {
    local user=$1
    [[ -n $user ]] && id "$user" >/dev/null 2>&1 || return 0
    if [[ $user == "$USER" ]] || (($(id -u "$user") < 1000)); then
        ui_warn "$user não é um usuário de jogos: mantido"
        return 0
    fi
    sudo loginctl terminate-user "$user" 2>/dev/null || true
    if ! timeout 30 bash -c "while pgrep -u '$user' >/dev/null; do sleep 1; done"; then
        sudo pkill -KILL -u "$user" || true
        sleep 2
    fi
    sudo userdel -r "$user" 2>&1 | grep -v 'mail spool' | ui_prefix || true
    if id "$user" >/dev/null 2>&1; then
        ui_warn "não foi possível apagar o usuário $user"
        return 1
    fi
    ui_ok "usuário $user apagado, com a home"
}

cmd_remove() {
    local user bin
    user="$(env_get GAMES_USER)"

    ui_step "Remoção"
    if [[ -n $user && $(gdm_autologin_user) == "$user" ]]; then
        autologin_off
    fi
    remove_games_user "$user"
    remove_esde
    if command -v sunshine >/dev/null; then
        bin="$(readlink -f "$(command -v sunshine)")"
        if getcap "$bin" | grep -q cap_sys_admin; then
            sudo setcap -r "$bin"
            ui_ok "permissão de captura de tela tirada do Sunshine"
        fi
    fi
    if [[ -e $DISPLAY_BIN || -e $SPEAKERS_BIN ]]; then
        sudo rm -f "$DISPLAY_BIN" "$SPEAKERS_BIN"
        ui_ok "ajuste de resolução e alto-falantes removidos"
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
    state_purge
    ui_info "mantidos: pacote do Sunshine, RetroArch (Flatpak) e driver da NVIDIA"
}

arcade_sync() {
    local base=$1 dest disk log
    dest="$(env_get ARCADE_BACKUP)"
    [[ -n $dest ]] || return 0
    disk="$(cut -d/ -f1-3 <<< "$dest")"
    if [[ $disk == "$DISK_ROOT"/* ]] && ! mountpoint -q "$disk"; then
        ui_error "$disk não está montado: o backup do RetroArch e do ES-DE não foi feito"
        return 1
    fi
    if ! command -v rclone >/dev/null; then
        ui_error "o backup do RetroArch e do ES-DE precisa do rclone: instale o Astro de novo"
        return 1
    fi
    mkdir -p "$dest"
    if ! log="$(rclone --config /dev/null sync "$base" "$dest" --skip-links --log-level ERROR \
            --filter-from <(printf '%s\n' "${ARCADE_BACKUP_FILTER[@]}") 2>&1)"; then
        printf '%s\n' "$log" | ui_prefix
        ui_error "o backup do RetroArch e do ES-DE em $dest falhou"
        return 1
    fi
    ui_ok "RetroArch e ES-DE copiados para $dest"
}

cmd_backup() {
    local user base
    user="$(env_get GAMES_USER)"
    [[ -n $user ]] || return 0
    base="$(games_home "$user")/.astro/arcade"
    if [[ ! -r $base ]]; then
        ui_warn "sem leitura em ~$user/.astro/arcade: rode a instalação do arcade" >&2
        return 0
    fi
    arcade_sync "$base" >&2 || return 1
    if [[ -d $base/sunshine ]]; then
        printf 'include sunshine %s\nexclude %s\n' "$base/sunshine" "$base/sunshine/sunshine.log*"
    fi
    if [[ -f $base/retroarch/retroarch.cfg ]]; then
        printf 'include retroarch.cfg %s\n' "$base/retroarch/retroarch.cfg"
    fi
    if [[ -f $base/es-de/settings/es_settings.xml ]]; then
        printf 'include es_settings.xml %s\n' "$base/es-de/settings/es_settings.xml"
    fi
}

cmd_restore() {
    local from=$1 user home base group
    state_restore "$from"
    [[ -e $STATE/sunshine || -e $STATE/retroarch.cfg || -e $STATE/es_settings.xml ]] || return 0
    user="$(env_get GAMES_USER)"
    home="$(games_home "$user" 2>/dev/null || true)"
    if [[ -z $home ]]; then
        ui_warn "usuário de jogos $user não existe: a configuração dele ficou em $STATE"
        return 0
    fi
    base="$home/.astro/arcade"
    group="$(id -gn "$user")"
    stop_sunshine "$user"
    if [[ -d $STATE/sunshine ]]; then
        sudo rm -rf "$base/sunshine"
        sudo mkdir -p "$base"
        sudo cp -a "$STATE/sunshine" "$base/sunshine"
        ui_ok "Sunshine de $user restaurado (pareamentos e painel)"
    fi
    if [[ -f $STATE/retroarch.cfg ]]; then
        sudo install -D -m 0644 "$STATE/retroarch.cfg" "$base/retroarch/retroarch.cfg"
        ui_ok "retroarch.cfg de $user restaurado"
    fi
    if [[ -f $STATE/es_settings.xml ]]; then
        sudo install -D -m 0644 "$STATE/es_settings.xml" "$base/es-de/settings/es_settings.xml"
        ui_ok "es_settings.xml de $user restaurado"
    fi
    sudo chown -R "$user:$group" "$home/.astro"
    podman unshare rm -rf "$STATE/sunshine" "$STATE/retroarch.cfg" "$STATE/es_settings.xml"
    games_state "$user"
    stop_sunshine "$user" start
}

case "${1:-}" in
    describe) cmd_describe ;;
    status)   cmd_status ;;
    actions)  cmd_actions ;;
    action)   shift; cmd_action "$@" ;;
    install)  cmd_install ;;
    remove)   cmd_remove ;;
    backup)   cmd_backup ;;
    restore)  shift; cmd_restore "$1" ;;
    *)        ui_fail "uso: $0 describe | status | actions | action <id> | install | remove | backup | restore <pasta>" ;;
esac
