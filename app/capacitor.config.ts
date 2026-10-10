import type { CapacitorConfig } from "@capacitor/cli";

/**
 * Astro — empacotamento mobile (Capacitor).
 * O MESMO app web (Vite/TanStack em modo SPA) vira o .apk: o build gera
 * `.output/public` (shell estático + assets) e `scripts/assemble-www.mjs`
 * monta a pasta `www` que o Capacitor embute no app Android.
 */
const config: CapacitorConfig = {
  appId: "com.payflow.app",
  appName: "Astro",
  webDir: "www",
  backgroundColor: "#0A0A0A",
  plugins: {
    Keyboard: { resizeOnFullScreen: true },
  },
  android: {
    // Nem o APK de debug abre o WebView no chrome://inspect: quem controla o JavaScript
    // do app pede assinaturas à chave do Keystore (SEGURANCA.md item 10).
    webContentsDebuggingEnabled: false,
  },
};

export default config;
