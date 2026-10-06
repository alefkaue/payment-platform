// Config do Vite sem a camada da Lovable (@lovable.dev/vite-tanstack-config).
// Fora do sandbox da Lovable, aquele pacote só montava estes plugins padrão;
// aqui eles ficam explícitos e o projeto não depende mais da plataforma.
// Sem Nitro: o app é SPA (web + apk). O build sai em dist/client (shell em
// dist/client/_shell.html). Para deploy com SSR, adicione `nitro()` de "nitro/vite".
import { defineConfig } from "vite";
import tailwindcss from "@tailwindcss/vite";
import tsConfigPaths from "vite-tsconfig-paths";
import { tanstackStart } from "@tanstack/react-start/plugin/vite";
import viteReact from "@vitejs/plugin-react";

export default defineConfig({
  server: { port: 8081 },
  resolve: { dedupe: ["react", "react-dom", "@tanstack/react-router", "@tanstack/react-query"] },
  plugins: [
    tailwindcss(),
    tsConfigPaths({ projects: ["./tsconfig.json"] }),
    tanstackStart({
      // Código de servidor nunca entra no bundle do cliente.
      importProtection: {
        behavior: "error",
        client: { files: ["**/server/**"], specifiers: ["server-only"] },
      },
      // Entry do servidor em src/server.ts (wrapper de erro do SSR).
      server: { entry: "server" },
      // SPA: gera o shell estático (dist/client/_shell.html) que o apk usa.
      spa: { enabled: true },
    }),
    viteReact(),
  ],
});
