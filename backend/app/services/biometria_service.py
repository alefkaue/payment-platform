"""
Serviço de biometria facial: liveness detection + reconhecimento facial via DeepFace
(https://github.com/serengil/deepface).

Por que DeepFace e não os outros repositórios enviados:
- Os projetos "Face-Recognition-System-using-DeepFace" e "Face-Recognition-Authentication"
  são, eles mesmos, aplicações de exemplo construídas sobre o DeepFace (ou sobre a lib
  `face_recognition`, baseada em dlib) -- ou seja, já apontam para o mesmo motor.
- O "Face-Liveness-Detection" e o pacote `liveness-detector` fariam SÓ a parte de
  liveness (geralmente por vídeo/blink detection), exigindo depois integrar uma segunda
  lib só para o reconhecimento facial em si.
- O DeepFace entrega os dois no mesmo lugar: reconhecimento facial (`represent`/`verify`)
  e anti-spoofing/liveness (`extract_faces(..., anti_spoofing=True)`), com um único
  modelo leve (MiniFASNet, ~4MB) para a parte de liveness. Para uma PLATAFORMA DE
  PAGAMENTO (não um banco), isso é o suficiente: 1 dependência, sem exigir vídeo/captura
  contínua, liveness por foto única (passiva).

Arquitetura de dados: guardamos o EMBEDDING do rosto (vetor de floats), nunca a foto de
cadastro em si. Assim, se o repositório em memória (ou, no futuro, o banco) for exposto,
não há uma foto para vazar -- só um vetor que não é reversível para uma imagem.

Trade-offs assumidos (documentados aqui para não ficarem escondidos):
- model_name="Facenet": ~92MB, embedding de 128 dimensões, roda bem em CPU. Troque para
  "Facenet512" ou "ArcFace" se precisar de mais acurácia (mais lento); para "SFace" ou
  "GhostFaceNet" se precisar de menos latência (menos acurácia).
- detector_backend="opencv": o detector mais rápido/leve (Haar Cascade, já vem no
  próprio opencv-python, sem download extra). Menos robusto a ângulo/iluminação ruins
  que "retinaface" ou "mtcnn" -- troque se isso for um problema real no seu ambiente.
- Cada chamada com um rosto custa ~3-6s em CPU (medido em teste local). Isso é
  aceitável para uma ação pontual (criar conta, autorizar 1 transferência), mas é
  bloqueante: o request FastAPI fica parado esperando o modelo rodar. Para volume
  maior, isso pediria fila/async (fora de escopo do MVP de sexta).
"""

import base64
import binascii
import re

import cv2
import numpy as np
from deepface import DeepFace
from deepface.modules import verification
from fastapi import HTTPException

MODEL_NAME = "Facenet"
DETECTOR_BACKEND = "opencv"
DISTANCE_METRIC = "cosine"

_DATA_URI_RE = re.compile(r"^data:image/\w+;base64,")


def _decodificar_imagem(imagem_base64: str) -> np.ndarray:
    """Converte a string base64 vinda do front (com ou sem prefixo `data:image/...`)
    em uma imagem BGR (formato que o OpenCV/DeepFace esperam)."""
    if not imagem_base64 or not imagem_base64.strip():
        raise HTTPException(status_code=400, detail="Nenhuma foto foi enviada.")

    conteudo = _DATA_URI_RE.sub("", imagem_base64.strip())
    try:
        bytes_imagem = base64.b64decode(conteudo, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(status_code=400, detail="Foto inválida: base64 corrompido.")

    array = np.frombuffer(bytes_imagem, dtype=np.uint8)
    imagem = cv2.imdecode(array, cv2.IMREAD_COLOR)
    if imagem is None:
        raise HTTPException(
            status_code=400, detail="Foto inválida: não foi possível decodificar a imagem."
        )
    return imagem


def _checar_liveness(imagem: np.ndarray) -> None:
    """Levanta HTTPException se não houver exatamente 1 rosto real na imagem.
    'Real' = passou no anti-spoofing (não é foto de foto, nem de tela)."""
    try:
        rostos = DeepFace.extract_faces(
            img_path=imagem, anti_spoofing=True, detector_backend=DETECTOR_BACKEND
        )
    except ValueError as erro:
        # DeepFace usa ValueError tanto para "nenhum rosto encontrado" quanto para
        # outros problemas de decodificação -- todos viram 400 aqui.
        raise HTTPException(status_code=400, detail=f"Não foi possível processar a foto: {erro}")

    if len(rostos) == 0:
        raise HTTPException(status_code=400, detail="Nenhum rosto detectado na foto.")
    if len(rostos) > 1:
        raise HTTPException(
            status_code=400,
            detail=f"A foto deve ter apenas 1 rosto (foram detectados {len(rostos)}).",
        )

    rosto = rostos[0]
    if not rosto.get("is_real", False):
        raise HTTPException(
            status_code=401,
            detail=(
                "Falha no liveness: a foto parece ser de outra foto/tela, não de uma "
                "pessoa ao vivo. Tire uma nova foto com a câmera, de frente e com boa luz."
            ),
        )


def _extrair_embedding(imagem: np.ndarray) -> list[float]:
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


def cadastrar_biometria(imagem_base64: str) -> list[float]:
    """Usado na CRIAÇÃO DE CONTA. Valida liveness e devolve o embedding facial para o
    service de usuário persistir junto com a carteira."""
    imagem = _decodificar_imagem(imagem_base64)
    _checar_liveness(imagem)
    return _extrair_embedding(imagem)


def verificar_biometria(imagem_base64: str, embedding_cadastrado: list[float]) -> dict:
    """Usado na TRANSFERÊNCIA (MFA). Valida liveness da foto tirada agora e compara o
    rosto com o embedding cadastrado na carteira de origem.

    Retorna um dict {verificado, distancia, limite, confianca, modelo} -- levanta
    HTTPException (401) se liveness falhar ou o rosto não corresponder.
    """
    imagem = _decodificar_imagem(imagem_base64)
    _checar_liveness(imagem)
    embedding_atual = _extrair_embedding(imagem)

    limite = verification.find_threshold(model_name=MODEL_NAME, distance_metric=DISTANCE_METRIC)
    distancia = float(
        verification.find_distance(embedding_atual, embedding_cadastrado, DISTANCE_METRIC)
    )
    verificado = distancia <= limite
    confianca = verification.find_confidence(distancia, MODEL_NAME, verificado, DISTANCE_METRIC)

    if not verificado:
        raise HTTPException(
            status_code=401,
            detail=(
                "Rosto não corresponde ao titular da carteira de origem "
                f"(distância {distancia:.3f}, limite {limite})."
            ),
        )

    return {
        "verificado": verificado,
        "distancia": round(distancia, 4),
        "limite": limite,
        "confianca": confianca,
        "modelo": MODEL_NAME,
    }
