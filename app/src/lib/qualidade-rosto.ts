/**
 * Qualidade da captura ANTES da prova de vida (fase de preparo). Mesmas regras do
 * servidor (backend/app/services/qualidade_rosto.py); quem decide é o servidor.
 *
 * Óculos: a ponte da armação é uma BARRA HORIZONTAL entre os olhos. Medimos a maior
 * faixa contínua de bordas horizontais (Sobel com |gy| dominante) nessa região, como
 * fração da largura (0..1). O nariz de lado, sombra e fundo geram bordas VERTICAIS e
 * não contam, por isso virar o rosto não vira "óculos". Só vale com o rosto de frente.
 */
export const OCULOS_LIMIAR = 0.6;
export const PREPARO_MS = 1000;
/** Rosto "de frente" para medir óculos (mesma escala do giro do app/servidor). */
export const YAW_OCULOS = 0.08;
const BORDA_MIN = 100; // |gy| do Sobel 3x3 (0..1020) ~ contraste de 25 tons
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

export function orientarRosto(m: MedidasRosto, cadastro: boolean): string | null {
  if (!m.rostos) return "Posicione o rosto no círculo";
  if (m.rostos > 1) return "Fique sozinho na câmera";
  if (m.altura < 0.4) return "Aproxime o rosto";
  if (m.altura > 0.85) return "Afaste um pouco";
  if (Math.abs(m.centroX - 0.5) > 0.12 || Math.abs(m.centroY - 0.5) > 0.15)
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

/** Giro do rosto: nariz em relação ao meio das bochechas (o servidor usa a mesma conta). */
export function giroDoRosto(pontos: PontoRosto[]): number {
  const nariz = pontos[1];
  const e = pontos[234];
  const d = pontos[454];
  if (!nariz || !e || !d) return 0;
  return (nariz.x - (e.x + d.x) / 2) / (Math.abs(d.x - e.x) || 1);
}

/** Mediana (para estabilizar medidas ruidosas quadro a quadro). */
export function mediana(v: number[]): number {
  if (!v.length) return 0;
  const s = [...v].sort((a, b) => a - b);
  const m = s.length >> 1;
  return s.length % 2 ? (s[m] ?? 0) : ((s[m - 1] ?? 0) + (s[m] ?? 0)) / 2;
}

/**
 * Maior faixa contínua de bordas horizontais na região [x0,x1)×[y0,y1), como fração da
 * largura. Cada coluna conta se alguma linha de uma janela de 3 tem borda horizontal.
 */
export function barraHorizontal(
  cinza: ArrayLike<number>,
  w: number,
  h: number,
  x0: number,
  y0: number,
  x1: number,
  y1: number,
): number {
  const a = Math.max(1, Math.floor(x0));
  const b = Math.min(w - 1, Math.ceil(x1));
  const c = Math.max(1, Math.floor(y0));
  const d = Math.min(h - 1, Math.ceil(y1));
  const largura = b - a;
  if (largura < 4 || d - c < 3) return 0;
  // Suaviza o ruído do sensor (pouca luz) sem apagar a armação: gaussiana 3x3, como o
  // servidor (cv2.GaussianBlur). Bordas da imagem replicam o pixel vizinho.
  const bruto = (x: number, y: number) =>
    cinza[Math.max(0, Math.min(h - 1, y)) * w + Math.max(0, Math.min(w - 1, x))] ?? 0;
  const p = (x: number, y: number) =>
    (bruto(x - 1, y - 1) + 2 * bruto(x, y - 1) + bruto(x + 1, y - 1) +
      2 * bruto(x - 1, y) + 4 * bruto(x, y) + 2 * bruto(x + 1, y) +
      bruto(x - 1, y + 1) + 2 * bruto(x, y + 1) + bruto(x + 1, y + 1)) / 16;
  const horiz: boolean[][] = [];
  for (let y = c; y < d; y++) {
    const linha: boolean[] = [];
    for (let x = a; x < b; x++) {
      const gx =
        p(x + 1, y - 1) + 2 * p(x + 1, y) + p(x + 1, y + 1) -
        p(x - 1, y - 1) - 2 * p(x - 1, y) - p(x - 1, y + 1);
      const gy =
        p(x - 1, y + 1) + 2 * p(x, y + 1) + p(x + 1, y + 1) -
        p(x - 1, y - 1) - 2 * p(x, y - 1) - p(x + 1, y - 1);
      linha.push(Math.abs(gy) >= BORDA_MIN && Math.abs(gy) > 2 * Math.abs(gx));
    }
    horiz.push(linha);
  }
  let melhor = 0;
  for (let r = 0; r < horiz.length; r++) {
    let corrida = 0;
    let falhas = 0;
    let maior = 0;
    for (let x = 0; x < largura; x++) {
      const tem = [r - 1, r, r + 1].some((k) => horiz[k]?.[x]);
      if (tem) {
        corrida += 1 + falhas;
        falhas = 0;
        maior = Math.max(maior, corrida);
      } else if (corrida && falhas < 1) {
        falhas += 1; // tolera 1 pixel falhado na armação
      } else {
        corrida = 0;
        falhas = 0;
      }
    }
    melhor = Math.max(melhor, maior / largura);
  }
  return melhor;
}

/** Região da ponte dos óculos, em pixels: entre os cantos internos dos olhos. */
export function regiaoPonte(pontos: PontoRosto[], w: number, h: number) {
  const e = pontos[133];
  const d = pontos[362];
  const ponte = pontos[168];
  if (!e || !d || !ponte) return null;
  const dist = Math.hypot((d.x - e.x) * w, (d.y - e.y) * h);
  if (dist < 8) return null;
  const cx = ponte.x * w;
  const cy = ponte.y * h;
  return { x0: cx - 0.25 * dist, x1: cx + 0.25 * dist, y0: cy - 0.2 * dist, y1: cy + 0.35 * dist };
}

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
  const r = regiaoPonte(pontos, w, h);
  const oculos = r ? barraHorizontal(cinza, w, h, r.x0, r.y0, r.x1, r.y1) : 0;
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
