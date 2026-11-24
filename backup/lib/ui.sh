ASTROVERSO_PROJECT="${ASTROVERSO_PROJECT:-astroverso}"

_ui_tag() { printf '\033[1;36m[%s]\033[0m' "$ASTROVERSO_PROJECT"; }

export SUDO_PROMPT=$'\033[1;36m'"[$ASTROVERSO_PROJECT]"$'\033[0m     \033[35m?\033[0m senha do sudo: '

ui_step()  { printf '\n%s \033[1;34m==>\033[0m \033[1m%s\033[0m\n' "$(_ui_tag)" "$*"; }
ui_info()  { printf '%s     %s\n' "$(_ui_tag)" "$*"; }
ui_ok()    { printf '%s     \033[32m✔\033[0m %s\n' "$(_ui_tag)" "$*"; }
ui_warn()  { printf '%s     \033[33m!\033[0m %s\n' "$(_ui_tag)" "$*"; }
ui_error() { printf '%s     \033[31m✘\033[0m %s\n' "$(_ui_tag)" "$*" >&2; }
ui_fail()  { ui_error "$*"; exit 1; }

ui_prefix() {
    sed -u "s/^/$(_ui_tag | sed 's/[\/&]/\\&/g')       /"
}

_ui_ask() {
    local text
    read -rp "$(_ui_tag)     $(printf '\033[35m?\033[0m') $1" text </dev/tty
    printf '%s' "$text"
}

ui_input() {
    local -n __ui_out=$1
    local label=$2 default=${3:-} validator=${4:-} answer
    while true; do
        answer="$(_ui_ask "$label${default:+ [$default]}: ")"
        answer="${answer:-$default}"
        if [[ -z $answer ]]; then
            ui_warn "valor obrigatório"
        elif [[ -n $validator ]] && ! answer="$($validator "$answer")"; then
            ui_warn "valor inválido"
        else
            break
        fi
    done
    __ui_out=$answer
}

ui_secret() {
    local -n __ui_out=$1
    local label=$2 first second
    while true; do
        read -rsp "$(_ui_tag)     $(printf '\033[35m?\033[0m') $label: " first </dev/tty; echo
        read -rsp "$(_ui_tag)     $(printf '\033[35m?\033[0m') confirme: " second </dev/tty; echo
        if [[ -z $first ]]; then
            ui_warn "valor obrigatório"
        elif [[ $first != "$second" ]]; then
            ui_warn "os valores não conferem"
        else
            break
        fi
    done
    __ui_out=$first
}

ui_list() {
    local -n __ui_out=$1
    local label=$2 validator=${3:-} item normalized
    __ui_out=()
    while true; do
        item="$(_ui_ask "$label (Enter vazio para terminar): ")"
        [[ -z $item ]] && break
        if [[ -n $validator ]]; then
            if ! normalized="$($validator "$item")"; then
                ui_warn "valor inválido: $item"
                continue
            fi
            item=$normalized
        fi
        __ui_out+=("$item")
    done
}

ui_confirm() {
    local question=$1 default=${2:-n} hint answer
    [[ $default == y ]] && hint="S/n" || hint="s/N"
    answer="$(_ui_ask "$question [$hint] ")"
    answer="${answer:-$default}"
    [[ ${answer,,} == [sy]* ]]
}

_ui_cursor_hide() {
    printf '\033[?25l' >/dev/tty
    stty -echo </dev/tty 2>/dev/null || true
}

_ui_cursor_show() {
    stty echo </dev/tty 2>/dev/null || true
    printf '\033[?25h' >/dev/tty
}

trap '_ui_cursor_show; echo >/dev/tty; exit 130' INT

_ui_read_key() {
    local key rest
    IFS= read -rsn1 key </dev/tty
    if [[ $key == $'\e' ]]; then
        IFS= read -rsn2 -t 0.5 rest </dev/tty || true
        case $rest in
            '[A'|'OA') key=up ;;
            '[B'|'OB') key=down ;;
            *)    key=esc ;;
        esac
    fi
    case $key in
        k) key=up ;;
        j) key=down ;;
        '') key=enter ;;
        ' ') key=space ;;
    esac
    printf '%s' "$key"
}

ui_menu() {
    local -n __ui_out=$1
    local title=$2
    shift 2
    local items=("$@") count=$# cursor=0 i key back="" hint="↑/↓ e Enter"
    case ${items[count - 1]} in
        Voltar) back=$((count - 1)); hint+=", Esc volta" ;;
        Sair)   back=$((count - 1)); hint+=", Esc sai" ;;
    esac

    printf '%s     \033[35m?\033[0m %s \033[2m(%s)\033[0m\n' "$(_ui_tag)" "$title" "$hint" >/dev/tty
    _ui_cursor_hide
    while true; do
        for ((i = 0; i < count; i++)); do
            if ((i == cursor)); then
                printf '\r\033[K%s       \033[36m❯ %d. %s\033[0m\n' "$(_ui_tag)" $((i + 1)) "${items[i]}"
            else
                printf '\r\033[K%s         %d. %s\n' "$(_ui_tag)" $((i + 1)) "${items[i]}"
            fi
        done >/dev/tty
        key="$(_ui_read_key)"
        case $key in
            up)    cursor=$(((cursor - 1 + count) % count)) ;;
            down)  cursor=$(((cursor + 1) % count)) ;;
            enter) break ;;
            esc)   if [[ -n $back ]]; then cursor=$back; break; fi ;;
            [1-9]) if ((key <= count)); then cursor=$((key - 1)); fi ;;
        esac
        printf '\033[%dA' "$count" >/dev/tty
    done
    _ui_cursor_show
    __ui_out=$cursor
}

ui_checklist() {
    local -n __ui_out=$1
    local title=$2 preset="" offset=0 esc=0 hint="↑/↓, Espaço marca, a = todos, Enter confirma"
    shift 2
    UI_CANCELLED=0
    while [[ ${1:-} == --selected || ${1:-} == --all || ${1:-} == --esc ]]; do
        if [[ $1 == --all ]]; then
            offset=1
            shift
        elif [[ $1 == --esc ]]; then
            esc=1
            hint+=", Esc volta"
            shift
        else
            preset=" $2 "
            shift 2
        fi
    done
    local items=("$@") count=$# cursor=0 i key mark all label on total
    local -a selected=()
    for ((i = 0; i < count; i++)); do
        selected[i]=0
        [[ $preset == *" $i "* ]] && selected[i]=1
    done
    total=$((count + offset))

    printf '%s     \033[35m?\033[0m %s \033[2m(%s)\033[0m\n' "$(_ui_tag)" "$title" "$hint" >/dev/tty
    _ui_cursor_hide
    while true; do
        all=1
        for ((i = 0; i < count; i++)); do ((selected[i])) || all=0; done
        for ((i = 0; i < total; i++)); do
            if ((i < offset)); then
                label="Todos"
                on=$all
            else
                label="${items[i - offset]}"
                on=${selected[i - offset]}
            fi
            ((on)) && mark=$'\033[32m◉\033[0m' || mark='○'
            if ((i == cursor)); then
                printf '\r\033[K%s       \033[36m❯\033[0m %s \033[36m%s\033[0m\n' "$(_ui_tag)" "$mark" "$label"
            else
                printf '\r\033[K%s         %s %s\n' "$(_ui_tag)" "$mark" "$label"
            fi
        done >/dev/tty
        key="$(_ui_read_key)"
        case $key in
            up)    cursor=$(((cursor - 1 + total) % total)) ;;
            down)  cursor=$(((cursor + 1) % total)) ;;
            space)
                if ((cursor < offset)); then
                    for ((i = 0; i < count; i++)); do selected[i]=$((1 - all)); done
                else
                    selected[cursor - offset]=$((1 - selected[cursor - offset]))
                fi
                ;;
            a)
                for ((i = 0; i < count; i++)); do selected[i]=$((1 - all)); done
                ;;
            enter) break ;;
            esc)
                if ((esc)); then
                    UI_CANCELLED=1
                    for ((i = 0; i < count; i++)); do selected[i]=0; done
                    break
                fi
                ;;
        esac
        printf '\033[%dA' "$total" >/dev/tty
    done
    _ui_cursor_show
    __ui_out=()
    for ((i = 0; i < count; i++)); do
        ((selected[i])) && __ui_out+=("$i")
    done
    return 0
}

if [[ ${ASTROVERSO_PLAIN:-} == 1 ]]; then
    _ui_tag()  { printf '[%s]' "$ASTROVERSO_PROJECT"; }
    ui_step()  { printf '%s ==> %s\n' "$(_ui_tag)" "$*"; }
    ui_info()  { printf '%s     %s\n' "$(_ui_tag)" "$*"; }
    ui_ok()    { printf '%s     ok: %s\n' "$(_ui_tag)" "$*"; }
    ui_warn()  { printf '%s     aviso: %s\n' "$(_ui_tag)" "$*"; }
    ui_error() { printf '%s     erro: %s\n' "$(_ui_tag)" "$*" >&2; }
fi

_ui_scroll() {
    local -n __ui_sel=$1
    local title=$2
    shift 2
    local items=("$@") count=$# cursor=0 top=0 rows i key lines
    rows=$((count < 12 ? count : 12))
    printf '%s     \033[35m?\033[0m %s \033[2m(↑/↓ e Enter)\033[0m\n' "$(_ui_tag)" "$title" >/dev/tty
    _ui_cursor_hide
    while true; do
        ((cursor < top)) && top=$cursor
        ((cursor >= top + rows)) && top=$((cursor - rows + 1))
        for ((i = top; i < top + rows; i++)); do
            if ((i == cursor)); then
                printf '\r\033[K%s       \033[36m❯ %s\033[0m\n' "$(_ui_tag)" "${items[i]}"
            else
                printf '\r\033[K%s         %s\n' "$(_ui_tag)" "${items[i]}"
            fi
        done >/dev/tty
        lines=$rows
        if ((count > rows)); then
            printf '\r\033[K%s         \033[2m%d de %d\033[0m\n' "$(_ui_tag)" $((cursor + 1)) "$count" >/dev/tty
            lines=$((rows + 1))
        fi
        key="$(_ui_read_key)"
        case $key in
            up)    cursor=$(((cursor - 1 + count) % count)) ;;
            down)  cursor=$(((cursor + 1) % count)) ;;
            enter) break ;;
        esac
        printf '\033[%dA' "$lines" >/dev/tty
    done
    printf '\033[%dA\033[J' $((lines + 1)) >/dev/tty
    _ui_cursor_show
    __ui_sel=$cursor
}

ui_browse() {
    local -n __ui_path=$1
    local __ui_title=$2 __ui_current="" __ui_choice __ui_entry __ui_name __ui_root __ui_entries __ui_labels
    shift 2
    local __ui_roots=("$@")
    while true; do
        __ui_entries=()
        __ui_labels=()
        if [[ -z $__ui_current ]]; then
            for __ui_entry in "${__ui_roots[@]}"; do
                __ui_entries+=("$__ui_entry")
                __ui_labels+=("$__ui_entry")
            done
            __ui_entries+=(":digitar")
            __ui_labels+=("digitar um caminho")
        else
            __ui_entries+=(":usar" ":voltar")
            __ui_labels+=("✔ usar esta pasta" "↩ voltar")
            while IFS= read -r -d '' __ui_entry; do
                __ui_name=${__ui_entry##*/}
                [[ $__ui_name == .* || $__ui_name == '$RECYCLE.BIN' || $__ui_name == 'System Volume Information' || $__ui_name == lost+found ]] && continue
                __ui_entries+=("$__ui_entry")
                __ui_labels+=("$__ui_name/")
            done < <(find "$__ui_current" -mindepth 1 -maxdepth 1 -type d -print0 2>/dev/null | sort -z)
        fi
        _ui_scroll __ui_choice "$__ui_title${__ui_current:+ $__ui_current}" "${__ui_labels[@]}"
        case ${__ui_entries[__ui_choice]} in
            :usar)
                __ui_path=$__ui_current
                break
                ;;
            :voltar)
                for __ui_root in "${__ui_roots[@]}"; do
                    [[ $__ui_current == "$__ui_root" ]] && __ui_current="" && continue 2
                done
                __ui_current=${__ui_current%/*}
                [[ -n $__ui_current ]] || __ui_current=/
                ;;
            :digitar)
                ui_input __ui_entry "caminho da pasta"
                __ui_entry=${__ui_entry%/}
                if [[ $__ui_entry == /* && -d $__ui_entry ]]; then
                    __ui_path=$__ui_entry
                    break
                fi
                ui_warn "pasta não encontrada: $__ui_entry"
                ;;
            *)
                __ui_current=${__ui_entries[__ui_choice]}
                ;;
        esac
    done
    printf '%s     \033[35m?\033[0m %s %s\n' "$(_ui_tag)" "$__ui_title" "$__ui_path"
}
