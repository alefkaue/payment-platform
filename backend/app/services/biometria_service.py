"""
Serviço de biometria facial: liveness detection + reconhecimento facial via DeepFace
(https://github.com/serengil/deepface).

Por que DeepFace e não os outros repositórios enviados:
- "Face-Recognition-System-using-DeepFace" e "Face-Recognition-Authentication" são
  aplicações de exemplo construídas SOBRE o DeepFace (ou sobre `face_recognition`/dlib)
  -- apontam para o mesmo motor.
- "Face-Liveness-Detection" e o pacote `liveness-detector` fariam SÓ a parte de
  liveness, exigindo integrar uma segunda lib para o reconhecimento.
- O DeepFace entrega os dois: reconhecimento (`represent`/`verify`) e
  anti-spoofing/liveness (`extract_faces(..., anti_spoofing=True)`, modelo MiniFASNet
  ~4MB). Uma dependência, liveness por foto única (passiva).

Arquitetura de dados: este módulo trabalha só com o EMBEDDING em texto puro (vetor
de floats). Quem cifra/decifra para o banco é a camada de service (usuario_service /
pagamento_service) via core/security.py -- aqui não há cripto, de propósito, pra
manter a responsabilidade única.

Mudanças de segurança desta versão (auditoria):
- Limite de tamanho da imagem decodificada (item #4: foto gigante travava o servidor).
- As mensagens de erro de "rosto não bateu" NÃO expõem mais distância/limite (item #3:
  isso ajudava um atacante a calibrar a foto). O detalhe numérico continua sendo
  gravado na auditoria interna, só não volta pro cliente.
- O RATE-LIMIT de tentativas não fica aqui: ele depende do usuário/sessão e é
  aplicado nos services (que têm acesso ao repositório). Ver usuario_service e
  pagamento_service.
"""

import base64
import binascii
import logging
import re

from fastapi import HTTPException

from app.core.config import get_settings

# cv2/numpy/deepface/tensorflow são pesados (~1-2GB) e só são necessários quando
# uma foto é de fato processada. Importamos de forma PREGUIÇOSA dentro das funções
# para a app subir (e os testes que não tocam biometria rodarem) sem TensorFlow
# instalado -- ver _carregar_cv2 / _carregar_deepface.

logger = logging.getLogger("payflow.biometria")

MODEL_NAME = "Facenet"
DETECTOR_BACKEND = "opencv"
DISTANCE_METRIC = "cosine"

_DATA_URI_RE = re.compile(r"^data:image/\w+;base64,")


def _carregar_cv2():
    import cv2
    import numpy as np
    return cv2, np


def _carregar_deepface():
    from deepface import DeepFace
    from deepface.modules import verification
    return DeepFace, verification


def _decodificar_imagem(imagem_base64: str):
    """base64 (com ou sem prefixo data:image/...) -> imagem BGR (OpenCV/DeepFace).
    Rejeita cedo foto vazia, base64 corrompido ou acima do tamanho máximo."""
    if not imagem_base64 or not imagem_base64.strip():
        raise HTTPException(status_code=400, detail="Nenhuma foto foi enviada.")

    conteudo = _DATA_URI_RE.sub("", imagem_base64.strip())
    try:
        bytes_imagem = base64.b64decode(conteudo, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(status_code=400, detail="Foto inválida: base64 corrompido.")

    limite = get_settings().foto_max_bytes
    if len(bytes_imagem) > limite:
        raise HTTPException(
            status_code=413,
            detail=f"Foto muito grande (máximo {limite // (1024 * 1024)}MB). Tire outra foto.",
        )

    cv2, np = _carregar_cv2()
    array = np.frombuffer(bytes_imagem, dtype=np.uint8)
    imagem = cv2.imdecode(array, cv2.IMREAD_COLOR)
    if imagem is None:
        raise HTTPException(status_code=400, detail="Foto inválida: não foi possível decodificar a imagem.")
    return imagem


def _checar_liveness(imagem) -> None:
    """Levanta HTTPException se não houver exatamente 1 rosto REAL (anti-spoofing)."""
    DeepFace, _ = _carregar_deepface()
    try:
        rostos = DeepFace.extract_faces(
            img_path=imagem, anti_spoofing=True, detector_backend=DETECTOR_BACKEND
        )
    except ValueError as erro:
        raise HTTPException(status_code=400, detail=f"Não foi possível processar a foto: {erro}")

    if len(rostos) == 0:
        raise HTTPException(status_code=400, detail="Nenhum rosto detectado na foto.")
    if len(rostos) > 1:
        raise HTTPException(
            status_code=400,
            detail=f"A foto deve ter apenas 1 rosto (foram detectados {len(rostos)}).",
        )
    if not rostos[0].get("is_real", False):
        raise HTTPException(
            status_code=401,
            detail=(
                "Falha no liveness: a foto parece ser de outra foto/tela, não de uma "
                "pessoa ao vivo. Tire uma nova foto com a câmera, de frente e com boa luz."
            ),
        )


def _extrair_embedding(imagem) -> list[float]:
    DeepFace, _ = _carregar_deepface()
    try:
        representacoes = DeepFace.represent(
            img_path=imagem, model_name=MODEL_NAME, detector_backend=DETECTOR_BACKEND
        )
    except ValueError as erro:
        raise HTTPException(status_code=400, detail=f"Não foi possível processar a foto: {erro}")

    if len(representacoes) != 1:
        raise HTTPException(
            status_code=400,
            detail=f"A foto deve ter apenas 1 rosto (foram detectados {len(representacoes)}).",
        )
    return representacoes[0]["embedding"]


# Embedding fixo usado no modo de teste (BIOMETRIA_STUB) -- 128 dims, como o Facenet.
_EMBEDDING_STUB = [0.0] * 128


def cadastrar_biometria(imagem_base64: str) -> list[float]:
    """CRIAÇÃO DE CONTA: valida liveness e devolve o embedding em texto puro para
    o service cifrar e persistir. Nunca devolve/guarda a imagem."""
    if get_settings().biometria_stub:
        logger.warning("BIOMETRIA_STUB ligado -- cadastro NÃO verifica o rosto (modo de teste).")
        return list(_EMBEDDING_STUB)
    imagem = _decodificar_imagem(imagem_base64)
    _checar_liveness(imagem)
    return _extrair_embedding(imagem)


def verificar_biometria(imagem_base64: str, embedding_cadastrado: list[float]) -> dict:
    """TRANSFERÊNCIA (MFA): valida liveness da foto de agora e compara com o rosto
    cadastrado. Retorna {verificado, distancia, limite, confianca, modelo} em caso
    de sucesso; levanta HTTPException(401) genérica se não bater (o detalhe numérico
    vai só pro log/auditoria, não pro cliente -- item #3)."""
    if get_settings().biometria_stub:
        logger.warning("BIOMETRIA_STUB ligado -- transferência aprovada SEM conferir o rosto (modo de teste).")
        return {"verificado": True, "distancia": 0.0, "limite": 0.4, "confianca": 100.0, "modelo": "stub"}
    _, verification = _carregar_deepface()
    imagem = _decodificar_imagem(imagem_base64)
    _checar_liveness(imagem)
    embedding_atual = _extrair_embedding(imagem)

    limite = verification.find_threshold(model_name=MODEL_NAME, distance_metric=DISTANCE_METRIC)
    distancia = float(verification.find_distance(embedding_atual, embedding_cadastrado, DISTANCE_METRIC))
    verificado = distancia <= limite
    confianca = verification.find_confidence(distancia, MODEL_NAME, verificado, DISTANCE_METRIC)

    if not verificado:
        logger.info("MFA facial reprovado (distancia=%.4f limite=%.4f)", distancia, limite)
        raise HTTPException(
            status_code=401,
            detail="Rosto não corresponde ao titular da carteira de origem.",
        )

    return {
        "verificado": verificado,
        "distancia": round(distancia, 4),
        "limite": round(float(limite), 4),
        "confianca": round(float(confianca), 2),
        "modelo": MODEL_NAME,
    }
