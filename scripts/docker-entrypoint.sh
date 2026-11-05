#!/bin/sh
# Gera o AdGuardHome.yaml a partir do template na primeira execução
# (ou sempre, se ADGUARD_FORCE_CONFIG=true) e inicia o AdGuard Home.
set -eu

CONF_DIR=/opt/adguardhome/conf
CONF_FILE="$CONF_DIR/AdGuardHome.yaml"
TEMPLATE=/opt/adguardhome/templates/AdGuardHome.yaml.template

mkdir -p "$CONF_DIR" /opt/adguardhome/work
chmod 0700 "$CONF_DIR" /opt/adguardhome/work

if [ ! -f "$CONF_FILE" ] || [ "${ADGUARD_FORCE_CONFIG:-false}" = "true" ]; then
    if [ -z "${ADGUARD_PASSWORD:-}" ]; then
        echo "[astro-adguard] ERRO: defina ADGUARD_PASSWORD no arquivo .env" >&2
        exit 1
    fi

    echo "[astro-adguard] Gerando $CONF_FILE a partir do template..."
    ADGUARD_PASSWORD_HASH="$(htpasswd -nbBC 10 "" "$ADGUARD_PASSWORD" | tr -d ':\n')"
    export ADGUARD_PASSWORD_HASH TZ ADGUARD_USERNAME ADGUARD_LANGUAGE

    [ -f "$CONF_FILE" ] && cp "$CONF_FILE" "$CONF_FILE.bak"
    envsubst '${ADGUARD_USERNAME} ${ADGUARD_PASSWORD_HASH} ${ADGUARD_LANGUAGE} ${TZ}' \
        < "$TEMPLATE" > "$CONF_FILE"
    chmod 0600 "$CONF_FILE"
else
    echo "[astro-adguard] Config existente encontrada, mantendo (ADGUARD_FORCE_CONFIG=true para regerar)."
fi

exec /opt/adguardhome/AdGuardHome "$@"
