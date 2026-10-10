/** Certificate pinning do APK (scripts/pinos.mjs): pins das raízes reserva e o XML gerado. */
import { describe, expect, it } from "vitest";
import { montarXml, pinosReserva, RESERVAS } from "../../scripts/pinos.mjs";

// Pin público e bem conhecido da DigiCert Global Root G2 (raiz dos certificados do Azure).
const DIGICERT_G2 = "i7WTqTvh0OioIruIfFR4kMPnBqrS2rdiVPl/s2uC/CY=";

describe("pinos", () => {
  it("acha todas as raízes reserva no pacote de CAs e calcula o SPKI certo", () => {
    const pinos = pinosReserva();
    expect(pinos).toHaveLength(RESERVAS.length);
    expect(pinos).toContain(DIGICERT_G2);
  });

  it("fixa só o domínio da API, sem texto em claro e sem pins repetidos", () => {
    const xml = montarXml({
      host: "api.astro.test",
      pinos: ["a=", "b=", "a="],
      expira: "2027-04-01",
    });
    expect(xml).toContain('<domain includeSubdomains="false">api.astro.test</domain>');
    expect(xml).toContain('<pin-set expiration="2027-04-01">');
    expect(xml.match(/<pin digest/g)).toHaveLength(2);
    expect(xml).not.toContain('cleartextTrafficPermitted="true"');
  });
});
