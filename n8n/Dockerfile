ARG N8N_VERSION=2.47.5
FROM docker.io/n8nio/runners:${N8N_VERSION}
ARG QRCODE_VERSION=1.5.4
ARG PNGJS_VERSION=5.0.0
ARG MUPDF_VERSION=1.28.6
ARG ZXING_WASM_VERSION=3.1.6
USER root
RUN mkdir -p /opt/astroverso && cd /opt/astroverso \
    && printf '{"name":"astroverso-runners","private":true}\n' > package.json \
    && pnpm add --config.node-linker=hoisted "qrcode@${QRCODE_VERSION}" "pngjs@${PNGJS_VERSION}" "mupdf@${MUPDF_VERSION}" "zxing-wasm@${ZXING_WASM_VERSION}" \
    && python3 -I -c 'import json; p = "/etc/n8n-task-runners.json"; c = json.load(open(p)); r = next(x for x in c["task-runners"] if x["runner-type"] == "javascript"); r["env-overrides"]["NODE_FUNCTION_ALLOW_EXTERNAL"] = "moment,qrcode,pngjs,astroverso-qr"; json.dump(c, open(p, "w"), indent=2)'
COPY astroverso-qr /opt/astroverso/node_modules/astroverso-qr
ENV NODE_PATH=/opt/astroverso/node_modules
USER runner
