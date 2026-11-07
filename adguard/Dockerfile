ARG ADGUARD_VERSION=v0.107.80
FROM docker.io/adguard/adguardhome:${ADGUARD_VERSION}

RUN apk add --no-cache apache2-utils gettext-envsubst

ENV TZ=America/Sao_Paulo \
    ADGUARD_USERNAME=admin \
    ADGUARD_PASSWORD_HASH="" \
    ADGUARD_LANGUAGE=pt-br \
    ADGUARD_REWRITES="" \
    ADGUARD_REWRITE_ANSWER=""

COPY config/AdGuardHome.yaml.template /opt/adguardhome/
COPY --chmod=0755 scripts/docker-entrypoint.sh /usr/local/bin/

ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
CMD ["--no-check-update", "-c", "/opt/adguardhome/conf/AdGuardHome.yaml", "-w", "/opt/adguardhome/work"]
