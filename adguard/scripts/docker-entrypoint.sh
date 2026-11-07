#!/bin/sh
set -eu

CONF_FILE=/opt/adguardhome/conf/AdGuardHome.yaml
TEMPLATE=/opt/adguardhome/AdGuardHome.yaml.template

log() { printf '[adguard]     %s %s\n' "$1" "$2" >&2; }

chmod 0700 /opt/adguardhome/conf /opt/adguardhome/work

if [ -f "$CONF_FILE" ]; then
    log "✔" "usando configuração existente"
else
    [ -n "$ADGUARD_PASSWORD_HASH" ] || { log "✘" "ADGUARD_PASSWORD_HASH não definida"; exit 1; }
    envsubst '${ADGUARD_USERNAME} ${ADGUARD_PASSWORD_HASH} ${ADGUARD_LANGUAGE} ${TZ}' \
        < "$TEMPLATE" > "$CONF_FILE"
    chmod 0600 "$CONF_FILE"
    log "✔" "configuração gerada (usuário: $ADGUARD_USERNAME, fuso: $TZ)"
fi

exec /opt/adguardhome/AdGuardHome "$@"
