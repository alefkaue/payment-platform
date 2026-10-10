// Certificate pinning do APK (SEGURANCA.md item 10).
//
// Gera android/app/src/main/res/xml/network_security_config.xml com um <pin-set>
// para o domínio da API (VITE_API_URL). Roda no CI antes do Gradle (android.yml).
//
// O que é fixado: as CAs (intermediária e raiz) da cadeia que a API apresenta AGORA,
// mais raízes reserva das autoridades que emitem os certificados do Azure. A folha
// não é fixada: o Azure troca o certificado sozinho, e um pin nela quebraria o app
// na próxima renovação. Com o pin, para este domínio só valem essas autoridades: um
// certificado emitido por qualquer outra CA (mesmo confiável no Android) é recusado.
//
// Os pins expiram (PINOS_DIAS, padrão 180): depois disso o Android volta a aceitar
// qualquer CA do sistema, em vez de deixar um APK velho sem conexão.

import { createHash, X509Certificate } from "node:crypto";
import { writeFileSync } from "node:fs";
import { connect, rootCertificates } from "node:tls";
import { pathToFileURL } from "node:url";

export const DESTINO = "android/app/src/main/res/xml/network_security_config.xml";

// Raízes reserva (pelo nome, do pacote de CAs do Node, sem colar hash à mão).
export const RESERVAS = [
  "DigiCert Global Root G2",
  "DigiCert Global Root G3",
  "Microsoft RSA Root Certificate Authority 2017",
  "Microsoft ECC Root Certificate Authority 2017",
];

/** pin-sha256 (base64 do SHA-256 do SPKI) de um certificado DER ou PEM. */
export function pino(cert) {
  const spki = new X509Certificate(cert).publicKey.export({ type: "spki", format: "der" });
  return createHash("sha256").update(spki).digest("base64");
}

export function pinosReserva() {
  const out = [];
  for (const pem of rootCertificates) {
    const cn = /CN=([^\n]+)/.exec(new X509Certificate(pem).subject)?.[1];
    if (cn && RESERVAS.includes(cn.trim())) out.push(pino(pem));
  }
  return out;
}

/** CAs (sem a folha) da cadeia que o servidor apresenta. */
export function pinosDaCadeia(host, porta = 443) {
  return new Promise((ok, falha) => {
    const s = connect({ host, port: porta, servername: host, timeout: 15000 }, () => {
      const pinos = [];
      let c = s.getPeerCertificate(true);
      const vistos = new Set();
      let primeiro = true;
      while (c && c.raw && !vistos.has(c.fingerprint256)) {
        vistos.add(c.fingerprint256);
        if (!primeiro) pinos.push(pino(c.raw));
        primeiro = false;
        c = c.issuerCertificate;
      }
      s.end();
      if (!pinos.length) falha(new Error(`${host} não apresentou a cadeia de CAs.`));
      else ok(pinos);
    });
    s.on("timeout", () => s.destroy(new Error(`tempo esgotado conectando em ${host}`)));
    s.on("error", falha);
  });
}

export function montarXml({ host, pinos, expira }) {
  const pins = [...new Set(pinos)]
    .map((p) => `            <pin digest="SHA-256">${p}</pin>`)
    .join("\n");
  return `<?xml version="1.0" encoding="utf-8"?>
<!-- GERADO por app/scripts/pinos.mjs no build do APK. Não edite: edite o script. -->
<network-security-config>
    <base-config cleartextTrafficPermitted="false">
        <trust-anchors>
            <certificates src="system" />
        </trust-anchors>
    </base-config>
    <domain-config cleartextTrafficPermitted="false">
        <domain includeSubdomains="false">${host}</domain>
        <pin-set expiration="${expira}">
${pins}
        </pin-set>
    </domain-config>
</network-security-config>
`;
}

async function main() {
  const api = process.env.VITE_API_URL;
  if (!api) {
    console.log("• sem VITE_API_URL: APK sem pinning (modo demonstração), fica o arquivo base.");
    return;
  }
  const { hostname: host, port } = new URL(api);
  const daCadeia = await pinosDaCadeia(host, Number(port) || 443);
  const reservas = pinosReserva();
  const dias = Number(process.env.PINOS_DIAS || 180);
  const expira = new Date(Date.now() + dias * 864e5).toISOString().slice(0, 10);
  writeFileSync(DESTINO, montarXml({ host, pinos: [...daCadeia, ...reservas], expira }));
  console.log(
    `✓ pinning de ${host}: ${daCadeia.length} CA(s) da cadeia + ${reservas.length} reserva(s), até ${expira}.`,
  );
}

if (import.meta.url === pathToFileURL(process.argv[1] ?? "").href)
  main().catch((e) => {
    // Com API configurada e sem conseguir ler a cadeia, o build falha: melhor que
    // publicar um APK sem pinning achando que tem.
    console.error(`✗ pinning: ${e.message}`);
    process.exit(1);
  });
