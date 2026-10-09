"""
Biometria facial com prova de vida decidida pelo SERVIDOR.

Fluxo (v8 -- prova de vida por landmarks):
1. O app pede um desafio: POST /biometria/desafios -> {desafio_id, acao, ...}.
   `acao` é sorteada aqui (piscar | abrir_boca | sorrir | virar_esquerda |
   virar_direita) e o desafio vale uma vez só, por DESAFIO_VALIDADE_SEG.
2. O app filma o rosto e manda de 4 a 16 quadros cobrindo a ação (`ProvaBiometrica`).
3. O servidor confere o desafio (existe, não expirou, não foi usado, é deste
   usuário); extrai os landmarks de CADA quadro (olhos/boca/giro, via MediaPipe
   em landmarks_service); decide de forma TEMPORAL se a ação aconteceu
   (liveness_logic -- ex.: piscar é a transição aberto->fechado->aberto do EAR,
   não um limiar solto); roda anti-spoofing e compara o rosto com o cadastro.

Por que mudou (a v7 só olhava o giro): virar a cabeça rápido passava e uma foto
parada também; às vezes aprovava sem rosto claro. Agora exigimos ROSTO EM TODOS
os quadros e a transição correta do movimento. A checagem no app continua só
como guia -- quem decide é o servidor, então chamar a API direto não pula nada.

Motores: MediaPipe Face Landmarker (olhos/boca/giro -> liveness) + DeepFace
(anti-spoofing MiniFASNet + reconhecimento Facenet). Ambos importados de forma
preguiçosa: a API e os testes sobem sem eles (modo BIOMETRIA_STUB). A análise
roda dentro de um semáforo (BIOMETRIA_CONCORRENCIA); sem vaga em
BIOMETRIA_ESPERA_SEG, 503. O app deve mandar os quadros SEM espelhamento (o
sinal do yaw depende disso) -- calibre os limiares de liveness_logic num aparelho
real antes de produção.

Embedding: este módulo devolve o vetor em texto puro; quem cifra/decifra para o
banco é core/security.py, chamado pelos services.
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
from app.services import landmarks_service, liveness_logic

logger = logging.getLogger("payflow.biometria")

MODEL_NAME = "Facenet"
DETECTOR_BACKEND = "opencv"
DISTANCE_METRIC = "cosine"
# Os modos (cadastro = sequência completa; login = piscar 3x) e seus passos/
# limiares moram em liveness_logic -- aqui só orquestramos câmera + IA.
MODOS = liveness_logic.MODOS

_DATA_URI_RE = re.compile(r"^data:image/\w+;base64,")
_semaforo: threading.BoundedSemaphore | None = None
_semaforo_lock = threading.Lock()

# Embedding fixo do modo de teste (BIOMETRIA_STUB) -- 128 dims, como o Facenet.
_EMBEDDING_STUB = [0.0] * 128


# =============================================================================
# Desafio
# =============================================================================


def criar_desafio(repo, *, usuario_id: int | None, modo: str = "login") -> dict:
    if modo not in MODOS:
        raise HTTPException(status_code=400, detail="Modo de biometria inválido.")
    s = get_settings()
    publico_id = secrets.token_urlsafe(24)
    expira = tempo.agora() + timedelta(seconds=s.desafio_validade_seg)
    # O MODO vai na coluna `acao` do desafio: o conjunto de passos é fixo por modo
    # (cadastro = piscar 3x + sorrir + virar p/ os dois lados; login = piscar 3x).
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
    # pedido pela MESMA pessoa logada -- um desafio anônimo não serve para MFA.
    if d["usuario_id"] != usuario_id:
        raise HTTPException(status_code=401, detail="Este desafio de biometria pertence a outra sessão.")
    return d["acao"]


# =============================================================================
# Análise das imagens (DeepFace)
# =============================================================================


def _carregar_cv2():
    import cv2
    import numpy as np
    return cv2, np


def _carregar_deepface():
    from deepface import DeepFace
    from deepface.modules import verification
    return DeepFace, verification


def _sem():
    global _semaforo
    with _semaforo_lock:
        if _semaforo is None:
            _semaforo = threading.BoundedSemaphore(max(1, get_settings().biometria_concorrencia))
        return _semaforo


def _decodificar_imagem(imagem_base64: str):
    if not imagem_base64 or not imagem_base64.strip():
        raise HTTPException(status_code=400, detail="Quadro de vídeo vazio.")
    conteudo = _DATA_URI_RE.sub("", imagem_base64.strip())
    try:
        bruto = base64.b64decode(conteudo, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(status_code=400, detail="Imagem inválida: base64 corrompido.")
    limite = get_settings().foto_max_bytes
    if len(bruto) > limite:
        raise HTTPException(status_code=413, detail=f"Imagem muito grande (máximo {limite // (1024 * 1024)}MB).")
    cv2, np = _carregar_cv2()
    imagem = cv2.imdecode(np.frombuffer(bruto, dtype=np.uint8), cv2.IMREAD_COLOR)
    if imagem is None:
        raise HTTPException(status_code=400, detail="Imagem inválida: não foi possível decodificar.")
    return imagem


def _rosto_unico_real(imagem) -> dict:
    DeepFace, _ = _carregar_deepface()
    try:
        rostos = DeepFace.extract_faces(img_path=imagem, anti_spoofing=True, detector_backend=DETECTOR_BACKEND)
    except ValueError as erro:
        raise HTTPException(status_code=400, detail=f"Não foi possível encontrar o rosto: {erro}")
    if len(rostos) != 1:
        raise HTTPException(status_code=400, detail=f"Cada quadro deve ter exatamente 1 rosto (encontrados: {len(rostos)}).")
    if not rostos[0].get("is_real", False):
        raise HTTPException(status_code=401, detail="Falha na prova de vida: a imagem parece ser de uma foto ou tela.")
    return rostos[0]["facial_area"]


def _embedding(imagem) -> list[float]:
    DeepFace, _ = _carregar_deepface()
    try:
        reps = DeepFace.represent(img_path=imagem, model_name=MODEL_NAME, detector_backend=DETECTOR_BACKEND)
    except ValueError as erro:
        raise HTTPException(status_code=400, detail=f"Não foi possível processar o rosto: {erro}")
    if len(reps) != 1:
        raise HTTPException(status_code=400, detail="Cada quadro deve ter exatamente 1 rosto.")
    return reps[0]["embedding"]


def _analisar_sequencia(quadros: list[str], modo: str) -> list[list[float]]:
    """Prova de vida por LANDMARKS + anti-spoofing + extração do embedding.

    1. extrai os sinais de cada quadro (olhos/boca/giro) com o MediaPipe;
    2. confere, de forma temporal, se a SEQUÊNCIA do modo aconteceu
       (liveness_logic) -- exige rosto em todos os quadros, as 3 piscadas, etc.;
    3. roda anti-spoofing (DeepFace) nos quadros frontais escolhidos (foto/tela
       reprova) e devolve o(s) embedding(s) para comparação.
    """
    cv2, _ = _carregar_cv2()
    imagens_bgr = [_decodificar_imagem(q) for q in quadros]
    sinais = [landmarks_service.extrair(cv2.cvtColor(img, cv2.COLOR_BGR2RGB)) for img in imagens_bgr]

    ok, motivo = liveness_logic.verificar_sequencia(sinais, modo)
    if not ok:
        raise HTTPException(status_code=401, detail=motivo)

    idxs = liveness_logic.melhores_frontais(sinais, n=2)
    if not idxs:
        raise HTTPException(status_code=400, detail="Não foi possível isolar um quadro nítido do rosto. Tente com mais luz.")
    for i in idxs:
        _rosto_unico_real(imagens_bgr[i])  # anti-spoofing: reprova foto/tela
    return [_embedding(imagens_bgr[i]) for i in idxs]


def _distancia(a: list[float], b: list[float]) -> tuple[float, float]:
    _, verification = _carregar_deepface()
    limite = float(verification.find_threshold(model_name=MODEL_NAME, distance_metric=DISTANCE_METRIC))
    return float(verification.find_distance(a, b, DISTANCE_METRIC)), limite


def _executar(fn, *args):
    s = get_settings()
    sem = _sem()
    if not sem.acquire(timeout=s.biometria_espera_seg):
        raise HTTPException(status_code=503, detail="Verificação facial ocupada no momento. Tente em alguns segundos.")
    try:
        return fn(*args)
    finally:
        sem.release()


# =============================================================================
# API do módulo
# =============================================================================


def _validar_quadros(quadros: list[str]) -> None:
    if not 2 <= len(quadros) <= 40:
        raise HTTPException(status_code=400, detail="Envie de 2 a 40 quadros cobrindo a sequência pedida.")


def cadastrar(repo, prova, *, usuario_id: int | None = None) -> list[float]:
    """Cadastro: confere o desafio (que precisa ser de CADASTRO -- a sequência
    completa), faz a prova de vida e devolve o embedding."""
    modo = _consumir_desafio(repo, prova.desafio_id, usuario_id)
    _validar_quadros(prova.quadros)
    if get_settings().biometria_stub:
        logger.warning("BIOMETRIA_STUB ligado -- cadastro NÃO confere o rosto (modo de teste).")
        return list(_EMBEDDING_STUB)
    if modo != "cadastro":
        # Impede baixar o nível: usar um desafio curto (login) para abrir conta.
        raise HTTPException(status_code=400, detail="Peça um desafio de cadastro (sequência completa) para abrir a conta.")

    def _fazer():
        return _analisar_sequencia(prova.quadros, modo)[0]

    return _executar(_fazer)


def verificar(repo, prova, *, usuario_id: int, embedding_cadastrado: list[float]) -> dict:
    """MFA: confere desafio + prova de vida e compara com o rosto cadastrado.
    401 genérico se não bater (o número fica só no log)."""
    modo = _consumir_desafio(repo, prova.desafio_id, usuario_id)
    _validar_quadros(prova.quadros)
    if get_settings().biometria_stub:
        logger.warning("BIOMETRIA_STUB ligado -- verificação aprovada SEM conferir o rosto (modo de teste).")
        return {"verificado": True, "distancia": 0.0, "limite": 0.4, "modelo": "stub", "modo": modo}

    def _fazer():
        embeddings = _analisar_sequencia(prova.quadros, modo)
        distancias = [_distancia(e, embedding_cadastrado) for e in embeddings]
        pior = max(d for d, _ in distancias)
        limite = distancias[0][1]
        if pior > limite:
            logger.info("MFA facial reprovado (pior=%.4f limite=%.4f)", pior, limite)
            raise HTTPException(status_code=401, detail="Rosto não corresponde ao titular da conta.")
        return {"verificado": True, "distancia": round(pior, 4), "limite": round(limite, 4),
                "modelo": MODEL_NAME, "modo": modo}

    return _executar(_fazer)
