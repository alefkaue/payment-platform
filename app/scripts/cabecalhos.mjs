// Cabeçalhos de segurança do front (CSP e companhia) para o host estático.
//
// Roda depois do `vite build` (ver "build" no package.json) e grava, em dist/client:
//   - staticwebapp.config.json → Azure Static Web Apps (alvo do pentest, SEGURANCA.md item 9)
//   - _headers                  → Netlify (deploy da apresentação)
//
// A CSP não usa 'unsafe-inline' em script: o shell do TanStack Start tem 3 scripts
// inline (restaurar rolagem, estado do roteador, autoremoção). O script calcula o
// SHA-256 de cada um no _shell.html gerado e põe na política — se o shell mudar, o
// hash muda junto. Estilo inline continua liberado (bibliotecas de UI injetam <style>);
// injeção de CSS é bem menos grave que de script.
//
// Origens externas: só as que o app usa de fato.
//   - MediaPipe (prova de vida): WASM no jsDelivr e o modelo no Google Storage
//     (constantes WASM e MODELO em src/components/payflow/liveness.tsx);
//   - Google Fonts (src/routes/__root.tsx);
//   - a API (VITE_API_URL) e, se houver, o sincronizador do modo demonstração.

import { createHash } from "node:crypto";
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { pathToFileURL } from "node:url";

export const MEDIAPIPE_WASM = "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@1.0.1/";
export const MEDIAPIPE_MODELOS = "https://storage.googleapis.com/mediapipe-models/";

/** SHA-256 (base64) do conteúdo de cada <script> inline do HTML, no formato da CSP. */
export function hashesInline(html) {
  const hashes = [];
  for (const m of html.matchAll(/<script(?![^>]*\bsrc=)[^>]*>([\s\S]*?)<\/script>/g)) {
    // O hash é do texto que o navegador vê depois do parser HTML: quebras de linha
    // viram LF e o caractere NUL vira U+FFFD (o estado do roteador tem um NUL).
    const corpo = (m[1] ?? "").replace(/\r\n?/g, "\n").replace(/\0/g, "\uFFFD");
    if (!corpo) continue;
    hashes.push(`'sha256-${createHash("sha256").update(corpo, "utf8").digest("base64")}'`);
  }
  return [...new Set(hashes)];
}

const origem = (url) => (url ? new URL(url).origin : null);

/** Monta a Content-Security-Policy do app. */
export function montarCsp({ hashes, apiUrl, syncUrl }) {
  const api = origem(apiUrl);
  const sync = origem(syncUrl);
  const https = !api || api.startsWith("https:");
  const diretivas = [
    "default-src 'self'",
    // 'wasm-unsafe-eval' só libera compilar WebAssembly (MediaPipe), não eval de JS.
    `script-src 'self' ${hashes.join(" ")} ${MEDIAPIPE_WASM} 'wasm-unsafe-eval'`,
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
    "font-src 'self' https://fonts.gstatic.com",
    // Fotos do documento e quadros da câmera viram data:/blob: antes de ir para a API.
    "img-src 'self' data: blob:",
    "media-src 'self' blob:",
    ["connect-src 'self'", api, sync, MEDIAPIPE_WASM, MEDIAPIPE_MODELOS].filter(Boolean).join(" "),
    "worker-src 'self' blob:",
    "manifest-src 'self'",
    "object-src 'none'",
    "base-uri 'none'",
    "form-action 'self'",
    "frame-ancestors 'none'",
  ];
  if (https) diretivas.push("upgrade-insecure-requests");
  return diretivas.join("; ");
}

/** Cabeçalhos que valem para todas as respostas do front. */
export function cabecalhos(csp) {
  return {
    "Content-Security-Policy": csp,
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(self), microphone=(), geolocation=(), payment=(), usb=()",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
  };
}

function main() {
  const PUB = "dist/client";
  const shell = `${PUB}/_shell.html`;
  if (!existsSync(shell)) {
    console.error(`✗ ${shell} não encontrado. Rode "vite build" antes.`);
    process.exit(1);
  }
  const html = readFileSync(shell, "utf8");
  const hashes = hashesInline(html);
  const apiUrl = process.env.VITE_API_URL || lerEnv("VITE_API_URL");
  const syncUrl = process.env.VITE_DEMO_SYNC_URL || lerEnv("VITE_DEMO_SYNC_URL");
  const h = cabecalhos(montarCsp({ hashes, apiUrl, syncUrl }));

  // Azure Static Web Apps: SPA → toda rota cai no shell; assets com hash no nome
  // ficam em cache longo; o shell nunca (senão a CSP com hash fica velha).
  const swa = {
    navigationFallback: {
      rewrite: "/_shell.html",
      exclude: ["/assets/*", "/welcome/*", "/*.{png,ico,svg,txt,json}"],
    },
    globalHeaders: h,
    routes: [
      { route: "/assets/*", headers: { "Cache-Control": "public, max-age=31536000, immutable" } },
      { route: "/_shell.html", headers: { "Cache-Control": "no-cache" } },
    ],
    mimeTypes: { ".wasm": "application/wasm" },
  };
  writeFileSync(`${PUB}/staticwebapp.config.json`, JSON.stringify(swa, null, 2) + "\n");

  // Netlify: mesmo conteúdo no formato _headers (+ _redirects para o SPA).
  const linhas = Object.entries(h).map(([k, v]) => `  ${k}: ${v}`);
  writeFileSync(
    `${PUB}/_headers`,
    [
      "/*",
      ...linhas,
      "",
      "/assets/*",
      "  Cache-Control: public, max-age=31536000, immutable",
      "",
    ].join("\n"),
  );
  if (!existsSync(`${PUB}/_redirects`))
    writeFileSync(`${PUB}/_redirects`, "/*  /_shell.html  200\n");

  console.log(`✓ cabeçalhos de segurança gerados (${hashes.length} script(s) inline com hash).`);
}

/** Lê uma variável dos .env do Vite (modo production), como o próprio build faz. */
function lerEnv(nome) {
  for (const arq of [".env.production.local", ".env.local", ".env.production", ".env"]) {
    if (!existsSync(arq)) continue;
    const m = readFileSync(arq, "utf8").match(new RegExp(`^\\s*${nome}\\s*=\\s*(.*)$`, "m"));
    const v = m?.[1]?.trim().replace(/^["']|["']$/g, "");
    if (v) return v;
  }
  return undefined;
}

if (import.meta.url === pathToFileURL(process.argv[1] ?? "").href) main();
