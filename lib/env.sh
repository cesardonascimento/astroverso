env_get() {
    local value
    value="$(grep -m1 "^$1=" .env 2>/dev/null | cut -d= -f2- | tr -d "'")" || true
    printf '%s' "${value:-${2:-}}"
}
