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
import io
import logging
import os
import re
import subprocess
import sys
import threading
from pathlib import Path
import time

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


def _validar_pdf_local(bruto: bytes) -> None:
    """Nomes PDF aceitam escapes e objetos comprimidos: não basta buscar bytes."""
    from pypdf import PdfReader
    from pypdf.generic import ArrayObject, DictionaryObject, IndirectObject, NameObject

    ativos = {"/JavaScript", "/JS", "/OpenAction", "/AA", "/Launch", "/EmbeddedFile",
              "/EmbeddedFiles", "/RichMedia", "/XFA"}
    try:
        leitor = PdfReader(io.BytesIO(bruto), strict=True)
        if leitor.is_encrypted:
            raise HTTPException(status_code=415, detail="PDF protegido por senha não é aceito.")
        fila = [leitor.trailer]
        vistos = set()
        inicio = time.monotonic()
        visitados = 0
        while fila:
            visitados += 1
            if visitados > 10000 or len(fila) > 10000 or time.monotonic() - inicio > 1:
                raise HTTPException(status_code=413, detail="PDF complexo demais para análise.")
            obj = fila.pop()
            if isinstance(obj, IndirectObject):
                ref = (obj.idnum, obj.generation)
                if ref in vistos:
                    continue
                vistos.add(ref)
                obj = obj.get_object()
            if isinstance(obj, DictionaryObject):
                if any(str(k) in ativos for k in obj):
                    raise HTTPException(status_code=415, detail="PDF com conteúdo ativo não é aceito. Gere um PDF simples.")
                fila.extend(obj.values())
            elif isinstance(obj, ArrayObject):
                fila.extend(obj)
            elif isinstance(obj, NameObject) and str(obj) in ativos:
                raise HTTPException(status_code=415, detail="PDF com conteúdo ativo não é aceito. Gere um PDF simples.")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=400, detail="PDF inválido ou corrompido.") from None


_COMANDO_PDF = (sys.executable, "-m", "app.core.pdf_worker")
_TEMPO_PDF = 5
_VAGAS_PDF = threading.BoundedSemaphore(2)
# O worker escreve esta linha depois de importar tudo: sem ela, a falha foi do processo
# (ambiente, instalação), não do documento (R10).
PRONTO_PDF = b"pronto\n"
# Windows: sem SystemRoot o Python não inicializa o Winsock e `import asyncio` (puxado
# pelo FastAPI/Starlette em algumas versões) quebra com WinError 10106. São caminhos do
# sistema, sem credenciais; o resto do ambiente do pai continua de fora.
_AMBIENTE_WINDOWS = ("SYSTEMROOT", "WINDIR")

logger = logging.getLogger("payflow.arquivos")


def _ambiente_pdf() -> dict[str, str]:
    env = {"PYTHONNOUSERSITE": "1", "OMP_NUM_THREADS": "1"}
    if sys.platform == "win32":
        for nome in _AMBIENTE_WINDOWS:
            if os.environ.get(nome):
                env[nome] = os.environ[nome]
    return env


def _executar_pdf(bruto: bytes, *, texto: bool = False) -> bytes:
    """Parser em processo descartável: prazo real, sem segredos no ambiente."""
    if not _VAGAS_PDF.acquire(blocking=False):
        raise HTTPException(status_code=503, detail="Análise de PDF ocupada. Tente novamente.")
    try:
        try:
            comando = (*_COMANDO_PDF, "--texto") if texto else _COMANDO_PDF
            resultado = subprocess.run(comando, input=bruto, stdout=subprocess.PIPE,
                                       stderr=subprocess.DEVNULL, timeout=_TEMPO_PDF,
                                       cwd=Path(__file__).resolve().parents[2],
                                       env=_ambiente_pdf(),
                                       close_fds=True)
        except subprocess.TimeoutExpired:
            raise HTTPException(status_code=413, detail="PDF excedeu o tempo de análise.") from None
        except OSError:
            raise HTTPException(status_code=503, detail="Análise de PDF indisponível.") from None
    finally:
        _VAGAS_PDF.release()
    iniciou = resultado.stdout.startswith(PRONTO_PDF)
    saida = resultado.stdout[len(PRONTO_PDF):] if iniciou else resultado.stdout
    if resultado.returncode != 0:
        if not iniciou:
            logger.error("Worker de PDF não iniciou (código %s).", resultado.returncode)
            raise HTTPException(status_code=503, detail="Análise de PDF indisponível no servidor. Tente mais tarde.")
        raise HTTPException(status_code=413, detail="PDF excedeu os recursos de análise.")
    if len(saida) > 262150:
        raise HTTPException(status_code=413, detail="Texto do PDF excedeu o limite de análise.")
    return saida


def _validar_pdf(bruto: bytes) -> None:
    _conferir_resultado_pdf(_executar_pdf(bruto))


def _conferir_resultado_pdf(saida: bytes) -> None:
    estados = {b"ok": None, b"400": (400, "PDF inválido ou corrompido."),
               b"413": (413, "PDF complexo demais para análise."),
               b"415": (415, "PDF protegido ou com conteúdo ativo não é aceito.")}
    estado = saida.strip()
    if estado not in estados:
        raise HTTPException(status_code=503, detail="Análise de PDF indisponível.")
    if estados[estado] is not None:
        status, detalhe = estados[estado]
        raise HTTPException(status_code=status, detail=detalhe)


def extrair_texto_pdf(bruto: bytes) -> str:
    saida = _executar_pdf(bruto, texto=True)
    if saida.startswith(b"texto:"):
        try:
            return saida[6:].decode("utf-8")
        except UnicodeError:
            raise HTTPException(status_code=400, detail="Texto do PDF inválido.") from None
    _conferir_resultado_pdf(saida)
    raise HTTPException(status_code=503, detail="Extração de PDF indisponível.")


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
        _validar_pdf(bruto)
    return bruto, mime, hashlib.sha256(bruto).hexdigest()
