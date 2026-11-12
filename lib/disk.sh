DISK_FSTAB=/etc/fstab
DISK_CRYPTTAB=/etc/crypttab
DISK_ROOT=/srv
DISK_MOUNTS=()
DISK_CHECK_BIN="$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/disk-check.sh"
DISK_CHECK_UNIT=astro-disk-check

disk_scan() {
    lsblk -J -b --tree -o PATH,UUID,LABEL,SIZE,FSTYPE,TYPE,MOUNTPOINTS,MODEL | python3 -I -c '
import json, sys
SYSTEM = {"/", "/boot", "/boot/efi", "/efi", "/home", "/usr", "/var", "[SWAP]"}
KNOWN = {"ext4", "xfs", "btrfs", "ntfs", "exfat", "vfat", "crypto_LUKS"}

def tree(node):
    yield node
    for child in node.get("children") or []:
        yield from tree(child)

def human(size):
    for unit in ("B", "K", "M", "G", "T"):
        if size < 1024 or unit == "T":
            return f"{size:.1f}{unit}" if unit in "GT" else f"{size}{unit}"
        size /= 1024

for disk in json.load(sys.stdin)["blockdevices"]:
    if disk.get("type") != "disk":
        continue
    if any(set(filter(None, node.get("mountpoints") or [])) & SYSTEM for node in tree(disk)):
        continue
    model = (disk.get("model") or "").strip() or "-"
    for part in disk.get("children") or [disk]:
        if part.get("fstype") not in KNOWN or not part.get("uuid") or part["size"] < 2**30:
            continue
        inner = {}
        if part["fstype"] == "crypto_LUKS":
            inner = next(iter(part.get("children") or []), {})
        label = inner.get("label") or part.get("label") or "-"
        print("\t".join([part["uuid"], part["path"], part["fstype"], label, human(part["size"]), model,
                         inner.get("fstype") or "-"]))
'
}

disk_read() {
    if [[ -r $1 ]]; then
        cat "$1"
    elif [[ -e $1 ]]; then
        sudo cat "$1"
    fi
}

DISK_OURS='
function ours(line,  f) {
    split(line, f, /[ \t]+/)
    if (kind == "fstab")
        return index(f[2], root "/") == 1 && f[4] ~ /x-udisks-auth/ && f[4] ~ /container_file_t/
    return f[1] ~ /^luks-/ && f[4] ~ /headless=true/
}
function owns(uuid, line,  part, count, esc, i) {
    count = split(uuid, part, "-")
    esc = part[1]
    for (i = 2; i <= count; i++)
        esc = esc "\\x2d" part[i]
    return uuid != "" && (index(line, uuid) || index(line, esc))
}
'

disk_awk() {
    local kind=crypttab
    [[ $1 == "$DISK_FSTAB" ]] && kind=fstab
    disk_read "$1" | awk -v kind="$kind" -v root="$DISK_ROOT" "$DISK_OURS$2"
    return 0
}

disk_block() {
    disk_awk "$1" '
        /^# astro / { marker = $0; uuid = $3; next }
        marker != "" { if (ours($0) && owns(uuid, $0)) { print marker; print }; marker = "" }
    '
}

disk_orphans() {
    disk_awk "$1" '
        /^# astro / { uuid = $3; next }
        { if (ours($0) && !owns(uuid, $0)) print; uuid = "" }
    '
}

disk_configured() {
    disk_block "$DISK_FSTAB" | awk '
        /^# astro / {
            uuid = $3
            type = ($4 == "compartilhado") ? "compartilhado" : "privado"
            getline
            print uuid, type, $2
        }
    '
}

disk_mounts() {
    local uuid type target
    while read -r uuid type target; do
        printf '%s %s\n' "$target" "$type"
    done < <(disk_configured)
}

disk_responds() {
    local path=$1 source dm slave
    source="$(findmnt -no SOURCE "$path" 2>/dev/null || true)"
    if [[ $source == /dev/mapper/* ]]; then
        dm="$(basename "$(readlink -f "$source")")"
        for slave in /sys/block/"$dm"/slaves/*; do
            [[ -e $slave ]] || return 1
        done
    fi
    timeout 20 ls -ld "$path" >/dev/null 2>&1 && timeout 20 ls -A "$path" >/dev/null 2>&1
}

disk_check_units() {
    local dir="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
    mkdir -p "$dir"
    printf '[Unit]\nDescription=astro: confere se os discos da máquina respondem\n\n[Service]\nType=oneshot\nEnvironment=ASTRO_PLAIN=1\nExecStart=%s\n' \
        "$DISK_CHECK_BIN" > "$dir/$DISK_CHECK_UNIT.service"
    printf '[Unit]\nDescription=astro: confere os discos a cada 15 minutos\n\n[Timer]\nOnBootSec=5min\nOnUnitActiveSec=15min\n\n[Install]\nWantedBy=timers.target\n' \
        > "$dir/$DISK_CHECK_UNIT.timer"
    systemctl --user daemon-reload
    systemctl --user enable -q --now "$DISK_CHECK_UNIT.timer"
    ui_ok "discos conferidos a cada 15 minutos: um disco que some ou para de responder gera aviso no Discord"
}

disk_check_remove() {
    local dir="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
    [[ -e $dir/$DISK_CHECK_UNIT.timer ]] || return 0
    systemctl --user disable -q --now "$DISK_CHECK_UNIT.timer" 2>/dev/null || true
    rm -f "$dir/$DISK_CHECK_UNIT.timer" "$dir/$DISK_CHECK_UNIT.service"
    systemctl --user daemon-reload
    ui_ok "verificação dos discos removida"
}

disk_type() {
    disk_configured | awk -v target="$1" '$3 == target { print $2; exit }'
}

disk_line() {
    disk_block "$1" | awk -v uuid="$2" '/^# astro / { match_uuid = ($3 == uuid); next } match_uuid { print; match_uuid = 0 }'
}

disk_block_write() {
    local file=$1 current wanted
    shift
    current="$(disk_read "$file")"
    wanted="$(
        if [[ -n $current ]]; then
            disk_awk "$file" '/^# astro / { next } ours($0) { next } { print }'
        fi
        if (($#)); then
            printf '%s\n' "$@"
        fi
    )"
    [[ $wanted == "$current" ]] && return 0
    if [[ -e $file && ! -e $file.astro-bak ]]; then
        sudo cp -a "$file" "$file.astro-bak"
    fi
    printf '%s\n' "$wanted" | sudo tee "$file" >/dev/null
    [[ $file == "$DISK_CRYPTTAB" ]] && sudo chmod 600 "$file"
    return 0
}

disk_hotplug_link() {
    local wants
    wants="/etc/systemd/system/$(systemd-escape -p --suffix=device "$1").wants"
    [[ -L $wants/$2 ]] && return 0
    sudo mkdir -p "$wants"
    sudo ln -sfn "/run/systemd/generator/$2" "$wants/$2"
}

disk_hotplug_unlink() {
    sudo find /etc/systemd/system -path '*.device.wants/*' -name "${1//\\/\\\\}" -delete 2>/dev/null || true
    sudo find /etc/systemd/system -name '*.device.wants' -type d -empty -delete 2>/dev/null || true
}

disk_tpm_ok() {
    sudo cryptsetup open --test-passphrase --token-only "$1" >/dev/null 2>&1
}

disk_tpm_enroll() {
    local device=$1 name=$2 password log
    if disk_tpm_ok "$device"; then
        ui_ok "o TPM já destrava $name"
        return 0
    fi
    if [[ ! -e /dev/tpmrm0 ]]; then
        ui_warn "máquina sem TPM 2.0: $name não pode ser destravado sozinho no boot e fica de fora"
        return 1
    fi
    ui_info "$name é criptografado: digite a senha do LUKS uma vez para cadastrar o TPM"
    ui_info "depois disso o TPM destrava o disco no boot, sem pedir senha; a senha continua valendo como reserva"
    while true; do
        ui_secret password "senha do LUKS de $name"
        if log="$(printf '%s' "$password" | sudo systemd-cryptenroll --unlock-key-file=/dev/stdin \
                --wipe-slot=tpm2 --tpm2-device=auto --tpm2-pcrs=7 "$device" 2>&1)"; then
            break
        fi
        printf '%s\n' "$log" | ui_prefix >&2
        ui_warn "senha recusada pelo LUKS, tente de novo"
    done
    if ! disk_tpm_ok "$device"; then
        ui_warn "o TPM não conseguiu destravar $name logo após o cadastro; ele fica de fora"
        return 1
    fi
    ui_ok "TPM cadastrado: $name destrava sozinho no boot (Secure Boot conferido, PCR 7)"
}

disk_release_target() {
    local target=$1
    [[ $target == "$DISK_ROOT"/* ]] || return 0
    disk_hotplug_unlink "$(systemd-escape -p --suffix=mount "$target")"
    if mountpoint -q "$target"; then
        if sudo umount "$target"; then
            ui_ok "$target desmontado"
        else
            ui_warn "$target está em uso: ele sai do fstab e deixa de montar no próximo boot"
        fi
    fi
    if [[ -d $target ]] && ! mountpoint -q "$target"; then
        sudo chattr -i "$target" 2>/dev/null || true
        sudo rmdir "$target" 2>/dev/null || true
    fi
}

disk_release_mapper() {
    local mapper=$1
    disk_hotplug_unlink "systemd-cryptsetup@$(systemd-escape "$mapper").service"
    if [[ -e /dev/mapper/$mapper ]]; then
        sudo cryptsetup close "$mapper" 2>/dev/null || ui_warn "não foi possível travar $mapper (em uso)"
    fi
}

disk_release_unused() {
    local keep=" $1 " marker uuid line target
    while read -r marker; do
        uuid="$(awk '{ print $3 }' <<< "$marker")"
        read -r line
        [[ $keep == *" $uuid "* ]] && continue
        disk_release_target "$(awk '{ print $2 }' <<< "$line")"
    done < <(disk_block "$DISK_FSTAB")
    while read -r line; do
        target="$(awk '{ print $2 }' <<< "$line")"
        [[ " ${DISK_MOUNTS[*]} " == *" $target "* ]] && continue
        disk_release_target "$target"
    done < <(disk_orphans "$DISK_FSTAB")
    while read -r marker; do
        uuid="$(awk '{ print $3 }' <<< "$marker")"
        read -r line
        [[ $keep == *" $uuid "* ]] && continue
        disk_release_mapper "$(awk '{ print $1 }' <<< "$line")"
    done < <(disk_block "$DISK_CRYPTTAB")
    while read -r line; do
        target="$(awk '{ print $1 }' <<< "$line")"
        [[ $keep == *" ${target#luks-} "* ]] && continue
        disk_release_mapper "$target"
    done < <(disk_orphans "$DISK_CRYPTTAB")
}

disk_release_all() {
    local uuid file luks=()
    mapfile -t luks < <(disk_awk "$DISK_CRYPTTAB" 'ours($0) { sub(/^UUID=/, "", $2); print $2 }')
    if [[ -z $(disk_awk "$DISK_FSTAB" '/^# astro / || ours($0)') && -z $(disk_awk "$DISK_CRYPTTAB" '/^# astro / || ours($0)') ]]; then
        ui_ok "nenhum disco montado pelo Astro"
        disk_check_remove
        return 0
    fi
    DISK_MOUNTS=()
    disk_release_unused ""
    disk_block_write "$DISK_CRYPTTAB"
    disk_block_write "$DISK_FSTAB"
    for file in "$DISK_FSTAB" "$DISK_CRYPTTAB"; do
        sudo rm -f "$file.astro-bak"
    done
    disk_check_remove
    sudo systemctl daemon-reload
    ui_ok "discos fora do fstab e do crypttab: deixam de montar no boot (os dados continuam neles)"
    for uuid in "${luks[@]}"; do
        [[ -e /dev/disk/by-uuid/$uuid ]] || continue
        if sudo timeout 60 systemd-cryptenroll --wipe-slot=tpm2 "/dev/disk/by-uuid/$uuid" </dev/null >/dev/null 2>&1; then
            ui_ok "TPM descadastrado do disco $uuid: ele volta a abrir só com a senha"
        else
            ui_warn "não foi possível descadastrar o TPM do disco $uuid (a senha continua valendo)"
        fi
    done
}

disk_options() {
    local fs_type=$1 type=$2 options="context=system_u:object_r:container_file_t:s0"
    if [[ $type == compartilhado ]]; then
        options+=",x-gvfs-show,x-systemd.before=systemd-user-sessions.service"
    else
        options+=",x-gvfs-hide,x-systemd.before=user@$(id -u).service"
    fi
    case $fs_type in
        ntfs3|exfat|vfat)
            if [[ $type == compartilhado ]]; then
                options+=",uid=$(id -u),gid=$(id -g),umask=000"
            else
                options+=",uid=$(id -u),gid=$(id -g),umask=077"
            fi
            ;;
    esac
    printf '%s' "$options"
}

disk_mount_options() {
    awk '{ print $4 }' <<< "$1" | tr ',' '\n' | grep -v '^x-' | sort | tr '\n' ','
}

disk_permissions() {
    local target=$1 type=$2 mode=770
    [[ $type == compartilhado ]] && mode=777
    mountpoint -q "$target" || return 0
    if [[ $(stat -c '%u:%g' "$target") != "$(id -u):$(id -g)" ]]; then
        sudo chown "$(id -u):$(id -g)" "$target" 2>/dev/null || true
    fi
    if [[ $(stat -c '%a' "$target") != "$mode" ]]; then
        sudo chmod "$mode" "$target"
    fi
    if [[ $type == compartilhado ]]; then
        ui_ok "$target: compartilhado, todos os usuários da máquina acessam"
    else
        ui_ok "$target: privado, só $USER acessa"
    fi
}

disk_setup() {
    local arg uuid type device fstype label mapper fs_uuid fs_type name target pass wait_options
    local hotplug=() fstab=() crypttab=() keep=() mounts=()
    local -A seen=() old=()
    DISK_MOUNTS=()
    while read -r uuid type target; do
        old[$uuid]="$(disk_line "$DISK_FSTAB" "$uuid")"
    done < <(disk_configured)
    for arg in "$@"; do
        uuid="${arg%%:*}"
        type="${arg#*:}"
        device="/dev/disk/by-uuid/$uuid"
        if [[ ! -e $device ]]; then
            local old_crypttab
            if [[ -n ${old[$uuid]:-} ]]; then
                old_crypttab="$(disk_line "$DISK_CRYPTTAB" "$uuid")"
                fstab+=("# astro $uuid $type" "${old[$uuid]}")
                [[ -n $old_crypttab ]] && crypttab+=("# astro $uuid" "$old_crypttab")
                keep+=("$uuid")
                DISK_MOUNTS+=("$(awk '{ print $2 }' <<< "${old[$uuid]}")")
                ui_warn "disco $uuid não encontrado: a montagem dele fica configurada e volta quando ele for ligado"
            else
                ui_warn "disco $uuid não encontrado, pulado"
            fi
            continue
        fi
        fstype="$(lsblk -dno FSTYPE "$device")"
        wait_options="x-systemd.device-timeout=10s"
        if [[ $fstype == crypto_LUKS ]]; then
            mapper="luks-$uuid"
            label="$(lsblk -no LABEL "$device" | grep -v '^$' | head -1 || true)"
            disk_tpm_enroll "$device" "${label:-disco $uuid}" || continue
            if [[ ! -e /dev/mapper/$mapper ]] && ! sudo cryptsetup open --token-only "$device" "$mapper"; then
                ui_warn "não foi possível destravar ${label:-o disco $uuid} agora; ele fica de fora"
                continue
            fi
            hotplug+=("/dev/disk/by-uuid/$uuid systemd-cryptsetup@$(systemd-escape "$mapper").service")
            crypttab+=("# astro $uuid"
                "$mapper UUID=$uuid none tpm2-device=auto,headless=true,nofail,x-systemd.device-timeout=10s,x-udisks-auth")
            udevadm settle 2>/dev/null || true
            device="/dev/mapper/$mapper"
            wait_options="x-systemd.device-timeout=5min,x-systemd.requires=systemd-cryptsetup@$(systemd-escape "$mapper").service"
        fi
        read -r fs_uuid fs_type label < <(lsblk -dno UUID,FSTYPE,LABEL "$device")
        if [[ $fstype == crypto_LUKS && -n $label && -z $(lsblk -dno LABEL "/dev/disk/by-uuid/$uuid") ]] \
                && [[ $(lsblk -dno FSVER "/dev/disk/by-uuid/$uuid") == 2 ]]; then
            sudo cryptsetup config --label "$label" "/dev/disk/by-uuid/$uuid"
            ui_ok "nome $label gravado no cabeçalho da criptografia (aparece mesmo com o disco travado)"
        fi
        name="${label:-disco-${uuid:0:8}}"
        [[ $name =~ ^[A-Za-z0-9._-]+$ ]] || name="disco-${uuid:0:8}"
        [[ -n ${seen[$name]:-} ]] && name="$name-${uuid:0:8}"
        seen[$name]=1
        target="$DISK_ROOT/$name"
        [[ $fs_type == ntfs ]] && fs_type=ntfs3
        [[ $fs_type == ext4 || $fs_type == xfs || $fs_type == btrfs ]] && pass=2 || pass=0
        local line="UUID=$fs_uuid $target $fs_type nofail,nosuid,nodev,$wait_options,x-udisks-auth,$(disk_options "$fs_type" "$type") 0 $pass"
        fstab+=("# astro $uuid $type" "$line")
        keep+=("$uuid")
        hotplug+=("/dev/disk/by-uuid/$fs_uuid $(systemd-escape -p --suffix=mount "$target")")
        local changed=false
        if [[ -n ${old[$uuid]:-} && $(disk_mount_options "${old[$uuid]}") != "$(disk_mount_options "$line")" ]]; then
            changed=true
        fi
        mounts+=("$device $target $fs_type $type $changed")
        DISK_MOUNTS+=("$target")
    done

    disk_release_unused "${keep[*]}"
    disk_block_write "$DISK_CRYPTTAB" "${crypttab[@]}"
    disk_block_write "$DISK_FSTAB" "${fstab[@]}"
    local link
    for link in "${hotplug[@]}"; do
        disk_hotplug_link "${link% *}" "${link##* }"
    done
    sudo systemctl daemon-reload

    local entry source mounted log already busy changed
    for entry in "${mounts[@]}"; do
        read -r device target fs_type type changed <<< "$entry"
        source="$(readlink -f "$device")"
        already=false
        busy=false
        while read -r mounted; do
            [[ -n $mounted ]] || continue
            if [[ $mounted == "$target" ]]; then
                already=true
            elif sudo umount "$mounted"; then
                ui_ok "$source desmontado de $mounted"
            else
                busy=true
            fi
        done < <(findmnt -rn -o TARGET -S "$source" 2>/dev/null || true)
        if $busy; then
            ui_warn "$source está em uso em outra sessão: feche os programas que o usam ou reinicie a máquina"
            continue
        fi
        if $already && $changed; then
            if sudo umount "$target" 2>/dev/null; then
                already=false
                ui_ok "$target desmontado para aplicar as opções novas"
            else
                ui_warn "$target está em uso: as opções novas valem a partir do próximo boot"
            fi
        fi
        if $already; then
            ui_ok "$target já montado"
            disk_permissions "$target" "$type"
            continue
        fi
        if ! mountpoint -q "$target"; then
            sudo mkdir -p "$target"
            sudo chattr +i "$target" 2>/dev/null || true
        fi
        if ! log="$(sudo mount "$target" 2>&1)"; then
            printf '%s\n' "$log" | ui_prefix >&2
            if [[ $fs_type == ntfs3 ]]; then
                ui_info "um NTFS fechado sem desligar direito (Windows, inicialização rápida) fica marcado como sujo:"
                ui_info "  sudo ntfsfix -d $source   e rode esta opção de novo"
            fi
            ui_warn "não foi possível montar $target agora; ele fica configurado para o próximo boot"
            continue
        fi
        ui_ok "$source montado em $target (também no boot, sem travar se faltar)"
        disk_permissions "$target" "$type"
    done
}

disk_manage() {
    local uuid type target path fstype label size model inner kind
    local lines=() uuids=() chosen=() shared=() args=() removed=() preset="" i
    local -A current=() targets=()
    ui_step "Discos da máquina"
    while read -r uuid type target; do
        current[$uuid]=$type
        targets[$uuid]=$target
    done < <(disk_configured)
    while IFS=$'\t' read -r uuid path fstype label size model inner; do
        kind=$fstype
        [[ $label == - ]] && label="${path##*/} (${uuid:0:8})"
        if [[ $fstype == crypto_LUKS && $inner == - ]]; then
            kind="criptografado, travado"
        elif [[ $fstype == crypto_LUKS ]]; then
            kind="criptografado, $inner"
        fi
        lines+=("$(printf '%-20s %8s  %-24s %s' "$label" "$size" "$kind" "$model")")
        [[ -n ${current[$uuid]:-} ]] && preset+="${#uuids[@]} "
        uuids+=("$uuid")
    done < <(disk_scan)
    if ((${#uuids[@]} == 0 && ${#current[@]} == 0)); then
        ui_info "nenhum disco além do disco do sistema"
        return 0
    fi
    ui_info "os discos escolhidos montam no boot em $DISK_ROOT/<rótulo>, sempre com $USER como dono"
    ui_checklist chosen "Quais discos a máquina monta?" --selected "$preset" "${lines[@]}"
    local picked=() picked_lines=()
    for i in "${chosen[@]}"; do
        picked+=("${uuids[i]}")
        picked_lines+=("${lines[i]}")
    done
    for uuid in "${!current[@]}"; do
        [[ " ${picked[*]} " == *" $uuid "* ]] && continue
        if [[ " ${uuids[*]} " == *" $uuid "* ]]; then
            removed+=("${targets[$uuid]}")
        else
            picked+=("$uuid")
            picked_lines+=("${targets[$uuid]##*/} (desligado)")
        fi
    done
    if ((${#removed[@]})); then
        ui_warn "deixam de ser montados: ${removed[*]} (os dados continuam nos discos)"
        ui_warn "projetos que usam esses discos (ex.: nextcloud, rclone) param de encontrá-los"
        ui_confirm "confirma?" n || { ui_warn "cancelado, nada mudou"; return 0; }
    fi
    if ((${#picked[@]})); then
        preset=""
        for i in "${!picked[@]}"; do
            [[ ${current[${picked[i]}]:-} == compartilhado ]] && preset+="$i "
        done
        ui_info "privado: só $USER acessa (dados pessoais). compartilhado: todos os usuários da máquina acessam (ex.: jogos)"
        ui_checklist shared "Quais são compartilhados com todos os usuários?" --selected "$preset" "${picked_lines[@]}"
        for i in "${!picked[@]}"; do
            type=privado
            [[ " ${shared[*]} " == *" $i "* ]] && type=compartilhado
            args+=("${picked[i]}:$type")
        done
    fi
    disk_setup "${args[@]}"
    if ((${#DISK_MOUNTS[@]} == 0)); then
        ui_ok "nenhum disco de dados montado pela máquina"
        disk_check_remove
    else
        disk_check_units
    fi
}
