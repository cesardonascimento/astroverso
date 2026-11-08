#!/bin/sh
set -eu

CONF_FILE=/opt/adguardhome/conf/AdGuardHome.yaml
TEMPLATE=/opt/adguardhome/AdGuardHome.yaml.template

log() { printf '[adguard]     %s %s\n' "$1" "$2" >&2; }

chmod 0700 /opt/adguardhome/conf /opt/adguardhome/work

if [ -f "$CONF_FILE" ]; then
    sed -i \
        -e "s|^  address: .*|  address: 0.0.0.0:$WEB_PORT|" \
        -e "/^  bind_hosts:/{n;s|^    - .*|    - $DNS_BIND_IP|}" \
        "$CONF_FILE"
    log "✔" "usando configuração existente (painel na porta $WEB_PORT, DNS em $DNS_BIND_IP)"
else
    [ -n "$ADGUARD_PASSWORD_HASH" ] || { log "✘" "ADGUARD_PASSWORD_HASH não definida"; exit 1; }

    ADGUARD_REWRITES_YAML=""
    for domain in $(printf '%s' "$ADGUARD_REWRITES" | tr ',' ' '); do
        ADGUARD_REWRITES_YAML="$ADGUARD_REWRITES_YAML{domain: '*.$domain', answer: '$ADGUARD_REWRITE_ANSWER', enabled: true}, "
        log "✔" "reescrita *.$domain → $ADGUARD_REWRITE_ANSWER"
    done
    ADGUARD_REWRITES_YAML="[${ADGUARD_REWRITES_YAML%, }]"
    export ADGUARD_REWRITES_YAML

    envsubst '${ADGUARD_USERNAME} ${ADGUARD_PASSWORD_HASH} ${ADGUARD_LANGUAGE} ${TZ} ${ADGUARD_REWRITES_YAML} ${WEB_PORT} ${DNS_BIND_IP}' \
        < "$TEMPLATE" > "$CONF_FILE"
    chmod 0600 "$CONF_FILE"
    log "✔" "configuração gerada (usuário: $ADGUARD_USERNAME, fuso: $TZ, painel na porta $WEB_PORT)"
fi

exec /opt/adguardhome/AdGuardHome "$@"
