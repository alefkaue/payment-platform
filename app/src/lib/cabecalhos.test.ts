/** CSP do front (scripts/cabecalhos.mjs): hashes dos scripts inline e origens liberadas. */
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import {
  cabecalhos,
  hashesInline,
  MEDIAPIPE_MODELOS,
  MEDIAPIPE_WASM,
  montarCsp,
} from "../../scripts/cabecalhos.mjs";

const sha = (s: string) => `'sha256-${createHash("sha256").update(s).digest("base64")}'`;

describe("CSP do front", () => {
  it("hash de cada script inline, nenhum para script com src", () => {
    const html =
      '<script>a()</script><script data-x="1">b()</script>' +
      '<script type="module" src="/assets/i.js"></script><script>a()</script>';
    expect(hashesInline(html)).toEqual([sha("a()"), sha("b()")]);
  });

  it("hash como o navegador: NUL vira U+FFFD e CRLF vira LF", () => {
    expect(hashesInline("<script>a\u0000b\r\nc</script>")).toEqual([sha("a\uFFFDb\nc")]);
  });

  it("script só do próprio site + hashes + MediaPipe; nada de unsafe-inline/eval em script", () => {
    const csp = montarCsp({ hashes: ["'sha256-x'"], apiUrl: "https://api.astro.com/v1" });
    const script = csp.split("; ").find((d) => d.startsWith("script-src")) ?? "";
    expect(script).not.toContain("'unsafe-inline'");
    expect(script).not.toContain("'unsafe-eval'");
    expect(script).toContain("'sha256-x'");
    expect(csp).toContain("connect-src 'self' https://api.astro.com ");
    expect(csp).toContain("frame-ancestors 'none'");
    expect(csp).toContain("upgrade-insecure-requests");
  });

  it("API em http (desenvolvimento) não força https", () => {
    expect(montarCsp({ hashes: [], apiUrl: "http://localhost:8000" })).not.toContain(
      "upgrade-insecure-requests",
    );
  });

  it("as URLs do MediaPipe em liveness.tsx estão liberadas na CSP", () => {
    const fonte = readFileSync("src/components/payflow/liveness.tsx", "utf8");
    const wasm = /const WASM = "([^"]+)"/.exec(fonte)?.[1] ?? "";
    const modelo = /const MODELO =\s*"([^"]+)"/.exec(fonte)?.[1] ?? "";
    expect(wasm.startsWith(MEDIAPIPE_WASM)).toBe(true);
    expect(modelo.startsWith(MEDIAPIPE_MODELOS)).toBe(true);
  });

  it("câmera só para o próprio site e página não pode ser embutida", () => {
    const h = cabecalhos("default-src 'self'");
    expect(h["Permissions-Policy"]).toContain("camera=(self)");
    expect(h["X-Frame-Options"]).toBe("DENY");
  });
});
