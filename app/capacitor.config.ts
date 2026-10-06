import type { CapacitorConfig } from "@capacitor/cli";

/**
 * PayFlow — empacotamento mobile (Capacitor).
 * O MESMO app web (Vite/TanStack em modo SPA) vira o .apk: o build gera
 * `.output/public` (shell estático + assets) e `scripts/assemble-www.mjs`
 * monta a pasta `www` que o Capacitor embute no app Android.
 */
const config: CapacitorConfig = {
  appId: "com.payflow.app",
  appName: "PayFlow",
  webDir: "www",
  backgroundColor: "#141414",
};

export default config;
