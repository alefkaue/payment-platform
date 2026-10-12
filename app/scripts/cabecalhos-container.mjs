/** CSP do nginx com hashes do shell final, inclusive no ambiente local. */
import { readFileSync, writeFileSync } from "node:fs";
import { pathToFileURL } from "node:url";
import { cabecalhos, hashesInline, montarCsp, validarApiProducao } from "./cabecalhos.mjs";

export function cabecalhosContainer(html, env) {
  const api = env.VITE_API_URL;
  if (env.VITE_MODE === "development" && api) {
    const url = new URL(api);
    if (
      !["localhost", "127.0.0.1", "[::1]"].includes(url.hostname) ||
      !["http:", "https:"].includes(url.protocol) ||
      url.username ||
      url.password ||
      url.search ||
      url.hash
    )
      throw new Error("API local deve usar localhost sem credenciais.");
  } else {
    validarApiProducao(env);
  }
  const headers = cabecalhos(montarCsp({ hashes: hashesInline(html), apiUrl: api }));
  if (api?.startsWith("http:")) delete headers["Strict-Transport-Security"];
  return (
    Object.entries(headers)
      .map(([nome, valor]) => `add_header ${nome} "${valor.replaceAll('"', '\\"')}" always;`)
      .join("\n") + "\n"
  );
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  writeFileSync(
    "security-headers.conf",
    cabecalhosContainer(readFileSync("dist/client/_shell.html", "utf8"), process.env),
  );
}
