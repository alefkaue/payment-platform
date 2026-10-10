// Monta a pasta `www` (raiz web do apk) a partir do build SPA do Vite.
// O TanStack Start em modo SPA gera `dist/client/_shell.html`; o Capacitor
// precisa de um `index.html` na raiz, então copiamos tudo e renomeamos o shell.
import { cpSync, rmSync, renameSync, existsSync, readFileSync, writeFileSync } from "node:fs";

// dist/client = build sem Nitro (atual); .output/public = build com Nitro (antigo).
const PUB = existsSync("dist/client/_shell.html") ? "dist/client" : ".output/public";
const WWW = "www";

if (!existsSync(`${PUB}/_shell.html`)) {
  console.error(`✗ ${PUB}/_shell.html não encontrado. Rode "npm run build" antes.`);
  process.exit(1);
}

rmSync(WWW, { recursive: true, force: true });
cpSync(PUB, WWW, { recursive: true });
renameSync(`${WWW}/_shell.html`, `${WWW}/index.html`);

// Cabeçalhos do host (scripts/cabecalhos.mjs) apontam o SPA para o shell: aqui ele é o index.html.
for (const arq of ["_redirects", "staticwebapp.config.json"]) {
  const p = `${WWW}/${arq}`;
  if (existsSync(p))
    writeFileSync(p, readFileSync(p, "utf8").replaceAll("/_shell.html", "/index.html"));
}

console.log(`✓ www/ pronto (SPA estático) — pronto para "npx cap sync android".`);
