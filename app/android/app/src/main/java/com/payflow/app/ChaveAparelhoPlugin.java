package com.payflow.app;

import android.os.Build;
import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyProperties;
import android.util.Base64;

import com.getcapacitor.JSArray;
import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;

import java.math.BigInteger;
import java.nio.charset.StandardCharsets;
import java.security.KeyPairGenerator;
import java.security.KeyStore;
import java.security.PrivateKey;
import java.security.ProviderException;
import java.security.Signature;
import java.security.cert.Certificate;
import java.security.interfaces.ECPublicKey;
import java.security.spec.ECGenParameterSpec;
import java.util.Arrays;

/**
 * Chave DPoP do aparelho no Android Keystore (SEGURANCA.md item 10).
 *
 * A chave ECDSA P-256 nasce dentro do hardware seguro (StrongBox quando existe,
 * senão o TEE) e nunca sai de lá: nem o app consegue ler a chave privada, só
 * pedir assinaturas. Junto vem a cadeia de ATESTAÇÃO, assinada pelo hardware e
 * pela Google, que o servidor confere no login (backend/app/core/atestacao.py).
 *
 * O WebView chama pelo src/lib/dpop.ts; no navegador/PWA continua o WebCrypto.
 */
@CapacitorPlugin(name = "ChaveAparelho")
public class ChaveAparelhoPlugin extends Plugin {

    private static final String ALIAS = "astro-dpop";
    // Tem que bater com DESAFIO em backend/app/core/atestacao.py.
    private static final byte[] DESAFIO = "astro-dpop-v1".getBytes(StandardCharsets.US_ASCII);

    /** Chave pública (JWK) e cadeia de atestação; cria a chave na 1ª vez. */
    @PluginMethod
    public void chavePublica(PluginCall call) {
        try {
            KeyStore ks = keystore();
            if (!ks.containsAlias(ALIAS)) gerar();
            ECPublicKey pub = (ECPublicKey) ks.getCertificate(ALIAS).getPublicKey();

            JSObject jwk = new JSObject();
            jwk.put("kty", "EC");
            jwk.put("crv", "P-256");
            jwk.put("x", b64url(fixo32(pub.getW().getAffineX())));
            jwk.put("y", b64url(fixo32(pub.getW().getAffineY())));

            // Sem atestação o Keystore devolve só um certificado autoassinado:
            // aí não mandamos nada (o servidor trata como aparelho sem atestação).
            JSArray cadeia = new JSArray();
            Certificate[] certs = ks.getCertificateChain(ALIAS);
            if (certs != null && certs.length > 1) {
                for (Certificate c : certs) cadeia.put(Base64.encodeToString(c.getEncoded(), Base64.NO_WRAP));
            }

            JSObject ret = new JSObject();
            ret.put("jwk", jwk);
            ret.put("atestacao", cadeia);
            call.resolve(ret);
        } catch (Exception e) {
            call.reject("Chave do aparelho indisponível: " + e.getMessage(), e);
        }
    }

    /** Assina `dados` (texto UTF-8) com ES256; devolve r||s em base64url, como o JWS pede. */
    @PluginMethod
    public void assinar(PluginCall call) {
        String dados = call.getString("dados");
        if (dados == null) {
            call.reject("Faltou o texto a assinar.");
            return;
        }
        try {
            KeyStore ks = keystore();
            if (!ks.containsAlias(ALIAS)) gerar();
            PrivateKey chave = (PrivateKey) ks.getKey(ALIAS, null);
            Signature s = Signature.getInstance("SHA256withECDSA");
            s.initSign(chave);
            s.update(dados.getBytes(StandardCharsets.UTF_8));
            JSObject ret = new JSObject();
            ret.put("assinatura", b64url(derParaRs(s.sign())));
            call.resolve(ret);
        } catch (Exception e) {
            call.reject("Não foi possível assinar com a chave do aparelho: " + e.getMessage(), e);
        }
    }

    private static KeyStore keystore() throws Exception {
        KeyStore ks = KeyStore.getInstance("AndroidKeyStore");
        ks.load(null);
        return ks;
    }

    private static void gerar() throws Exception {
        if (Build.VERSION.SDK_INT >= 28) {
            try {
                gerar(true, true);
                return;
            } catch (ProviderException semStrongBox) {
                // StrongBoxUnavailableException: o aparelho não tem chip dedicado; vai pro TEE.
            }
        }
        try {
            gerar(false, true);
        } catch (ProviderException semAtestacao) {
            // Aparelho antigo que não atesta: a chave continua no Keystore, só sem a cadeia.
            gerar(false, false);
        }
    }

    private static void gerar(boolean strongBox, boolean atestar) throws Exception {
        KeyGenParameterSpec.Builder b = new KeyGenParameterSpec.Builder(ALIAS, KeyProperties.PURPOSE_SIGN)
                .setAlgorithmParameterSpec(new ECGenParameterSpec("secp256r1"))
                .setDigests(KeyProperties.DIGEST_SHA256);
        if (atestar) b.setAttestationChallenge(DESAFIO);
        if (strongBox) b.setIsStrongBoxBacked(true);
        KeyPairGenerator g = KeyPairGenerator.getInstance(KeyProperties.KEY_ALGORITHM_EC, "AndroidKeyStore");
        g.initialize(b.build());
        g.generateKeyPair();
    }

    /** Coordenada da curva em exatamente 32 bytes (sem o 0 de sinal, com zeros à esquerda). */
    private static byte[] fixo32(BigInteger n) {
        byte[] b = n.toByteArray();
        if (b.length == 32) return b;
        byte[] out = new byte[32];
        if (b.length > 32) System.arraycopy(b, b.length - 32, out, 0, 32);
        else System.arraycopy(b, 0, out, 32 - b.length, b.length);
        return out;
    }

    /** Assinatura ECDSA em DER (SEQUENCE { INTEGER r, INTEGER s }) para r||s de 64 bytes. */
    static byte[] derParaRs(byte[] der) {
        int i = 2; // 0x30 + tamanho (P-256 cabe na forma curta)
        if ((der[1] & 0x80) != 0) i += der[1] & 0x7F;
        int lenR = der[i + 1];
        byte[] r = Arrays.copyOfRange(der, i + 2, i + 2 + lenR);
        i += 2 + lenR;
        int lenS = der[i + 1];
        byte[] s = Arrays.copyOfRange(der, i + 2, i + 2 + lenS);
        byte[] out = new byte[64];
        System.arraycopy(fixo32(new BigInteger(1, r)), 0, out, 0, 32);
        System.arraycopy(fixo32(new BigInteger(1, s)), 0, out, 32, 32);
        return out;
    }

    private static String b64url(byte[] b) {
        return Base64.encodeToString(b, Base64.URL_SAFE | Base64.NO_WRAP | Base64.NO_PADDING);
    }
}
