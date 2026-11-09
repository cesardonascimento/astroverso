DISK_FSTAB=/etc/fstab
DISK_CRYPTTAB=/etc/crypttab
DISK_ROOT=/srv
DISK_MOUNTS=()

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

disk_owner() {
    sed -n "s|^# astro:\([a-z0-9_-]*\) $1\$|\1|p" "$DISK_FSTAB" | head -1
}

disk_choose() {
    local -n __disk_out=$1
    local project=$2 title=$3 current=" ${4:-} " uuid path fstype label size model inner owner kind preset=""
    local lines=() uuids=() chosen=() i
    __disk_out=()
    while IFS=$'\t' read -r uuid path fstype label size model inner; do
        owner="$(disk_owner "$uuid")"
        [[ -z $owner || $owner == "$project" ]] || continue
        kind=$fstype
        if [[ $fstype == crypto_LUKS && $inner == - ]]; then
            kind="criptografado, travado"
        elif [[ $fstype == crypto_LUKS ]]; then
            kind="criptografado, $inner"
        fi
        lines+=("$(printf '%-20s %8s  %-24s %s' "$label" "$size" "$kind" "$model")")
        [[ $current == *" $uuid "* ]] && preset+="${#uuids[@]} "
        uuids+=("$uuid")
    done < <(disk_scan)
    if ((${#uuids[@]} == 0)); then
        ui_info "nenhum disco disponível além do disco do sistema"
        return 0
    fi
    ui_checklist chosen "$title" --selected "$preset" "${lines[@]}"
    for i in "${chosen[@]}"; do __disk_out+=("${uuids[i]}"); done
    return 0
}

disk_read() {
    if [[ -r $1 ]]; then
        cat "$1"
    elif [[ -e $1 ]]; then
        sudo cat "$1"
    fi
}

disk_block() {
    disk_read "$1" | awk -v tag="# astro:$2 " '
        index($0, tag) == 1 { print; keep = 1; next }
        keep { print; keep = 0 }
    '
    return 0
}

disk_block_write() {
    local file=$1 project=$2 current wanted
    shift 2
    current="$(disk_read "$file")"
    wanted="$(
        if [[ -n $current ]]; then
            printf '%s\n' "$current" | awk -v tag="# astro:$project " '
                index($0, tag) == 1 { skip = 1; next }
                skip { skip = 0; next }
                { print }
            '
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

disk_release_unused() {
    local project=$1 keep=" $2 " marker uuid target line
    while read -r marker; do
        uuid="${marker##* }"
        read -r line
        [[ $keep == *" $uuid "* ]] && continue
        target="$(awk '{ print $2 }' <<< "$line")"
        if mountpoint -q "$target"; then
            sudo umount "$target"
            ui_ok "$target desmontado"
        fi
        if [[ -d $target ]]; then
            sudo chattr -i "$target" 2>/dev/null || true
            sudo rmdir "$target" 2>/dev/null || true
        fi
    done < <(disk_block "$DISK_FSTAB" "$project")
    while read -r marker; do
        uuid="${marker##* }"
        read -r line
        [[ $keep == *" $uuid "* ]] && continue
        target="$(awk '{ print $1 }' <<< "$line")"
        if [[ -e /dev/mapper/$target ]]; then
            sudo cryptsetup close "$target" 2>/dev/null || ui_warn "não foi possível travar $target (em uso)"
        fi
    done < <(disk_block "$DISK_CRYPTTAB" "$project")
}

disk_setup() {
    local project=$1 options=$2
    shift 2
    local uuid device fstype label mapper fs_uuid fs_type name target pass wait_options fstab=() crypttab=() keep=() mounts=()
    local -A seen=()
    DISK_MOUNTS=()
    if (($# == 0)) && [[ -z $(disk_block "$DISK_FSTAB" "$project") ]]; then
        return 0
    fi
    for uuid in "$@"; do
        device="/dev/disk/by-uuid/$uuid"
        if [[ ! -e $device ]]; then
            local old_fstab old_crypttab
            old_fstab="$(disk_block "$DISK_FSTAB" "$project" | grep -A1 -x "# astro:$project $uuid" || true)"
            old_crypttab="$(disk_block "$DISK_CRYPTTAB" "$project" | grep -A1 -x "# astro:$project $uuid" || true)"
            if [[ -n $old_fstab ]]; then
                mapfile -t -O "${#fstab[@]}" fstab <<< "$old_fstab"
                [[ -n $old_crypttab ]] && mapfile -t -O "${#crypttab[@]}" crypttab <<< "$old_crypttab"
                keep+=("$uuid")
                DISK_MOUNTS+=("$(tail -1 <<< "$old_fstab" | awk '{ print $2 }')")
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
            crypttab+=("# astro:$project $uuid"
                "$mapper UUID=$uuid none tpm2-device=auto,headless=true,nofail,x-systemd.device-timeout=10s,x-udisks-auth")
            udevadm settle 2>/dev/null || true
            device="/dev/mapper/$mapper"
            wait_options="x-systemd.device-timeout=5min,x-systemd.requires=systemd-cryptsetup@$(systemd-escape "$mapper").service"
        fi
        read -r fs_uuid fs_type label < <(lsblk -dno UUID,FSTYPE,LABEL "$device")
        name="${label:-disco-${uuid:0:8}}"
        [[ $name =~ ^[A-Za-z0-9._-]+$ ]] || name="disco-${uuid:0:8}"
        [[ -n ${seen[$name]:-} ]] && name="$name-${uuid:0:8}"
        seen[$name]=1
        target="$DISK_ROOT/$name"
        [[ $fs_type == ntfs ]] && fs_type=ntfs3
        [[ $fs_type == ext4 || $fs_type == xfs || $fs_type == btrfs ]] && pass=2 || pass=0
        fstab+=("# astro:$project $uuid"
            "UUID=$fs_uuid $target $fs_type nofail,nosuid,nodev,$wait_options,x-udisks-auth${options:+,$options} 0 $pass")
        keep+=("$uuid")
        mounts+=("$device $target $fs_type")
        DISK_MOUNTS+=("$target")
    done

    disk_release_unused "$project" "${keep[*]}"
    disk_block_write "$DISK_CRYPTTAB" "$project" "${crypttab[@]}"
    disk_block_write "$DISK_FSTAB" "$project" "${fstab[@]}"
    sudo systemctl daemon-reload

    local entry source mounted log already busy
    for entry in "${mounts[@]}"; do
        read -r device target fs_type <<< "$entry"
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
        if $already; then
            ui_ok "$target já montado"
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
                ui_info "  sudo ntfsfix -d $source   e rode a instalação de novo"
            fi
            ui_warn "não foi possível montar $target agora; ele fica configurado para o próximo boot"
            continue
        fi
        ui_ok "$source montado em $target (também no boot, sem travar se faltar)"
    done
}

disk_release() {
    local project=$1
    disk_release_unused "$project" ""
    disk_block_write "$DISK_FSTAB" "$project"
    disk_block_write "$DISK_CRYPTTAB" "$project"
    sudo systemctl daemon-reload
    ui_ok "discos liberados do $DISK_FSTAB (os dados continuam nos discos)"
}

disk_mounts() {
    awk -v skip="${1:-}" '
        /^# astro:/ { split($2, tag, ":"); project = tag[2]; getline; if (project != skip) print $2, project }
    ' "$DISK_FSTAB"
}
