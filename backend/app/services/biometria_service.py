"""
Biometria facial com prova de vida decidida pelo SERVIDOR.

Fluxo (v7):
1. O app pede um desafio: POST /biometria/desafios -> {desafio_id, acao, expira_em}.
   `acao` é sorteada aqui (virar_esquerda | virar_direita) e o desafio vale uma
   vez só, por DESAFIO_VALIDADE_SEG.
2. O app filma o rosto e manda de 2 a 5 quadros: o primeiro de frente, os
   seguintes durante a ação pedida (`ProvaBiometrica`).
3. O servidor confere o desafio (existe, não expirou, não foi usado, é deste
   usuário), roda anti-spoofing em todos os quadros, mede o giro da cabeça entre
   o quadro frontal e o mais virado, e compara o rosto com o cadastro.

Antes (v6) a "liveness" com piscar/virar rodava só no navegador (MediaPipe em
app/src/components/payflow/liveness.tsx) e o servidor recebia uma foto solta --
quem chamasse a API direto pulava a checagem. A checagem do app continua útil
como guia para o usuário, mas quem decide agora é o servidor.

Motor: DeepFace (reconhecimento Facenet + anti-spoofing MiniFASNet). Importado de
forma preguiçosa: a API e os testes sobem sem TensorFlow. A análise roda dentro
de um semáforo (BIOMETRIA_CONCORRENCIA) para não ocupar todas as threads da API;
quem não consegue vaga em BIOMETRIA_ESPERA_SEG recebe 503.

Giro da cabeça: usamos a posição do ponto médio entre os olhos em relação ao
centro da caixa do rosto (fração da largura). De frente fica perto de 0; virando
a cabeça ele se desloca. O SINAL depende de a câmera espelhar ou não a imagem --
o app deve mandar os quadros SEM espelhamento. Calibre GIRO_MINIMO e o sinal num
aparelho real antes de produção.

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

logger = logging.getLogger("payflow.biometria")

MODEL_NAME = "Facenet"
DETECTOR_BACKEND = "opencv"
DISTANCE_METRIC = "cosine"
ACOES = ("virar_esquerda", "virar_direita")
# Deslocamento mínimo (fração da largura do rosto) entre o quadro frontal e o
# mais virado. Frontal precisa estar abaixo de FRONTAL_MAXIMO.
GIRO_MINIMO = 0.06
FRONTAL_MAXIMO = 0.08
# Com a imagem SEM espelhamento, virar para a esquerda da pessoa desloca o
# ponto entre os olhos para a direita da imagem (deslocamento positivo).
SINAL_ACAO = {"virar_esquerda": 1, "virar_direita": -1}

_DATA_URI_RE = re.compile(r"^data:image/\w+;base64,")
_semaforo: threading.BoundedSemaphore | None = None
_semaforo_lock = threading.Lock()

# Embedding fixo do modo de teste (BIOMETRIA_STUB) -- 128 dims, como o Facenet.
_EMBEDDING_STUB = [0.0] * 128


# =============================================================================
# Desafio
# =============================================================================


def criar_desafio(repo, *, usuario_id: int | None) -> dict:
    s = get_settings()
    publico_id = secrets.token_urlsafe(24)
    acao = ACOES[secrets.randbelow(len(ACOES))]
    expira = tempo.agora() + timedelta(seconds=s.desafio_validade_seg)
    repo.criar_desafio(publico_id=publico_id, acao=acao, usuario_id=usuario_id, expira_em=expira)
    instrucao = {
        "virar_esquerda": "Olhe para a câmera e depois vire devagar o rosto para a sua esquerda.",
        "virar_direita": "Olhe para a câmera e depois vire devagar o rosto para a sua direita.",
    }[acao]
    return {"desafio_id": publico_id, "acao": acao, "instrucao": instrucao, "expira_em": expira,
            "quadros_min": 2, "quadros_max": 5}


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


def _deslocamento(area: dict) -> float:
    olho_e, olho_d = area.get("left_eye"), area.get("right_eye")
    if not olho_e or not olho_d or not area.get("w"):
        raise HTTPException(status_code=400, detail="Não foi possível localizar os olhos. Tente com mais luz, sem óculos escuros.")
    meio_x = (olho_e[0] + olho_d[0]) / 2
    centro_x = area["x"] + area["w"] / 2
    return (meio_x - centro_x) / area["w"]


def _embedding(imagem) -> list[float]:
    DeepFace, _ = _carregar_deepface()
    try:
        reps = DeepFace.represent(img_path=imagem, model_name=MODEL_NAME, detector_backend=DETECTOR_BACKEND)
    except ValueError as erro:
        raise HTTPException(status_code=400, detail=f"Não foi possível processar o rosto: {erro}")
    if len(reps) != 1:
        raise HTTPException(status_code=400, detail="Cada quadro deve ter exatamente 1 rosto.")
    return reps[0]["embedding"]


def _analisar_quadros(quadros: list[str], acao: str) -> tuple[list[float], list[float]]:
    """Prova de vida + extração. Devolve (embedding do quadro frontal, embedding
    do quadro mais virado). Levanta HTTPException se algo falhar."""
    imagens = [_decodificar_imagem(q) for q in quadros]
    desloc = [_deslocamento(_rosto_unico_real(img)) for img in imagens]
    if abs(desloc[0]) > FRONTAL_MAXIMO:
        raise HTTPException(status_code=401, detail="O primeiro quadro precisa ser de frente para a câmera.")
    sinal = SINAL_ACAO[acao]
    idx = max(range(1, len(desloc)), key=lambda i: (desloc[i] - desloc[0]) * sinal)
    if (desloc[idx] - desloc[0]) * sinal < GIRO_MINIMO:
        raise HTTPException(status_code=401, detail="Não identificamos o movimento pedido. Tente de novo, virando o rosto devagar.")
    return _embedding(imagens[0]), _embedding(imagens[idx])


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
    if not 2 <= len(quadros) <= 5:
        raise HTTPException(status_code=400, detail="Envie de 2 a 5 quadros: o primeiro de frente e os seguintes durante o movimento.")


def cadastrar(repo, prova, *, usuario_id: int | None = None) -> list[float]:
    """Cadastro: confere o desafio, faz a prova de vida e devolve o embedding."""
    acao = _consumir_desafio(repo, prova.desafio_id, usuario_id)
    _validar_quadros(prova.quadros)
    if get_settings().biometria_stub:
        logger.warning("BIOMETRIA_STUB ligado -- cadastro NÃO confere o rosto (modo de teste).")
        return list(_EMBEDDING_STUB)

    def _fazer():
        frontal, virado = _analisar_quadros(prova.quadros, acao)
        dist, limite = _distancia(frontal, virado)
        if dist > limite:
            raise HTTPException(status_code=401, detail="Os quadros não parecem ser da mesma pessoa.")
        return frontal

    return _executar(_fazer)


def verificar(repo, prova, *, usuario_id: int, embedding_cadastrado: list[float]) -> dict:
    """MFA: confere desafio + prova de vida e compara com o rosto cadastrado.
    401 genérico se não bater (o número fica só no log)."""
    acao = _consumir_desafio(repo, prova.desafio_id, usuario_id)
    _validar_quadros(prova.quadros)
    if get_settings().biometria_stub:
        logger.warning("BIOMETRIA_STUB ligado -- verificação aprovada SEM conferir o rosto (modo de teste).")
        return {"verificado": True, "distancia": 0.0, "limite": 0.4, "modelo": "stub", "acao": acao}

    def _fazer():
        frontal, virado = _analisar_quadros(prova.quadros, acao)
        d1, limite = _distancia(frontal, embedding_cadastrado)
        d2, _ = _distancia(virado, embedding_cadastrado)
        if max(d1, d2) > limite:
            logger.info("MFA facial reprovado (d1=%.4f d2=%.4f limite=%.4f)", d1, d2, limite)
            raise HTTPException(status_code=401, detail="Rosto não corresponde ao titular da conta.")
        return {"verificado": True, "distancia": round(max(d1, d2), 4), "limite": round(limite, 4),
                "modelo": MODEL_NAME, "acao": acao}

    return _executar(_fazer)
