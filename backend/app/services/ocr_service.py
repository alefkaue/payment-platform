"""
Leitura de documentos: OCR + extração/validação de campos.

OCR NÃO É VALIDAÇÃO DE AUTENTICIDADE. Ler o texto de uma CNH não prova que ela é
verdadeira -- só permite conferir que os dados batem com o que a pessoa declarou.
A prova de que a pessoa é a dona do documento vem do rosto (foto do documento x
selfie com prova de vida, em documento_service). Em produção, a autenticidade
deve vir de um provedor especializado (ex.: Serpro Datavalid) -- ver AZURE.md.

Provedores (DOCUMENTO_PROVEDOR):
- "tesseract": Tesseract (lang "por") com pré-processamento OpenCV (cinza,
  ampliação, CLAHE, limiarização adaptativa) -- melhora muito a leitura de RG/CNH.
- "auto": Tesseract se o binário existir; senão "sem_ocr".
- "sem_ocr": o documento é validado (arquivo, rosto) mas o TEXTO não é conferido
  por máquina -- o caso vai para análise humana em vez de ser aprovado às cegas.
- "stub": testes -- devolve o que foi declarado. Recusado em produção.

As funções de extração (CPF, datas, nome, MRZ) são puras e testadas em
tests/test_documentos_kyc.py.
"""

from __future__ import annotations

import difflib
import logging
import os
import re
import shutil
import unicodedata
from datetime import date

from fastapi import HTTPException

from app.core.config import get_settings
from app.core.documentos import cpf_valido, somente_digitos

logger = logging.getLogger("payflow.ocr")

_CPF_RE = re.compile(r"(?<!\d)(\d{3})[.\s]?(\d{3})[.\s]?(\d{3})[-\s.]?(\d{2})(?!\d)")
_DATA_RE = re.compile(r"(?<!\d)(\d{2})[/.\-](\d{2})[/.\-](\d{4})(?!\d)")


# =============================================================================
# Provedor
# =============================================================================


def _tesseract_cmd() -> str | None:
    return os.environ.get("TESSERACT_CMD") or shutil.which("tesseract")


def provedor() -> str:
    p = get_settings().documento_provedor
    if p == "auto":
        return "tesseract" if _tesseract_cmd() else "sem_ocr"
    if p == "tesseract" and not _tesseract_cmd():
        raise HTTPException(status_code=503, detail="Leitura de documentos indisponível (Tesseract não instalado).")
    if p not in ("tesseract", "sem_ocr", "stub"):
        raise RuntimeError(f"DOCUMENTO_PROVEDOR desconhecido: {p!r}")
    return p


def _preprocessar(img_bgr):
    """Cinza -> amplia para ~1600 px de largura -> CLAHE -> limiarização adaptativa."""
    import cv2

    cinza = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    h, w = cinza.shape[:2]
    if w < 1600:
        f = 1600 / w
        cinza = cv2.resize(cinza, (int(w * f), int(h * f)), interpolation=cv2.INTER_CUBIC)
    cinza = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(cinza)
    cinza = cv2.medianBlur(cinza, 3)
    return cv2.adaptiveThreshold(cinza, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 15)


def extrair_texto(img_bgr) -> str:
    import pytesseract

    cmd = _tesseract_cmd()
    if cmd:
        pytesseract.pytesseract.tesseract_cmd = cmd
    try:
        idiomas = pytesseract.get_languages(config="")
    except Exception:  # noqa: BLE001
        idiomas = []
    lang = "por" if "por" in idiomas else "eng"
    if lang != "por":
        logger.warning("Tesseract sem o idioma 'por' -- instale tesseract-ocr-por para ler acentos.")
    binaria = _preprocessar(img_bgr)
    # Duas passagens: texto corrido (psm 6) e esparso (psm 11) -- documentos BR
    # têm campos espalhados que um modo só perde.
    partes = [pytesseract.image_to_string(binaria, lang=lang, config="--psm 6", timeout=20),
              pytesseract.image_to_string(binaria, lang=lang, config="--psm 11", timeout=20)]
    return "\n".join(partes)


# =============================================================================
# Extração de campos (funções puras)
# =============================================================================


def normalizar(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Z0-9 ]+", " ", sem_acento.upper())


def encontrar_cpfs(texto: str) -> list[str]:
    """CPFs com dígito verificador válido (descarta leituras erradas do OCR)."""
    achados = []
    for m in _CPF_RE.finditer(texto or ""):
        c = "".join(m.groups())
        if cpf_valido(c) and c not in achados:
            achados.append(c)
    return achados


def encontrar_datas(texto: str) -> list[date]:
    datas = []
    for d, m, a in _DATA_RE.findall(texto or ""):
        try:
            dt = date(int(a), int(m), int(d))
        except ValueError:
            continue
        if 1900 <= dt.year <= 2100 and dt not in datas:
            datas.append(dt)
    return datas


def nome_confere(nome_declarado: str, texto: str, *, minimo: float = 0.8) -> bool:
    """Tolerante a erro de OCR: cada parte do nome (> 2 letras) precisa aparecer
    no texto com semelhança >= 0.85; exige o primeiro e o último nome e pelo
    menos `minimo` das partes."""
    partes = [p for p in normalizar(nome_declarado).split() if len(p) > 2]
    if not partes:
        return False
    palavras = normalizar(texto).split()

    def achou(p: str) -> bool:
        return any(w == p or difflib.SequenceMatcher(None, p, w).ratio() >= 0.85 for w in palavras)

    encontrados = [achou(p) for p in partes]
    return encontrados[0] and encontrados[-1] and sum(encontrados) / len(partes) >= minimo


# =============================================================================
# MRZ (ICAO 9303) -- CIN (verso) e passaporte
# =============================================================================


def _valor_mrz(c: str) -> int:
    if c.isdigit():
        return int(c)
    if "A" <= c <= "Z":
        return ord(c) - 55
    return 0  # "<"


def digito_mrz(campo: str) -> int:
    """Dígito verificador ICAO: pesos 7, 3, 1 repetidos, módulo 10."""
    pesos = (7, 3, 1)
    return sum(_valor_mrz(c) * pesos[i % 3] for i, c in enumerate(campo)) % 10


def _data_mrz(aammdd: str, *, futuro: bool) -> date | None:
    if not aammdd.isdigit():
        return None
    a, m, d = int(aammdd[:2]), int(aammdd[2:4]), int(aammdd[4:])
    hoje = date.today().year % 100
    # nascimento: AA > ano atual = século passado; validade: sempre 2000+
    seculo = 2000 if futuro or a <= hoje else 1900
    try:
        return date(seculo + a, m, d)
    except ValueError:
        return None


def _linhas_mrz(texto: str) -> list[str]:
    linhas = []
    for bruta in (texto or "").upper().splitlines():
        l = re.sub(r"\s+", "", bruta).replace("«", "<")
        if len(l) >= 28 and re.fullmatch(r"[A-Z0-9<]+", l) and l.count("<") >= 2:
            linhas.append(l)
    return linhas


def ler_mrz(texto: str) -> dict | None:
    """Procura uma MRZ TD1 (3x30, documento de identidade) ou TD3 (2x44,
    passaporte). Devolve os campos e se TODOS os dígitos verificadores batem."""
    linhas = _linhas_mrz(texto)
    for i in range(len(linhas) - 2):  # TD1
        l1, l2, l3 = (linhas[i][:30].ljust(30, "<"), linhas[i + 1][:30].ljust(30, "<"), linhas[i + 2][:30].ljust(30, "<"))
        if l1[0] not in "ACI":
            continue
        numero, dv_num = l1[5:14], l1[14]
        nasc, dv_nasc = l2[0:6], l2[6]
        val, dv_val = l2[8:14], l2[14]
        composto = l1[5:30] + l2[0:7] + l2[8:15] + l2[18:29]
        ok = (str(digito_mrz(numero)) == dv_num and str(digito_mrz(nasc)) == dv_nasc
              and str(digito_mrz(val)) == dv_val and str(digito_mrz(composto)) == l2[29])
        return {"formato": "TD1", "valido": ok, "pais": l1[2:5].replace("<", ""), "numero": numero.replace("<", ""),
                "nascimento": _data_mrz(nasc, futuro=False), "validade": _data_mrz(val, futuro=True),
                "opcional": l1[15:30].replace("<", ""), "nome": " ".join(p for p in l3.replace("<<", " ").split("<") if p).strip()}
    for i in range(len(linhas) - 1):  # TD3
        l1, l2 = linhas[i][:44].ljust(44, "<"), linhas[i + 1][:44].ljust(44, "<")
        if l1[0] != "P":
            continue
        numero, nasc, val = l2[0:9], l2[13:19], l2[21:27]
        composto = l2[0:10] + l2[13:20] + l2[21:43]
        ok = (str(digito_mrz(numero)) == l2[9] and str(digito_mrz(nasc)) == l2[19]
              and str(digito_mrz(val)) == l2[27] and str(digito_mrz(composto)) == l2[43])
        return {"formato": "TD3", "valido": ok, "pais": l1[2:5].replace("<", ""), "numero": numero.replace("<", ""),
                "nascimento": _data_mrz(nasc, futuro=False), "validade": _data_mrz(val, futuro=True),
                "opcional": l2[28:42].replace("<", ""), "nome": " ".join(l1[5:].replace("<<", " ").replace("<", " ").split())}
    return None


# =============================================================================
# QR code (CNH digital / CIN)
# =============================================================================


def ler_qr(img_bgr) -> list[str]:
    import cv2

    try:
        ok, textos, _, _ = cv2.QRCodeDetector().detectAndDecodeMulti(img_bgr)
    except cv2.error:
        return []
    return [t for t in (textos or []) if t] if ok else []


def cpf_no_texto(cpf: str, texto: str) -> bool:
    return somente_digitos(cpf) in encontrar_cpfs(texto)
