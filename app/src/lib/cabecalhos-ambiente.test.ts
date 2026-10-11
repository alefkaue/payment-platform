import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { ambienteBuild } from "../../scripts/cabecalhos.mjs";

let pasta: string;
beforeEach(() => {
  pasta = mkdtempSync(join(tmpdir(), "astro-csp-"));
  vi.stubEnv("VITE_API_URL", undefined);
});
afterEach(() => {
  rmSync(pasta, { recursive: true, force: true });
  vi.unstubAllEnvs();
});
it("produção prevalece sobre .env.local", () => {
  writeFileSync(join(pasta, ".env.local"), "VITE_API_URL=https://local.teste\n");
  writeFileSync(join(pasta, ".env.production"), "VITE_API_URL=https://producao.teste\n");
  expect(ambienteBuild(pasta)["VITE_API_URL"]).toBe("https://producao.teste");
});
it("produção local prevalece e expande variáveis com comentários", () => {
  writeFileSync(join(pasta, ".env.production"), "VITE_API_URL=https://producao.teste\n");
  writeFileSync(
    join(pasta, ".env.production.local"),
    'ORIGEM=https://final.teste\nVITE_API_URL="${ORIGEM}/v1" # comentário\n',
  );
  expect(ambienteBuild(pasta)["VITE_API_URL"]).toBe("https://final.teste/v1");
});
it.each(["", "https://processo.teste"])("processo prevalece mesmo vazio: %s", (valor) => {
  writeFileSync(join(pasta, ".env.production"), "VITE_API_URL=https://producao.teste\n");
  vi.stubEnv("VITE_API_URL", valor);
  expect(ambienteBuild(pasta)["VITE_API_URL"]).toBe(valor);
});
