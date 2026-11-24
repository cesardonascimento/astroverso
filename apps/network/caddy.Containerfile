ARG CADDY_VERSION
FROM docker.io/library/caddy:${CADDY_VERSION}-builder-alpine AS builder
ARG CLOUDFLARE_VERSION
RUN xcaddy build --with github.com/caddy-dns/cloudflare@${CLOUDFLARE_VERSION}

FROM docker.io/library/caddy:${CADDY_VERSION}-alpine
COPY --from=builder /usr/bin/caddy /usr/bin/caddy
