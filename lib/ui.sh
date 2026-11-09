ASTRO_PROJECT="${ASTRO_PROJECT:-astro}"

_ui_tag() { printf '\033[1;36m[%s]\033[0m' "$ASTRO_PROJECT"; }

export SUDO_PROMPT=$'\033[1;36m'"[$ASTRO_PROJECT]"$'\033[0m     \033[35m?\033[0m senha do sudo: '

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

_ui_cursor_hide() { printf '\033[?25l' >/dev/tty; }
_ui_cursor_show() { printf '\033[?25h' >/dev/tty; }

_ui_read_key() {
    local key rest
    IFS= read -rsn1 key </dev/tty
    if [[ $key == $'\e' ]]; then
        IFS= read -rsn2 -t 0.05 rest </dev/tty || true
        case $rest in
            '[A') key=up ;;
            '[B') key=down ;;
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
    local items=("$@") count=$# cursor=0 i key

    printf '%s     \033[35m?\033[0m %s \033[2m(↑/↓ e Enter)\033[0m\n' "$(_ui_tag)" "$title" >/dev/tty
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
            [1-9]) if ((key <= count)); then cursor=$((key - 1)); fi ;;
        esac
        printf '\033[%dA' "$count" >/dev/tty
    done
    _ui_cursor_show
    __ui_out=$cursor
}

ui_checklist() {
    local -n __ui_out=$1
    local title=$2 preset="" offset=0
    shift 2
    while [[ ${1:-} == --selected || ${1:-} == --all ]]; do
        if [[ $1 == --all ]]; then
            offset=1
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

    printf '%s     \033[35m?\033[0m %s \033[2m(↑/↓, Espaço marca, a = todos, Enter confirma)\033[0m\n' "$(_ui_tag)" "$title" >/dev/tty
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

if [[ ${ASTRO_PLAIN:-} == 1 ]]; then
    _ui_tag()  { printf '[%s]' "$ASTRO_PROJECT"; }
    ui_step()  { printf '%s ==> %s\n' "$(_ui_tag)" "$*"; }
    ui_info()  { printf '%s     %s\n' "$(_ui_tag)" "$*"; }
    ui_ok()    { printf '%s     ok: %s\n' "$(_ui_tag)" "$*"; }
    ui_warn()  { printf '%s     aviso: %s\n' "$(_ui_tag)" "$*"; }
    ui_error() { printf '%s     erro: %s\n' "$(_ui_tag)" "$*" >&2; }
fi
