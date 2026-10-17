/**
 * Captura da prova de vida em RAJADA: durante cada passo a câmera grava quadros em
 * sequência (~10 por segundo, como um vídeo) e, no fim do passo, escolhemos os que
 * mostram o movimento. Quem confere é o servidor, sobre essas imagens salvas; o app só
 * guia a pessoa e decide QUANDO o passo acabou (o movimento visto ou o tempo esgotado).
 *
 * Os sinais (blink, smile, yaw) vêm do FaceLandmarker do app e servem só para escolher
 * os quadros; o servidor recalcula tudo a partir das imagens.
 */
import type { PassoBiometria } from "./types";

export interface Quadro {
  img: string;
  t: number;
  blink: number;
  smile: number;
  yaw: number;
}

/** Teto total do servidor (biometria_service._validar_quadros). */
export const MAX_QUADROS = 40;
/** Intervalo entre quadros da rajada (ms). */
export const CADENCIA_MS = 100;
/** Tempo máximo de cada passo; acabou o tempo, segue e o servidor decide. */
export const TEMPO_PASSO_MS: Record<PassoBiometria, number> = {
  piscar2: 6000,
  piscar3: 7000,
  sorrir: 5000,
  virar_esquerda: 5000,
  virar_direita: 5000,
};

// Mesmos limiares do servidor (backend/app/services/liveness_logic.py).
const BLINK_FECHADO = 0.45;
const BLINK_ABERTO = 0.3;
const YAW_FRONTAL = 0.08;
const YAW_GIRO = 0.22;

export function cotaPorPasso(passos: number): number {
  return Math.max(3, Math.floor(MAX_QUADROS / Math.max(1, passos)));
}

/** Os quadros do passo que mostram a ação, em ordem de tempo, no máximo `max`. */
export function selecionarQuadros(qs: Quadro[], passo: PassoBiometria, max: number): Quadro[] {
  if (qs.length <= max) return qs;
  const escolhidos = new Set<number>();
  const add = (i: number) => {
    if (i >= 0 && i < qs.length && escolhidos.size < max) escolhidos.add(i);
  };

  if (passo === "piscar2" || passo === "piscar3") {
    // Cada piscada: o último quadro aberto antes, o mais fechado e o primeiro aberto depois.
    let i = 0;
    while (i < qs.length) {
      if ((qs[i]?.blink ?? 0) <= BLINK_FECHADO) {
        i++;
        continue;
      }
      let fim = i;
      let pico = i;
      while (fim < qs.length && (qs[fim]?.blink ?? 0) > BLINK_FECHADO) {
        if ((qs[fim]?.blink ?? 0) > (qs[pico]?.blink ?? 0)) pico = fim;
        fim++;
      }
      let antes = i - 1;
      while (antes >= 0 && (qs[antes]?.blink ?? 0) >= BLINK_ABERTO) antes--;
      let depois = fim;
      while (depois < qs.length && (qs[depois]?.blink ?? 0) >= BLINK_ABERTO) depois++;
      if (escolhidos.size + 3 > max) break;
      add(antes);
      add(pico);
      add(depois);
      i = fim;
    }
  } else if (passo === "sorrir") {
    let alto = 0;
    qs.forEach((q, i) => {
      if (q.smile > (qs[alto]?.smile ?? 0)) alto = i;
    });
    let neutro = 0;
    for (let i = 0; i <= alto; i++) if ((qs[i]?.smile ?? 1) < (qs[neutro]?.smile ?? 1)) neutro = i;
    add(neutro);
    [...qs.keys()]
      .filter((i) => i > neutro)
      .sort((a, b) => (qs[b]?.smile ?? 0) - (qs[a]?.smile ?? 0))
      .slice(0, 3)
      .forEach(add);
  } else {
    const sinal = passo === "virar_esquerda" ? 1 : -1;
    const virados = [...qs.keys()]
      .filter((i) => sinal * (qs[i]?.yaw ?? 0) > YAW_GIRO)
      .sort((a, b) => sinal * ((qs[b]?.yaw ?? 0) - (qs[a]?.yaw ?? 0)));
    const primeiroVirado = virados.length ? Math.min(...virados) : qs.length;
    let frontal = -1;
    for (let i = 0; i < primeiroVirado; i++) {
      const y = Math.abs(qs[i]?.yaw ?? 1);
      if (y < YAW_FRONTAL) {
        // Prefere frame com expressão neutra (menor smile) para não contaminar
        // o step de virar com frames de sorriso acidental.
        const melhor =
          frontal < 0 ||
          y < Math.abs(qs[frontal]?.yaw ?? 1) - 0.01 ||
          (Math.abs(y - Math.abs(qs[frontal]?.yaw ?? 1)) < 0.01 &&
            (qs[i]?.smile ?? 0) < (qs[frontal]?.smile ?? 0));
        if (melhor) frontal = i;
      }
    }
    add(frontal);
    virados.slice(0, 4).forEach(add);
  }

  // Completa com quadros espalhados no tempo (o servidor confere a sequência inteira).
  const livres = max - escolhidos.size;
  for (let k = 0; k < livres; k++) add(Math.round(((k + 0.5) * qs.length) / livres));
  for (let i = 0; escolhidos.size < max && i < qs.length; i++) add(i);
  return [...escolhidos].sort((a, b) => a - b).map((i) => qs[i] as Quadro);
}
