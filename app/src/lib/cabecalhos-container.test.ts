import { expect, it } from "vitest";
import { cabecalhosContainer } from "../../scripts/cabecalhos-container.mjs";
const html = "<script>window.teste=1</script>";
it("container local mantém hashes, permite MediaPipe e evita origens irrestritas", () => {
  const h = cabecalhosContainer(html, {
    VITE_MODE: "development",
    VITE_API_URL: "http://localhost:8000",
  });
  expect(h).toContain("'sha256-");
  expect(h).toContain("'wasm-unsafe-eval'");
  expect(h).toContain("https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@1.0.1/");
  expect(h).not.toContain("script-src 'self' 'unsafe-inline'");
  expect(h).not.toContain("connect-src *");
  expect(h).not.toContain("upgrade-insecure-requests");
  expect(h).not.toContain("Strict-Transport-Security");
});
it("container de produção continua exigindo HTTPS", () => {
  expect(() =>
    cabecalhosContainer(html, { VITE_MODE: "production", VITE_API_URL: "http://localhost:8000" }),
  ).toThrow();
  const h = cabecalhosContainer(html, {
    VITE_MODE: "production",
    VITE_API_URL: "https://api.exemplo",
  });
  expect(h).toContain("Strict-Transport-Security");
});
it("development não libera API remota HTTP", () => {
  expect(() =>
    cabecalhosContainer(html, { VITE_MODE: "development", VITE_API_URL: "http://api.exemplo" }),
  ).toThrow();
});
