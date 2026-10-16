/**
 * Contador de piscadas calibrado pelo olho aberto da própria pessoa.
 *
 * Antes os limiares do blendshape eyeBlink eram fixos (fechado > 0.5, aberto < 0.2).
 * Quem tem olhos mais fechados, usa óculos ou olha para baixo para o celular fica com o
 * olho ABERTO em 0.25-0.35: a piscada nunca "reabria" e o passo não andava. Agora a base
 * é o percentil baixo dos últimos quadros de frente, e os limiares são relativos a ela.
 *
 * Os limiares daqui são um pouco MAIS exigentes que os do servidor
 * (backend/app/services/liveness_logic.py:limiares_piscada): se o app deu o passo por
 * feito, o servidor também vê as piscadas.
 */

export const PISCADA_YAW_MAX = 0.18;
const JANELA = 60;
const PERCENTIL = 0.2;

export function limiaresPiscada(base: number): { fechado: number; aberto: number } {
  return {
    fechado: Math.min(0.8, Math.max(0.5, base + 0.3)),
    aberto: Math.max(0.2, base + 0.08),
  };
}

export class ContadorPiscadas {
  private historico: number[] = [];
  private fechado = false;
  piscadas = 0;

  /** Olho aberto de referência (percentil baixo da janela). */
  get base(): number {
    if (this.historico.length === 0) return 0;
    const ordenados = [...this.historico].sort((a, b) => a - b);
    return ordenados[Math.floor(PERCENTIL * (ordenados.length - 1))] ?? 0;
  }

  /** Olho fechando o suficiente para valer a pena gravar no ritmo da câmera. */
  fechando(blink: number): boolean {
    return blink > limiaresPiscada(this.base).aberto;
  }

  /** Alimenta um quadro (calibra sempre; conta só se `contar`). Devolve as piscadas. */
  observar(blink: number, yaw: number, contar = true): number {
    if (Math.abs(yaw) > PISCADA_YAW_MAX) return this.piscadas; // girar imita piscada
    const { fechado, aberto } = limiaresPiscada(this.base);
    // Quadros de olho fechado não puxam a base para cima.
    if (!this.fechado && blink < fechado) {
      this.historico.push(blink);
      if (this.historico.length > JANELA) this.historico.shift();
    }
    if (!contar) return this.piscadas;
    if (!this.fechado && blink > fechado) this.fechado = true;
    else if (this.fechado && blink < aberto) {
      this.fechado = false;
      this.piscadas += 1;
    }
    return this.piscadas;
  }

  /** Novo passo: zera a contagem e mantém a calibração. */
  recomecar(): void {
    this.fechado = false;
    this.piscadas = 0;
  }
}
