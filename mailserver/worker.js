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

export default {
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
    const mark = new TextEncoder().encode(`X-Astro-Mailserver: ${trusted ? "inbox" : "quarentena"}; ${reason}\r\n`);
    const body = new Uint8Array(mark.length + bytes.length);
    body.set(mark);
    body.set(bytes, mark.length);
    const key = `${trusted ? "inbox" : "quarentena"}.${Date.now()}.${crypto.randomUUID()}`;
    await env.MAIL.put(key, body);
  },
};
