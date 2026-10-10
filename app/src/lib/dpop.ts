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
 * No APK (Capacitor) a chave fica no Android Keystore, em hardware (StrongBox ou
 * TEE), pelo plugin nativo `ChaveAparelho` (android/.../ChaveAparelhoPlugin.java):
 * o JavaScript só pede assinaturas. O Keystore também entrega a cadeia de
 * atestação, que vai no login para o servidor conferir que a chave está mesmo em
 * hardware, no nosso app, num aparelho íntegro (SEGURANCA.md item 10).
 */

import { Capacitor, registerPlugin } from "@capacitor/core";

interface ChaveAparelhoPlugin {
  chavePublica(): Promise<{ jwk: JsonWebKey; atestacao: string[] }>;
  assinar(opcoes: { dados: string }): Promise<{ assinatura: string }>;
}

const ChaveAparelho = registerPlugin<ChaveAparelhoPlugin>("ChaveAparelho");

const BANCO = "astro-chaves";
const LOJA = "chaves";
const ID = "dpop";

interface ParChaves {
  privateKey: CryptoKey;
  publicKey: CryptoKey;
}

interface Chave {
  jwk: JsonWebKey;
  /** Assina o texto e devolve r||s em base64url (formato do JWS ES256). */
  assinar(entrada: string): Promise<string>;
  /** Cadeia de atestação do Keystore (só no APK). */
  atestacao?: string[] | undefined;
}

let emMemoria: Promise<Chave> | null = null;

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

const nativa = () => Capacitor.isNativePlatform() && Capacitor.isPluginAvailable("ChaveAparelho");

async function carregarNativa(): Promise<Chave> {
  const { jwk, atestacao } = await ChaveAparelho.chavePublica();
  return {
    jwk,
    atestacao: atestacao.length ? atestacao : undefined,
    assinar: async (dados) => (await ChaveAparelho.assinar({ dados })).assinatura,
  };
}

async function carregar(): Promise<Chave> {
  if (nativa()) return carregarNativa();
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
  const privada = par.privateKey;
  return {
    jwk: { kty, crv, x, y },
    // WebCrypto devolve a assinatura ECDSA já no formato r||s que o JWS ES256 usa.
    assinar: async (entrada) =>
      b64url(
        await sutil().sign(
          { name: "ECDSA", hash: "SHA-256" },
          privada,
          new TextEncoder().encode(entrada),
        ),
      ),
  };
}

function chave() {
  emMemoria ??= carregar().catch((e: unknown) => {
    emMemoria = null; // tenta de novo na próxima requisição
    throw e;
  });
  return emMemoria;
}

/** Cadeia de atestação da chave (APK Android) para o login; no navegador, nada. */
export async function atestacaoDoAparelho(): Promise<string[] | undefined> {
  return (await chave()).atestacao;
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
  const { jwk, assinar } = await chave();
  const cabecalho = { typ: "dpop+jwt", alg: "ES256", jwk };
  const corpo: Record<string, string | number> = {
    jti: crypto.randomUUID(),
    htm: metodo.toUpperCase(),
    htu: url.split("?")[0]!.split("#")[0]!,
    iat: Math.floor(Date.now() / 1000),
  };
  if (accessToken) corpo["ath"] = await sha256(accessToken);
  const entrada = `${b64urlTexto(JSON.stringify(cabecalho))}.${b64urlTexto(JSON.stringify(corpo))}`;
  return `${entrada}.${await assinar(entrada)}`;
}
