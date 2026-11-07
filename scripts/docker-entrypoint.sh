#!/bin/sh
set -eu

CONF_FILE=/opt/adguardhome/conf/AdGuardHome.yaml
TEMPLATE=/opt/adguardhome/AdGuardHome.yaml.template

log() {
    printf '%s [%s] astro-adguard: %s\n' "$(date '+%Y/%m/%d %H:%M:%S')" "$1" "$2" >&2
}

chmod 0700 /opt/adguardhome/conf /opt/adguardhome/work

if [ -f "$CONF_FILE" ] && [ "$ADGUARD_FORCE_CONFIG" != "true" ]; then
    log info "usando configuração existente em $CONF_FILE"
else
    if [ -z "$ADGUARD_PASSWORD" ]; then
        log error "ADGUARD_PASSWORD não definida no .env"
        exit 1
    fi

    if [ -f "$CONF_FILE" ]; then
        cp "$CONF_FILE" "$CONF_FILE.bak"
        log info "backup da configuração anterior salvo em $CONF_FILE.bak"
    fi

    ADGUARD_PASSWORD_HASH="$(htpasswd -nbBC 10 "" "$ADGUARD_PASSWORD" | tr -d ':\n')" \
        envsubst '${ADGUARD_USERNAME} ${ADGUARD_PASSWORD_HASH} ${ADGUARD_LANGUAGE} ${TZ}' \
        < "$TEMPLATE" > "$CONF_FILE"
    chmod 0600 "$CONF_FILE"
    log info "configuração gerada a partir do template (usuário: $ADGUARD_USERNAME, fuso: $TZ)"
fi

exec /opt/adguardhome/AdGuardHome "$@"
