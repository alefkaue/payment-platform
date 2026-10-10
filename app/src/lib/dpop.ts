/**
 * Prova de posse da chave (DPoP, RFC 9449) — SEGURANCA.md item 2.
 *
 * Este aparelho tem um par de chaves ECDSA P-256 gerado pelo WebCrypto com
 * `extractable: false`: a chave privada NUNCA sai do navegador (nem o próprio
 * JavaScript consegue exportá-la). Ela fica no IndexedDB, que guarda o objeto
 * CryptoKey sem expor o conteúdo.
 *
 * Toda requisição ao backend leva o header `DPoP`: um JWT curto assinado com
 * essa chave, dizendo método, endereço, horário, um id de uso único e (com
 * sessão) o hash do access token. O servidor amarra os tokens à impressão da
 * chave no login; um token copiado para outra máquina não serve sem ela.
 *
 * No app nativo (Capacitor) o WebView tem o mesmo WebCrypto/IndexedDB; o passo
 * seguinte é guardar a chave no Keystore/Keychain (SEGURANCA.md item 10).
 */

const BANCO = "astro-chaves";
const LOJA = "chaves";
const ID = "dpop";

interface ParChaves {
  privateKey: CryptoKey;
  publicKey: CryptoKey;
}

let emMemoria: Promise<{ par: ParChaves; jwk: JsonWebKey }> | null = null;

const sutil = () => globalThis.crypto.subtle;

function abrirBanco(): Promise<IDBDatabase> | null {
  if (typeof indexedDB === "undefined") return null;
  return new Promise((ok, falha) => {
    const req = indexedDB.open(BANCO, 1);
    req.onupgradeneeded = () => req.result.createObjectStore(LOJA);
    req.onsuccess = () => ok(req.result);
    req.onerror = () => falha(req.error);
  });
}

async function lerPar(): Promise<ParChaves | null> {
  const abrir = abrirBanco();
  if (!abrir) return null;
  const db = await abrir;
  return new Promise((ok) => {
    const req = db.transaction(LOJA).objectStore(LOJA).get(ID);
    req.onsuccess = () => ok((req.result as ParChaves | undefined) ?? null);
    req.onerror = () => ok(null);
  });
}

async function gravarPar(par: ParChaves): Promise<void> {
  const abrir = abrirBanco();
  if (!abrir) return;
  const db = await abrir;
  await new Promise<void>((ok) => {
    const tx = db.transaction(LOJA, "readwrite");
    tx.objectStore(LOJA).put(par, ID);
    tx.oncomplete = () => ok();
    tx.onerror = () => ok(); // sem IndexedDB a chave vive só nesta aba
  });
}

async function carregar(): Promise<{ par: ParChaves; jwk: JsonWebKey }> {
  let par: ParChaves | null = null;
  try {
    par = await lerPar();
  } catch {
    par = null;
  }
  if (!par) {
    par = (await sutil().generateKey({ name: "ECDSA", namedCurve: "P-256" }, false, [
      "sign",
      "verify",
    ])) as ParChaves;
    try {
      await gravarPar(par);
    } catch {
      /* modo privado/sem IndexedDB: segue em memória */
    }
  }
  // Só os campos públicos (RFC 7638): é o que o servidor usa para a impressão da chave.
  const {
    kty = "EC",
    crv = "P-256",
    x = "",
    y = "",
  } = await sutil().exportKey("jwk", par.publicKey);
  return { par, jwk: { kty, crv, x, y } };
}

function chave() {
  emMemoria ??= carregar();
  return emMemoria;
}

const b64url = (bytes: ArrayBuffer | Uint8Array) => {
  const arr = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes);
  let s = "";
  for (const b of arr) s += String.fromCharCode(b);
  return btoa(s).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
};
const b64urlTexto = (txt: string) => b64url(new TextEncoder().encode(txt));

async function sha256(txt: string): Promise<string> {
  return b64url(await sutil().digest("SHA-256", new TextEncoder().encode(txt)));
}

/** Header `DPoP` para uma requisição. `url` sem query; `accessToken` quando há sessão. */
export async function criarProva(
  metodo: string,
  url: string,
  accessToken?: string,
): Promise<string> {
  const { par, jwk } = await chave();
  const cabecalho = { typ: "dpop+jwt", alg: "ES256", jwk };
  const corpo: Record<string, string | number> = {
    jti: crypto.randomUUID(),
    htm: metodo.toUpperCase(),
    htu: url.split("?")[0]!.split("#")[0]!,
    iat: Math.floor(Date.now() / 1000),
  };
  if (accessToken) corpo["ath"] = await sha256(accessToken);
  const entrada = `${b64urlTexto(JSON.stringify(cabecalho))}.${b64urlTexto(JSON.stringify(corpo))}`;
  // WebCrypto devolve a assinatura ECDSA já no formato r||s que o JWS ES256 usa.
  const assinatura = await sutil().sign(
    { name: "ECDSA", hash: "SHA-256" },
    par.privateKey,
    new TextEncoder().encode(entrada),
  );
  return `${entrada}.${b64url(assinatura)}`;
}
