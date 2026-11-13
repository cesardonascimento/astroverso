ARG N8N_VERSION=2.47.5
FROM docker.io/n8nio/runners:${N8N_VERSION}
ARG QRCODE_VERSION=1.5.4
USER root
RUN mkdir -p /opt/astro && cd /opt/astro \
    && printf '{"name":"astro-runners","private":true}\n' > package.json \
    && pnpm add --config.node-linker=hoisted "qrcode@${QRCODE_VERSION}" \
    && python3 -I -c 'import json; p = "/etc/n8n-task-runners.json"; c = json.load(open(p)); r = next(x for x in c["task-runners"] if x["runner-type"] == "javascript"); r["env-overrides"]["NODE_FUNCTION_ALLOW_EXTERNAL"] = "moment,qrcode"; json.dump(c, open(p, "w"), indent=2)'
ENV NODE_PATH=/opt/astro/node_modules
USER runner
