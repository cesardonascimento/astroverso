# =============================================================================
#  astro-adguard — imagem customizada do AdGuard Home
# =============================================================================
#  Customizações em relação à imagem oficial:
#   - Versão fixada (reprodutível em qualquer máquina)
#   - Timezone America/Sao_Paulo por padrão
#   - Config pré-pronta: pula o assistente de instalação (porta 3000)
#   - Usuário/senha do painel vindos de variáveis de ambiente (hash bcrypt)
#   - Upstreams DoH (Cloudflare, Quad9, Google) em modo paralelo
#   - Cache otimista e maior, DNSSEC, listas de bloqueio extras
#   - Healthcheck (web + DNS)
# =============================================================================

ARG ADGUARD_VERSION=v0.107.80
FROM docker.io/adguard/adguardhome:${ADGUARD_VERSION}

ARG ADGUARD_VERSION
LABEL org.opencontainers.image.title="astro-adguard" \
      org.opencontainers.image.description="AdGuard Home customizado (config pré-pronta, DoH, listas extras)" \
      org.opencontainers.image.base.name="docker.io/adguard/adguardhome:${ADGUARD_VERSION}"

# apache2-utils -> htpasswd (gera hash bcrypt da senha)
# gettext-envsubst -> envsubst (renderiza o template de config)
RUN apk add --no-cache apache2-utils gettext-envsubst tzdata

ENV TZ=America/Sao_Paulo \
    ADGUARD_USERNAME=admin \
    ADGUARD_PASSWORD="" \
    ADGUARD_LANGUAGE=pt-br \
    ADGUARD_FORCE_CONFIG=false

COPY config/AdGuardHome.yaml.template /opt/adguardhome/templates/AdGuardHome.yaml.template
COPY scripts/docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod 0755 /usr/local/bin/docker-entrypoint.sh

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD wget -q --spider http://127.0.0.1:80/login.html \
   && nslookup -timeout=3 adguard.com 127.0.0.1 >/dev/null || exit 1

ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
CMD ["--no-check-update", "-c", "/opt/adguardhome/conf/AdGuardHome.yaml", "-w", "/opt/adguardhome/work"]
