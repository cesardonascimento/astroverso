const MAX_SIZE = 24 * 1024 * 1024;

function allowed(sender, list) {
  const domain = sender.toLowerCase().split("@").pop();
  return list.split(",").map((item) => item.trim().toLowerCase().replace(/^@/, "")).filter(Boolean).includes(domain);
}

function cloudflareResults(raw) {
  const end = raw.search(/\r?\n\r?\n/);
  const head = (end < 0 ? raw : raw.slice(0, end)).replace(/\r?\n[ \t]+/g, " ");
  const line = head.split(/\r?\n/).find((item) => /^authentication-results:/i.test(item)) || "";
  const value = line.replace(/^authentication-results:\s*/i, "");
  return value.toLowerCase().startsWith("mx.cloudflare.net") ? value : "";
}

function resposta(status, dados) {
  return new Response(JSON.stringify(dados), { status, headers: { "content-type": "application/json" } });
}

async function enviar(request, env) {
  if (request.method !== "POST" || new URL(request.url).pathname !== "/enviar") return resposta(404, { erro: "não encontrado" });
  if (!env.CHAVE_ENVIO || request.headers.get("x-astroverso-chave") !== env.CHAVE_ENVIO) return resposta(401, { erro: "chave inválida" });
  let pedido;
  try {
    pedido = await request.json();
  } catch (erro) {
    return resposta(400, { erro: "JSON inválido" });
  }
  const para = (Array.isArray(pedido.para) ? pedido.para : []).map((item) => String(item).trim()).filter(Boolean);
  if (!para.length || !pedido.assunto) return resposta(400, { erro: "faltam destinatários ou assunto" });
  const anexos = (pedido.anexos || []).map((anexo) => ({
    content: Uint8Array.from(atob(String(anexo.base64 || "")), (letra) => letra.charCodeAt(0)),
    filename: anexo.nome,
    type: anexo.tipo,
    disposition: anexo.cid ? "inline" : "attachment",
    ...(anexo.cid ? { contentId: anexo.cid } : {}),
  }));
  const enviados = [];
  const erros = [];
  for (const destino of para) {
    try {
      await env.ENVIO.send({
        to: destino,
        from: env.REMETENTE,
        subject: String(pedido.assunto),
        text: String(pedido.texto || ""),
        html: String(pedido.html || ""),
        attachments: anexos,
      });
      enviados.push(destino);
    } catch (erro) {
      erros.push({ para: destino, erro: String((erro && erro.message) || erro) });
    }
  }
  return resposta(erros.length && !enviados.length ? 502 : 200, { enviados, erros });
}

export default {
  async fetch(request, env) {
    return enviar(request, env);
  },

  async email(message, env) {
    if (message.rawSize > MAX_SIZE) {
      message.setReject("message too large");
      return;
    }
    const bytes = new Uint8Array(await new Response(message.raw).arrayBuffer());
    const head = new TextDecoder().decode(bytes.slice(0, 65536));
    const results = cloudflareResults(head);
    const authenticated = /\b(spf|dmarc)=pass\b/i.test(results);
    const sender = allowed(message.from, env.ALLOWED_DOMAINS || "");
    const trusted = authenticated && sender;
    const reason = trusted ? "ok" : !sender ? `domínio fora da lista: ${message.from}` : "sem spf=pass nem dmarc=pass";
    const mark = new TextEncoder().encode(`X-Astroverso-Mailserver: ${trusted ? "inbox" : "quarentena"}; ${reason}\r\n`);
    const body = new Uint8Array(mark.length + bytes.length);
    body.set(mark);
    body.set(bytes, mark.length);
    const key = `${trusted ? "inbox" : "quarentena"}.${Date.now()}.${crypto.randomUUID()}`;
    await env.MAIL.put(key, body);
    await env.MAIL.put("campainha", String(Date.now()));
  },
};
