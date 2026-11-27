ARG CADDY_VERSION=2.11.9
ARG CLOUDFLARE_MODULE_VERSION=v0.2.4

FROM docker.io/library/caddy:${CADDY_VERSION}-builder-alpine AS builder
ARG CLOUDFLARE_MODULE_VERSION
RUN xcaddy build --with github.com/caddy-dns/cloudflare@${CLOUDFLARE_MODULE_VERSION}

FROM docker.io/library/caddy:${CADDY_VERSION}-alpine
COPY --from=builder /usr/bin/caddy /usr/bin/caddy
