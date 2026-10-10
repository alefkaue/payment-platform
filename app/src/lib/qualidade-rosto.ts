export const OCULOS_LIMIAR = 2.2;
export const PREPARO_MS = 1000;
export type PontoRosto = { x: number; y: number };
export interface MedidasRosto {
  rostos: number;
  altura: number;
  centroX: number;
  centroY: number;
  brilho: number;
  estourado: number;
  contraluz: number;
  oculos: number;
}

export function orientarRosto(m: MedidasRosto, cadastro: boolean, preparo = true): string | null {
  if (!m.rostos) return "Posicione o rosto no círculo";
  if (m.rostos > 1) return "Fique sozinho na câmera";
  if (preparo && m.altura < 0.4) return "Aproxime o rosto";
  if (preparo && m.altura > 0.85) return "Afaste um pouco";
  if (preparo && (Math.abs(m.centroX - 0.5) > 0.12 || Math.abs(m.centroY - 0.5) > 0.15))
    return "Centralize o rosto no círculo";
  if (m.brilho < 55) return "Está escuro: vá para um lugar com mais luz, de frente para a luz.";
  if (m.estourado > 0.25)
    return "Luz forte demais no rosto: saia do sol direto ou afaste a lâmpada.";
  if (m.contraluz > 85)
    return "Há muita luz atrás de você: fique de costas para a janela ou para a lâmpada.";
  if (cadastro && m.oculos >= OCULOS_LIMIAR) return "Tire os óculos para a verificação do rosto.";
  return null;
}

export function recusaQualidade(mensagem: string): boolean {
  return /está escuro|luz forte demais|muita luz atrás|tire os óculos|mais de um rosto|rosto mudou/i.test(
    mensagem,
  );
}

/** Mesmas regiões do servidor; Sobel substitui Canny no guia local. */
export function medirRosto(
  data: Uint8ClampedArray,
  w: number,
  h: number,
  pontos: PontoRosto[],
  rostos: number,
): MedidasRosto {
  const xs = pontos.map((p) => p.x);
  const ys = pontos.map((p) => p.y);
  const x0 = Math.max(0, Math.floor(Math.min(...xs) * w));
  const x1 = Math.min(w, Math.ceil(Math.max(...xs) * w));
  const y0 = Math.max(0, Math.floor(Math.min(...ys) * h));
  const y1 = Math.min(h, Math.ceil(Math.max(...ys) * h));
  const cinza = new Float32Array(w * h);
  let soma = 0,
    n = 0,
    brancos = 0,
    fundo = 0,
    nf = 0;
  for (let y = 0; y < h; y++)
    for (let x = 0; x < w; x++) {
      const i = y * w + x;
      const v =
        0.299 * (data[i * 4] ?? 0) +
        0.587 * (data[i * 4 + 1] ?? 0) +
        0.114 * (data[i * 4 + 2] ?? 0);
      cinza[i] = v;
      if (x >= x0 && x < x1 && y >= y0 && y < y1) {
        soma += v;
        n++;
        if (v >= 245) brancos++;
      } else {
        fundo += v;
        nf++;
      }
    }
  const densidade = (cx: number, cy: number, meia: number, altura: number) => {
    let bordas = 0,
      total = 0;
    const a = Math.max(0, Math.floor(cx - meia)),
      b = Math.min(w, Math.floor(cx + meia));
    const c = Math.max(0, Math.floor(cy - altura)),
      d = Math.min(h, Math.floor(cy + altura));
    const pixel = (x: number, y: number) =>
      cinza[Math.max(c, Math.min(d - 1, y)) * w + Math.max(a, Math.min(b - 1, x))] ?? 0;
    for (let y = c; y < d; y++)
      for (let x = a; x < b; x++) {
        const gx =
          pixel(x + 1, y - 1) +
          2 * pixel(x + 1, y) +
          pixel(x + 1, y + 1) -
          pixel(x - 1, y - 1) -
          2 * pixel(x - 1, y) -
          pixel(x - 1, y + 1);
        const gy =
          pixel(x - 1, y + 1) +
          2 * pixel(x, y + 1) +
          pixel(x + 1, y + 1) -
          pixel(x - 1, y - 1) -
          2 * pixel(x, y - 1) -
          pixel(x + 1, y - 1);
        if (Math.hypot(gx, gy) >= 140) bordas++;
        total++;
      }
    return total >= 16 ? bordas / total : 0;
  };
  const e = pontos[133],
    d = pontos[362],
    ponte = pontos[168],
    testa = pontos[10];
  let oculos = 0;
  if (e && d && ponte && testa) {
    const meia = Math.max(Math.abs(d.x - e.x) * w * 0.35, 4);
    const altura = Math.max(Math.abs(d.x - e.x) * w * 0.25, 4);
    oculos =
      densidade(ponte.x * w, ponte.y * h, meia, altura) /
      Math.max(densidade(testa.x * w, testa.y * h + altura, meia, altura), 0.01);
  }
  const brilho = n ? soma / n : 0;
  return {
    rostos,
    altura: (y1 - y0) / h,
    centroX: (x0 + x1) / (2 * w),
    centroY: (y0 + y1) / (2 * h),
    brilho,
    estourado: n ? brancos / n : 0,
    contraluz: nf ? fundo / nf - brilho : 0,
    oculos,
  };
}
