provider_describe() {
    echo "Proton Drive"
}

provider_default_name() {
    echo proton
}

provider_options() {
    printf '%s\n' --transfers 2 --checkers 4
}

provider_configure() {
    local name=$1 email password code obscured log
    email="$(rclone_get "$name" username)"
    ui_input email "e-mail da conta Proton" "$email" is_email
    while true; do
        ui_secret password "senha da conta Proton"
        code="$(_ui_ask "código da verificação em duas etapas (Enter se a conta não usa): ")"
        obscured="$(printf '%s' "$password" | rclone obscure -)"
        rclone_section_write "$name" \
            "type = protondrive" \
            "username = $email" \
            "password = $obscured" \
            "replace_existing_draft = true"
        if log="$(RCLONE_PROTONDRIVE_2FA="$code" rclone_run lsjson --max-depth 1 "$name:" 2>&1 >/dev/null)"; then
            ui_ok "conectado ao Proton Drive como $email"
            return 0
        fi
        printf '%s\n' "$log" | tail -3 | ui_prefix >&2
        ui_warn "o Proton recusou o login: confira a senha e o código e tente de novo"
    done
}
