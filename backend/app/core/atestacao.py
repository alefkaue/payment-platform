"""
Atestação da chave do aparelho no Android (SEGURANCA.md item 10).

No APK, a chave DPoP é gerada no Android Keystore (TEE ou StrongBox) com um
"desafio de atestação". O Keystore devolve uma cadeia de certificados: a folha
tem a chave pública e uma extensão (KeyDescription) que o próprio hardware
assina, e a cadeia sobe até uma raiz da Google. Com ela o servidor sabe:

- que a chave privada está em hardware de verdade e não sai dele;
- que a chave é a mesma do DPoP desta sessão (então quem assina as requisições
  é aquele hardware);
- que foi o NOSSO app (pacote e, em produção, o certificado de assinatura) que
  pediu a chave;
- que o aparelho subiu com boot verificado e bootloader travado (sem root
  "de fábrica" e sem ROM modificada).

É o mesmo tipo de garantia que o Play Integrity dá sobre o aparelho, mas sem
depender do app estar na Play Store nem de chamada à Google em cada login.
Atestações de chaves vazadas (o jeito comum de "falsificar" um aparelho
íntegro) estão na lista de revogação da Google, que conferimos.

Formato da extensão: https://source.android.com/docs/security/features/keystore/attestation
"""

from __future__ import annotations

import base64
import hashlib
import logging
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa

from app.core import dpop
from app.core.config import get_settings

logger = logging.getLogger("payflow.atestacao")

OID_KEY_DESCRIPTION = x509.ObjectIdentifier("1.3.6.1.4.1.11129.2.1.17")
# O app pede a chave com este desafio (android/.../ChaveAparelho.java). A frescura
# não vem dele: vem da prova DPoP, que só quem tem a chave privada consegue assinar.
DESAFIO = b"astro-dpop-v1"
MAX_CERTIFICADOS = 8

NIVEL_TEE, NIVEL_STRONGBOX = 1, 2
BOOT_VERIFICADO = 0


class AtestacaoInvalida(ValueError):
    """Cadeia forjada, de outro app ou de outra chave: recusar o login."""


@dataclass(frozen=True)
class Resultado:
    # "strongbox" | "tee" | None (atestação válida, mas sem garantia de hardware/boot)
    nivel: str | None
    motivo: str | None = None


# ---------------------------------------------------------------- raízes


def _spki(chave) -> bytes:
    return chave.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)


def _carregar_raizes() -> frozenset[bytes]:
    pem = (Path(__file__).with_name("raizes_atestacao.pem")).read_bytes()
    return frozenset(hashlib.sha256(_spki(c.public_key())).digest() for c in x509.load_pem_x509_certificates(pem))


_RAIZES = _carregar_raizes()


def raizes_confiaveis() -> frozenset[bytes]:
    """SHA-256 do SPKI das raízes aceitas (os testes trocam por uma raiz própria)."""
    return _RAIZES


# ---------------------------------------------------------------- revogação


_revogados: set[str] = set()
_revogados_em = 0.0
_revogados_lock = threading.Lock()


def _baixar_revogados() -> set[str]:
    import httpx

    r = httpx.get(get_settings().atestacao_status_url, timeout=10.0)
    r.raise_for_status()
    return {k.lower() for k in r.json().get("entries", {})}


def series_revogadas() -> set[str]:
    """Números de série (hex) revogados pela Google, com cache de 24 h. Se o download
    falhar, segue com a última lista boa (e registra no log)."""
    global _revogados, _revogados_em
    if not get_settings().atestacao_status_url:
        return set()
    with _revogados_lock:
        if time.monotonic() - _revogados_em > 24 * 3600 or not _revogados_em:
            try:
                _revogados = _baixar_revogados()
                _revogados_em = time.monotonic()
            except Exception as e:  # noqa: BLE001
                logger.warning("Lista de revogação da atestação indisponível: %s", e)
                _revogados_em = time.monotonic() - 23 * 3600  # tenta de novo em ~1 h
        return _revogados


# ---------------------------------------------------------------- DER mínimo


def _tlv(buf: bytes, i: int) -> tuple[int, int, int, int]:
    """Lê um TLV DER em buf[i:]. Devolve (classe, número da tag, início do valor, fim do valor)."""
    b = buf[i]
    classe, tag = b >> 6, b & 0x1F
    i += 1
    if tag == 0x1F:  # tag longa (ex.: [704] rootOfTrust)
        tag = 0
        while True:
            b = buf[i]
            i += 1
            tag = (tag << 7) | (b & 0x7F)
            if not b & 0x80:
                break
    n = buf[i]
    i += 1
    if n & 0x80:
        qtd = n & 0x7F
        if not 1 <= qtd <= 4:
            raise AtestacaoInvalida("DER: tamanho inválido.")
        n = int.from_bytes(buf[i:i + qtd], "big")
        i += qtd
    if i + n > len(buf):
        raise AtestacaoInvalida("DER truncado.")
    return classe, tag, i, i + n


def _filhos(buf: bytes, ini: int, fim: int) -> list[tuple[int, int, bytes]]:
    """Elementos de um SEQUENCE/SET: lista de (classe, tag, valor)."""
    out, i = [], ini
    while i < fim:
        classe, tag, a, b = _tlv(buf, i)
        out.append((classe, tag, buf[a:b]))
        i = b
    return out


def _seq(valor: bytes) -> list[tuple[int, int, bytes]]:
    _, _, a, b = _tlv(valor, 0)
    return _filhos(valor, a, b)


def _int(valor: bytes) -> int:
    return int.from_bytes(valor, "big", signed=True)


# ---------------------------------------------------------------- KeyDescription


@dataclass
class _Descricao:
    nivel_atestacao: int
    nivel_keymint: int
    desafio: bytes
    lista_sw: dict[int, bytes]
    lista_hw: dict[int, bytes]


def _lista_autorizacoes(valor: bytes) -> dict[int, bytes]:
    """AuthorizationList: SEQUENCE de [tag] EXPLICIT. Devolve tag -> conteúdo interno (DER)."""
    return {tag: interno for classe, tag, interno in _filhos(valor, 0, len(valor)) if classe == 2}


def _descricao(folha: x509.Certificate) -> _Descricao:
    try:
        ext = folha.extensions.get_extension_for_oid(OID_KEY_DESCRIPTION).value.value
    except x509.ExtensionNotFound:
        raise AtestacaoInvalida("Certificado sem a extensão de atestação.") from None
    campos = _seq(ext)
    if len(campos) < 8:
        raise AtestacaoInvalida("Extensão de atestação incompleta.")
    return _Descricao(
        nivel_atestacao=_int(campos[1][2]),
        nivel_keymint=_int(campos[3][2]),
        desafio=campos[4][2],
        lista_sw=_lista_autorizacoes(campos[6][2]),
        lista_hw=_lista_autorizacoes(campos[7][2]),
    )


def _raiz_de_confianca(d: _Descricao) -> tuple[bool, int] | None:
    """[704] RootOfTrust (só vale o da lista do hardware): (deviceLocked, verifiedBootState)."""
    interno = d.lista_hw.get(704)
    if interno is None:
        return None
    campos = _seq(interno)
    return campos[1][2] != b"\x00", _int(campos[2][2])


def _aplicativo(d: _Descricao) -> tuple[set[str], set[str]]:
    """[709] AttestationApplicationId: (pacotes, SHA-256 hex dos certificados de assinatura)."""
    interno = d.lista_sw.get(709) or d.lista_hw.get(709)
    if interno is None:
        raise AtestacaoInvalida("Atestação sem a identificação do app.")
    _, _, a, b = _tlv(interno, 0)  # OCTET STRING com o DER do AttestationApplicationId
    campos = _seq(interno[a:b])
    pacotes = set()
    for _, _, info in _filhos(campos[0][2], 0, len(campos[0][2])):
        pacote = _filhos(info, 0, len(info))[0][2]
        pacotes.add(pacote.decode("utf-8", "replace"))
    assinaturas = {v.hex() for _, _, v in _filhos(campos[1][2], 0, len(campos[1][2]))}
    return pacotes, assinaturas


# ---------------------------------------------------------------- cadeia


def _assinado_por(cert: x509.Certificate, emissor: x509.Certificate) -> None:
    chave = emissor.public_key()
    try:
        if isinstance(chave, rsa.RSAPublicKey):
            chave.verify(cert.signature, cert.tbs_certificate_bytes, padding.PKCS1v15(), cert.signature_hash_algorithm)
        elif isinstance(chave, ec.EllipticCurvePublicKey):
            chave.verify(cert.signature, cert.tbs_certificate_bytes, ec.ECDSA(cert.signature_hash_algorithm))
        else:
            raise AtestacaoInvalida("Tipo de chave não suportado na cadeia.")
    except InvalidSignature:
        raise AtestacaoInvalida("Cadeia de atestação com assinatura inválida.") from None


def _cadeia(certificados_b64: list[str]) -> list[x509.Certificate]:
    if not certificados_b64 or len(certificados_b64) > MAX_CERTIFICADOS:
        raise AtestacaoInvalida("Cadeia de atestação vazia ou longa demais.")
    try:
        cadeia = [x509.load_der_x509_certificate(base64.b64decode(c, validate=True)) for c in certificados_b64]
    except ValueError:
        raise AtestacaoInvalida("Certificado de atestação malformado.") from None
    # Relógio real (validade de certificado não segue o relógio simulado da app).
    agora = datetime.now(timezone.utc)
    for i, cert in enumerate(cadeia):
        # A folha do Keystore costuma ter validade "infinita" ou herdada; só os
        # intermediários e a raiz têm datas que importam.
        if i > 0 and not cert.not_valid_before_utc <= agora <= cert.not_valid_after_utc:
            raise AtestacaoInvalida("Certificado da cadeia de atestação fora da validade.")
        emissor = cadeia[i + 1] if i + 1 < len(cadeia) else cert
        _assinado_por(cert, emissor)
    if hashlib.sha256(_spki(cadeia[-1].public_key())).digest() not in raizes_confiaveis():
        raise AtestacaoInvalida("A cadeia de atestação não termina numa raiz da Google.")
    revogados = series_revogadas()
    if any(format(c.serial_number, "x") in revogados for c in cadeia):
        raise AtestacaoInvalida("Certificado de atestação revogado pela Google.")
    return cadeia


# ---------------------------------------------------------------- entrada


def verificar(certificados_b64: list[str], *, jkt: str | None) -> Resultado:
    """Confere a cadeia e diz o nível de garantia. Levanta AtestacaoInvalida quando a
    atestação não é de confiança (forjada, outra chave, outro app, revogada)."""
    s = get_settings()
    cadeia = _cadeia(certificados_b64)
    folha = cadeia[0]

    chave = folha.public_key()
    if not isinstance(chave, ec.EllipticCurvePublicKey) or not isinstance(chave.curve, ec.SECP256R1):
        raise AtestacaoInvalida("A chave atestada não é P-256.")
    numeros = chave.public_numbers()
    jwk = {"kty": "EC", "crv": "P-256",
           "x": dpop._b64url(numeros.x.to_bytes(32, "big")), "y": dpop._b64url(numeros.y.to_bytes(32, "big"))}
    if jkt is None or dpop.thumbprint(jwk) != jkt:
        raise AtestacaoInvalida("A chave atestada não é a chave DPoP desta sessão.")

    d = _descricao(folha)
    if d.desafio != DESAFIO:
        raise AtestacaoInvalida("Desafio de atestação diferente do esperado.")
    pacotes, assinaturas = _aplicativo(d)
    if s.atestacao_pacote not in pacotes:
        raise AtestacaoInvalida("A chave foi criada por outro app.")
    esperadas = s.atestacao_assinaturas_lista
    if esperadas and not esperadas & assinaturas:
        raise AtestacaoInvalida("App assinado por outro certificado (APK modificado?).")

    if d.nivel_atestacao not in (NIVEL_TEE, NIVEL_STRONGBOX) or d.nivel_keymint not in (NIVEL_TEE, NIVEL_STRONGBOX):
        return Resultado(None, "chave fora do hardware seguro (emulador ou Keystore em software)")
    raiz = _raiz_de_confianca(d)
    if raiz is None:
        return Resultado(None, "aparelho sem raiz de confiança atestada")
    travado, boot = raiz
    if not travado or boot != BOOT_VERIFICADO:
        return Resultado(None, "bootloader destravado ou sistema modificado")
    return Resultado("strongbox" if d.nivel_atestacao == NIVEL_STRONGBOX else "tee")
