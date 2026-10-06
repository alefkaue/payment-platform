// Monta a pasta `www` (raiz web do apk) a partir do build SPA do Vite.
// O TanStack Start em modo SPA gera `.output/public/_shell.html`; o Capacitor
// precisa de um `index.html` na raiz, então copiamos tudo e renomeamos o shell.
import { cpSync, rmSync, renameSync, existsSync } from "node:fs";

const PUB = ".output/public";
const WWW = "www";

if (!existsSync(`${PUB}/_shell.html`)) {
  console.error(`✗ ${PUB}/_shell.html não encontrado. Rode "npm run build" antes.`);
  process.exit(1);
}

rmSync(WWW, { recursive: true, force: true });
cpSync(PUB, WWW, { recursive: true });
renameSync(`${WWW}/_shell.html`, `${WWW}/index.html`);

console.log(`✓ www/ pronto (SPA estático) — pronto para "npx cap sync android".`);
