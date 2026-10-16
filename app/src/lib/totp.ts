/**
 * TOTP (RFC 6238), igual ao backend (backend/app/core/totp.py): HMAC-SHA1, 6 dígitos,
 * passo de 30 s e janela de ±1 passo. Usado só no modo demonstração, para a simulação
 * offline conferir o código do app autenticador do mesmo jeito que o servidor.
 */
export const PASSO_SEG = 30;
export const DIGITOS = 6;
const JANELA = 1;
const ALFABETO = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";

function base32(bytes: Uint8Array): string {
  let bits = 0;
  let valor = 0;
  let saida = "";
  for (const b of bytes) {
    valor = (valor << 8) | b;
    bits += 8;
    while (bits >= 5) {
      saida += ALFABETO[(valor >>> (bits - 5)) & 31];
      bits -= 5;
    }
  }
  if (bits > 0) saida += ALFABETO[(valor << (5 - bits)) & 31];
  return saida;
}

function deBase32(txt: string): Uint8Array {
  const limpo = txt.replace(/[\s=]/g, "").toUpperCase();
  const saida: number[] = [];
  let bits = 0;
  let valor = 0;
  for (const ch of limpo) {
    const i = ALFABETO.indexOf(ch);
    if (i < 0) throw new Error("Segredo TOTP inválido.");
    valor = (valor << 5) | i;
    bits += 5;
    if (bits >= 8) {
      saida.push((valor >>> (bits - 8)) & 255);
      bits -= 8;
    }
  }
  return new Uint8Array(saida);
}

/** Segredo base32 novo (160 bits), como o backend gera. */
export function gerarSegredo(): string {
  return base32(crypto.getRandomValues(new Uint8Array(20)));
}

/** URI otpauth:// (vira QR Code no app autenticador). */
export function uriOtpauth(segredo: string, conta: string, emissor = "ASTRO"): string {
  const rotulo = encodeURIComponent(`${emissor}:${conta}`);
  return (
    `otpauth://totp/${rotulo}?secret=${segredo}&issuer=${encodeURIComponent(emissor)}` +
    `&algorithm=SHA1&digits=${DIGITOS}&period=${PASSO_SEG}`
  );
}

export const passoAtual = (agoraMs = Date.now()) => Math.floor(agoraMs / 1000 / PASSO_SEG);

/** Código do passo (contador) informado. `chave` são os bytes do segredo. */
export async function codigoDoPasso(chave: Uint8Array, passo: number, digitos = DIGITOS) {
  const contador = new DataView(new ArrayBuffer(8));
  contador.setUint32(0, Math.floor(passo / 2 ** 32));
  contador.setUint32(4, passo >>> 0);
  const k = await crypto.subtle.importKey(
    "raw",
    chave as BufferSource,
    { name: "HMAC", hash: "SHA-1" },
    false,
    ["sign"],
  );
  const mac = new Uint8Array(await crypto.subtle.sign("HMAC", k, contador.buffer));
  const o = mac[mac.length - 1]! & 0x0f;
  const bin = ((mac[o]! & 0x7f) << 24) | (mac[o + 1]! << 16) | (mac[o + 2]! << 8) | mac[o + 3]!;
  return String(bin % 10 ** digitos).padStart(digitos, "0");
}

export async function codigoTotp(segredo: string, agoraMs = Date.now()): Promise<string> {
  return codigoDoPasso(deBase32(segredo), passoAtual(agoraMs));
}

/**
 * Confere o código e devolve o passo que ele representa (para o anti-replay), ou
 * `null` se não bater com nenhum passo da janela.
 */
export async function passoDoCodigo(
  segredo: string,
  codigo: string,
  agoraMs = Date.now(),
): Promise<number | null> {
  if (!/^\d{6}$/.test(codigo)) return null;
  const chave = deBase32(segredo);
  const atual = passoAtual(agoraMs);
  for (let d = -JANELA; d <= JANELA; d++)
    if ((await codigoDoPasso(chave, atual + d)) === codigo) return atual + d;
  return null;
}
