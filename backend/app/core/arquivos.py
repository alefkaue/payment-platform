"""
Validação de arquivos enviados (documentos de identidade e da empresa).

Nunca confiamos no nome do arquivo nem no Content-Type/data URI que o cliente
mandou: o tipo é decidido pela ASSINATURA real do conteúdo (magic bytes), o
tamanho é limitado antes de decodificar tudo, e PDFs com conteúdo ativo
(JavaScript, ação de abertura, arquivo embutido) são recusados -- é vetor
clássico de ataque contra quem for abrir o documento na análise manual.
"""

import base64
import binascii
import hashlib
import re

from fastapi import HTTPException

_DATA_URI_RE = re.compile(r"^data:[\w.+/-]+;base64,")

# (mime, prefixo) -- o WEBP tem "RIFF....WEBP".
_ASSINATURAS = (
    ("image/jpeg", b"\xff\xd8\xff"),
    ("image/png", b"\x89PNG\r\n\x1a\n"),
    ("application/pdf", b"%PDF-"),
)
IMAGENS = frozenset({"image/jpeg", "image/png", "image/webp"})
DOCUMENTOS = IMAGENS | {"application/pdf"}

# Marcadores de conteúdo ativo em PDF.
_PDF_ATIVO = (b"/JavaScript", b"/JS", b"/OpenAction", b"/Launch", b"/EmbeddedFile", b"/RichMedia", b"/XFA")


def detectar_mime(bruto: bytes) -> str | None:
    for mime, prefixo in _ASSINATURAS:
        if bruto.startswith(prefixo):
            return mime
    if len(bruto) >= 12 and bruto[:4] == b"RIFF" and bruto[8:12] == b"WEBP":
        return "image/webp"
    return None


def validar_arquivo(conteudo_b64: str, *, permitidos: frozenset[str], limite_bytes: int) -> tuple[bytes, str, str]:
    """base64 -> (bruto, mime, sha256). Levanta 400/413/415."""
    if not conteudo_b64 or not conteudo_b64.strip():
        raise HTTPException(status_code=400, detail="Arquivo vazio.")
    texto = _DATA_URI_RE.sub("", conteudo_b64.strip())
    # base64 ocupa ~4/3 do original: recusa cedo sem decodificar um arquivo gigante.
    if len(texto) > limite_bytes * 4 // 3 + 16:
        raise HTTPException(status_code=413, detail=f"Arquivo muito grande (máximo {limite_bytes // (1024 * 1024)}MB).")
    try:
        bruto = base64.b64decode(texto, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(status_code=400, detail="Arquivo inválido: base64 corrompido.")
    if len(bruto) > limite_bytes:
        raise HTTPException(status_code=413, detail=f"Arquivo muito grande (máximo {limite_bytes // (1024 * 1024)}MB).")
    if len(bruto) < 1024:
        raise HTTPException(status_code=400, detail="Arquivo pequeno demais para ser um documento legível.")
    mime = detectar_mime(bruto)
    if mime is None or mime not in permitidos:
        raise HTTPException(status_code=415, detail="Tipo de arquivo não aceito. Envie JPG, PNG, WEBP" +
                            (" ou PDF." if "application/pdf" in permitidos else "."))
    if mime == "application/pdf":
        if any(m in bruto for m in _PDF_ATIVO):
            raise HTTPException(status_code=415, detail="PDF com conteúdo ativo (scripts/anexos) não é aceito. Gere um PDF simples.")
        if b"/Encrypt" in bruto:
            raise HTTPException(status_code=415, detail="PDF protegido por senha não é aceito.")
    return bruto, mime, hashlib.sha256(bruto).hexdigest()
