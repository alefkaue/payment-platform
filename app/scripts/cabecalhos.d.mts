export const MEDIAPIPE_WASM: string;
export function ambienteBuild(diretorio?: string): Record<string, string>;
export function validarApiProducao(env: Record<string, string | undefined>): void;
export const MEDIAPIPE_MODELOS: string;
export function hashesInline(html: string): string[];
export function montarCsp(o: {
  hashes: string[];
  apiUrl?: string | undefined;
  syncUrl?: string | undefined;
}): string;
export function cabecalhos(csp: string): Record<string, string>;
