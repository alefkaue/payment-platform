"""
Biometria facial com prova de vida decidida pelo SERVIDOR.

Fluxo (v9):
1. O app pede um desafio: POST /biometria/desafios {modo} -> {desafio_id, passos}.
   modo "cadastro" = piscar 3x + sorrir + virar p/ os dois lados; "login" = piscar
   3x. O desafio vale uma vez só, por DESAFIO_VALIDADE_SEG, e fica preso a quem
   pediu (ou ao login informado).
2. O app filma e manda de 6 a 40 quadros cobrindo a sequência (`ProvaBiometrica`).
3. O servidor, com o desafio conferido:
   a. extrai os landmarks de CADA quadro (MediaPipe) e confere a sequência de
      forma temporal (liveness_logic) -- rosto em todos os quadros, 3 piscadas
      reais, giro forte e sustentado...;
   b. confere que é a MESMA pessoa do começo ao fim (amostra quadros do início,
      meio e fim) -- trocar de rosto no meio da gravação não passa;
   c. anti-spoofing passivo (MiniFASNet) nos quadros usados;
   d. extrai o template (SFace) e, na verificação, compara com o cadastrado.

Por que o servidor e não o app? O app também confere (para guiar a pessoa), mas
quem chamar a API direto não pula nada. Motores em face_engine (OpenCV leve,
padrão) -- sem TensorFlow. Concorrência limitada por semáforo; sem vaga em
BIOMETRIA_ESPERA_SEG, 503.

O template sai daqui em texto puro; quem cifra/decifra é core/security.py.
"""

import base64
import binascii
import logging
import re
import secrets
import threading
from datetime import timedelta

from fastapi import HTTPException

from app.core import tempo
from app.core.config import get_settings
from app.services import face_engine, landmarks_service, liveness_logic

logger = logging.getLogger("payflow.biometria")

MODOS = liveness_logic.MODOS

_DATA_URI_RE = re.compile(r"^data:image/[\w.+-]+;base64,")
_semaforo: threading.BoundedSemaphore | None = None
_semaforo_lock = threading.Lock()

# Template fixo do modo de teste (BIOMETRIA_STUB).
_EMBEDDING_STUB = [0.0] * 128
MODELO_STUB = "stub"


# =============================================================================
# Desafio
# =============================================================================


def criar_desafio(repo, *, usuario_id: int | None, modo: str = "login") -> dict:
    if modo not in MODOS:
        raise HTTPException(status_code=400, detail="Modo de biometria inválido.")
    s = get_settings()
    publico_id = secrets.token_urlsafe(24)
    expira = tempo.agora() + timedelta(seconds=s.desafio_validade_seg)
    # O MODO vai na coluna `acao` do desafio: o conjunto de passos é fixo por modo.
    repo.criar_desafio(publico_id=publico_id, acao=modo, usuario_id=usuario_id, expira_em=expira)
    return {"desafio_id": publico_id, "modo": modo, "passos": liveness_logic.passos_do_modo(modo),
            "expira_em": expira, "quadros_min": liveness_logic.MIN_QUADROS, "quadros_max": 40}


def _consumir_desafio(repo, desafio_id: str, usuario_id: int | None) -> str:
    d = repo.consumir_desafio(desafio_id)
    if d is None:
        raise HTTPException(status_code=401, detail="Desafio de biometria inválido ou já usado. Peça um novo.")
    if d["expira_em"] < tempo.agora():
        raise HTTPException(status_code=401, detail="Desafio de biometria expirado. Peça um novo.")
    # Cadastro usa desafio anônimo (None == None); verificação exige desafio
    # pedido pela MESMA pessoa -- um desafio anônimo não serve para MFA.
    if d["usuario_id"] != usuario_id:
        raise HTTPException(status_code=401, detail="Este desafio de biometria pertence a outra sessão.")
    return d["acao"]


# =============================================================================
# Imagem
# =============================================================================


def _sem():
    global _semaforo
    with _semaforo_lock:
        if _semaforo is None:
            _semaforo = threading.BoundedSemaphore(max(1, get_settings().biometria_concorrencia))
        return _semaforo


def _executar(fn, *args):
    s = get_settings()
    sem = _sem()
    if not sem.acquire(timeout=s.biometria_espera_seg):
        raise HTTPException(status_code=503, detail="Verificação facial ocupada no momento. Tente em alguns segundos.")
    try:
        return fn(*args)
    finally:
        sem.release()


def decodificar_imagem(imagem_base64: str, *, limite_bytes: int | None = None):
    """base64/data URI -> imagem BGR (numpy). Confere tamanho e se decodifica de
    verdade (não confia no rótulo do data URI)."""
    if not imagem_base64 or not imagem_base64.strip():
        raise HTTPException(status_code=400, detail="Imagem vazia.")
    conteudo = _DATA_URI_RE.sub("", imagem_base64.strip())
    try:
        bruto = base64.b64decode(conteudo, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(status_code=400, detail="Imagem inválida: base64 corrompido.")
    limite = limite_bytes or get_settings().foto_max_bytes
    if len(bruto) > limite:
        raise HTTPException(status_code=413, detail=f"Imagem muito grande (máximo {limite // (1024 * 1024)}MB).")
    import cv2
    import numpy as np

    imagem = cv2.imdecode(np.frombuffer(bruto, dtype=np.uint8), cv2.IMREAD_COLOR)
    if imagem is None:
        raise HTTPException(status_code=400, detail="Imagem inválida: não foi possível decodificar.")
    h, w = imagem.shape[:2]
    if min(h, w) < 120 or max(h, w) > 6000:
        raise HTTPException(status_code=400, detail="Resolução de imagem fora do aceito.")
    return imagem


# =============================================================================
# Análise
# =============================================================================


def _amostras(n: int, frontais: list[int]) -> list[int]:
    """Quadros usados na checagem de identidade: os frontais + início, meio e fim."""
    return sorted(set(frontais + [0, n // 2, n - 1]))


def _analisar_sequencia(quadros: list[str], modo: str) -> dict:
    import cv2

    imagens = [decodificar_imagem(q) for q in quadros]
    sinais = [landmarks_service.extrair(cv2.cvtColor(img, cv2.COLOR_BGR2RGB)) for img in imagens]

    ok, motivo = liveness_logic.verificar_sequencia(sinais, modo)
    if not ok:
        raise HTTPException(status_code=401, detail=motivo)

    frontais = liveness_logic.melhores_frontais(sinais, n=2)
    if not frontais:
        raise HTTPException(status_code=400, detail="Não foi possível isolar um quadro nítido do rosto. Tente com mais luz.")

    m = face_engine.motor()
    referencia: list[float] | None = None
    templates: list[list[float]] = []
    prob_real_min = 1.0
    for i in _amostras(len(imagens), frontais):
        rosto = m.rosto_unico(imagens[i], score_minimo=0.75)
        real, prob = m.anti_spoof(imagens[i], rosto)
        prob_real_min = min(prob_real_min, prob)
        if not real:
            raise HTTPException(status_code=401, detail="Falha na prova de vida: a imagem parece ser foto, tela ou máscara.")
        t = m.embedding(imagens[i], rosto)
        if referencia is None:
            referencia = t
        elif m.similaridade(referencia, t) < m.limiar:
            raise HTTPException(status_code=401, detail="O rosto mudou durante a verificação. Faça tudo sem sair da câmera.")
        if i in frontais:
            templates.append(t)
    return {"templates": templates, "modelo": m.nome, "prob_real_min": round(prob_real_min, 4)}


# =============================================================================
# API do módulo
# =============================================================================


def _validar_quadros(quadros: list[str]) -> None:
    if not 2 <= len(quadros) <= 40:
        raise HTTPException(status_code=400, detail="Envie de 2 a 40 quadros cobrindo a sequência pedida.")


def stub_ligado() -> bool:
    return get_settings().biometria_stub


def cadastrar(repo, prova, *, usuario_id: int | None = None) -> dict:
    """Cadastro: confere o desafio (que precisa ser de CADASTRO), faz a prova de
    vida e devolve {"vetor", "modelo"}."""
    modo = _consumir_desafio(repo, prova.desafio_id, usuario_id)
    _validar_quadros(prova.quadros)
    if stub_ligado():
        logger.warning("BIOMETRIA_STUB ligado -- cadastro NÃO confere o rosto (modo de teste).")
        return {"vetor": list(_EMBEDDING_STUB), "modelo": MODELO_STUB}
    if modo != "cadastro":
        # Impede baixar o nível: usar um desafio curto (login) para cadastrar rosto.
        raise HTTPException(status_code=400, detail="Peça um desafio de cadastro (sequência completa).")

    r = _executar(_analisar_sequencia, prova.quadros, modo)
    return {"vetor": r["templates"][0], "modelo": r["modelo"], "prob_real_min": r["prob_real_min"]}


def verificar(repo, prova, *, usuario_id: int, template: dict) -> dict:
    """MFA: confere desafio + prova de vida e compara com o template cadastrado.
    401 genérico se não bater (o número fica só no log)."""
    modo = _consumir_desafio(repo, prova.desafio_id, usuario_id)
    _validar_quadros(prova.quadros)
    if stub_ligado():
        logger.warning("BIOMETRIA_STUB ligado -- verificação aprovada SEM conferir o rosto (modo de teste).")
        return {"verificado": True, "similaridade": 1.0, "limiar": 0.0, "modelo": MODELO_STUB, "modo": modo}

    m = face_engine.motor()
    if template.get("modelo") != m.nome:
        raise HTTPException(status_code=409, detail="Seu cadastro facial é de uma versão anterior. Refaça a biometria no app.")

    r = _executar(_analisar_sequencia, prova.quadros, modo)
    pior = min(m.similaridade(t, template["vetor"]) for t in r["templates"])
    if pior < m.limiar:
        logger.info("MFA facial reprovado (similaridade=%.4f limiar=%.4f)", pior, m.limiar)
        raise HTTPException(status_code=401, detail="Rosto não corresponde ao titular da conta.")
    return {"verificado": True, "similaridade": round(pior, 4), "limiar": m.limiar, "modelo": m.nome,
            "modo": modo, "prob_real_min": r["prob_real_min"]}


def template_de_documento(imagem_bgr) -> list[float] | None:
    """Template do rosto impresso num documento (foto 3x4 da CNH/RG/CIN). None se
    não achar exatamente um rosto. Limiares de detecção mais baixos: a foto do
    documento é pequena e impressa."""
    if stub_ligado():
        return None
    m = face_engine.motor()
    try:
        rosto = m.rosto_unico(imagem_bgr, score_minimo=0.6, minimo_px=24)
    except HTTPException:
        return None
    return m.embedding(imagem_bgr, rosto)


def similaridade(a: list[float], b: list[float]) -> float:
    return face_engine.motor().similaridade(a, b)
