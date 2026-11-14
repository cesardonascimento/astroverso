const fs = require('fs');
const path = require('path');

let leitor;
let mupdf;

async function carregar() {
  if (!leitor) {
    const zxing = require('zxing-wasm/reader');
    const wasm = fs.readFileSync(path.join(path.dirname(require.resolve('zxing-wasm/reader')), '..', '..', 'reader', 'zxing_reader.wasm'));
    await zxing.prepareZXingModule({ overrides: { wasmBinary: wasm }, fireImmediately: true });
    leitor = zxing;
  }
  if (!mupdf) mupdf = await import('mupdf');
}

async function decodificar(imagem) {
  const lidos = await leitor.readBarcodes(imagem, { formats: ['QRCode'], tryHarder: true, maxNumberOfSymbols: 10 });
  return lidos.filter((r) => r.isValid).map((r) => r.text);
}

async function lerQrCodes(dados, { tipo = 'pdf', senhas = [], paginas = 5, resolucoes = [150, 300] } = {}) {
  await carregar();
  const bytes = dados instanceof Uint8Array ? dados : new Uint8Array(dados);
  if (tipo !== 'pdf') return [...new Set(await decodificar(bytes))];
  const doc = mupdf.Document.openDocument(bytes, 'application/pdf');
  try {
    if (doc.needsPassword() && !['', ...senhas].some((s) => doc.authenticatePassword(s))) return [];
    const achados = new Set();
    const total = Math.min(doc.countPages(), paginas);
    for (let i = 0; i < total; i++) {
      const pagina = doc.loadPage(i);
      for (const dpi of resolucoes) {
        const escala = dpi / 72;
        const pixmap = pagina.toPixmap(mupdf.Matrix.scale(escala, escala), mupdf.ColorSpace.DeviceRGB, false, true);
        const png = pixmap.asPNG();
        pixmap.destroy();
        const textos = await decodificar(png);
        textos.forEach((t) => achados.add(t));
        if (textos.length) break;
      }
      pagina.destroy();
    }
    return [...achados];
  } finally {
    doc.destroy();
  }
}

module.exports = { lerQrCodes };
