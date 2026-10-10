export const DESTINO: string;
export const RESERVAS: string[];
export function pino(cert: string | Buffer): string;
export function pinosReserva(): string[];
export function pinosDaCadeia(host: string, porta?: number): Promise<string[]>;
export function montarXml(o: { host: string; pinos: string[]; expira: string }): string;
