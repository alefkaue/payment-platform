// Reutiliza os mesmos cabeçalhos/CSP calculados para Static Web Apps.
import { readFileSync, writeFileSync } from "node:fs";

const config = JSON.parse(readFileSync("www/staticwebapp.config.json", "utf8"));
const headers = Object.entries(config.globalHeaders).map(([name, value]) => {
  if (!/^[A-Za-z-]+$/.test(name) || /[\r\n]/.test(value)) throw new Error("Cabeçalho inválido");
  const escaped = value.replaceAll("\\", "\\\\").replaceAll('"', '\\"').replaceAll("$", "\\$");
  return `add_header ${name} "${escaped}" always;`;
}).join("\n");
writeFileSync("nginx-students.conf", `server {
  listen 8080;
  server_tokens off;
  root /usr/share/nginx/html;
  index index.html;
  ${headers}
  add_header Cache-Control "no-cache" always;
  client_max_body_size 1m;
  location ~ /\\. { deny all; }
  location = /staticwebapp.config.json { return 404; }
  location = /_headers { return 404; }
  location = /_redirects { return 404; }
  location /assets/ { try_files $uri =404; }
  location / { try_files $uri $uri/ /index.html; }
}
`);
