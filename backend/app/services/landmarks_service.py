"""
Sinais de rosto por quadro, extraídos com o MediaPipe Face Landmarker (468
pontos + blendshapes). É o que torna a prova de vida *de verdade*: em vez de
olhar só dois pontos de olho (o que a DeepFace devolve), aqui medimos, para cada
quadro:

- EAR (Eye Aspect Ratio) de cada olho -> cai quando a pálpebra fecha (piscar);
- MAR (Mouth Aspect Ratio) + blendshape jawOpen -> boca aberta;
- blendshape mouthSmile -> sorriso;
- yaw (nariz em relação ao meio das bochechas / largura do rosto) -> giro;
- se EXISTE um rosto no quadro (sem isso, biometria_service recusa a prova --
  fecha o buraco de "aprova até sem rosto").

Quem decide se a AÇÃO aconteceu (transição aberto->fechado->aberto etc.) é o
biometria_service, de forma temporal e com histerese. Aqui só extraímos números.

Índices do Face Mesh (EAR de 6 pontos por olho, fórmula de Soukupová & Čech 2016):
- olho esquerdo:  362 385 387 263 373 380
- olho direito:    33 160 158 133 153 144
Boca (MAR): abertura 13/14, cantos 61/291. Giro: nariz 1, bochechas 234/454.

O modelo (.task) vem do registro core/modelos (SHA-256 conferido). Import e
download são preguiçosos: a API e os testes sobem sem MediaPipe (modo stub). Se o
pacote faltar no modo real, devolvemos 503 com um recado claro.
"""

from __future__ import annotations

import logging
import math
import threading
from dataclasses import dataclass

from fastapi import HTTPException

from app.core import modelos

logger = logging.getLogger("payflow.landmarks")

# Seis pontos por olho, na ordem p1..p6 da fórmula do EAR.
_OLHO_ESQ = (362, 385, 387, 263, 373, 380)
_OLHO_DIR = (33, 160, 158, 133, 153, 144)
# Boca: abertura (lábio sup./inf.) e cantos.
_BOCA_V = (13, 14)
_BOCA_H = (61, 291)
# Giro: ponta do nariz e bochechas (mesmos pontos usados no guia do app).
_NARIZ = 1
_BOCHECHA_ESQ = 234
_BOCHECHA_DIR = 454


@dataclass
class SinaisQuadro:
    """Medidas de um quadro. `tem_rosto` falso = nenhum rosto detectado."""

    tem_rosto: bool
    ear: float = 0.0        # média dos dois olhos (menor = olho mais fechado)
    mar: float = 0.0        # abertura da boca / largura
    jaw_open: float = 0.0   # blendshape jawOpen (0..1)
    blink: float = 0.0      # max(eyeBlinkLeft, eyeBlinkRight) (0..1)
    smile: float = 0.0      # média mouthSmileLeft/Right (0..1)
    yaw: float = 0.0        # >0 nariz à direita da imagem (sem espelho)


_local = threading.local()


def _obter_landmarker():
    """Um FaceLandmarker por thread (IMAGE mode, 1 rosto, com blendshapes)."""
    lm = getattr(_local, "landmarker", None)
    if lm is not None:
        return lm
    try:
        from mediapipe.tasks import python as mp_python
        from mediapipe.tasks.python import vision
    except ImportError as e:  # pragma: no cover - ambiente sem mediapipe
        raise HTTPException(
            status_code=503,
            detail="Verificador facial indisponível neste servidor (MediaPipe não instalado).",
        ) from e
    opcoes = vision.FaceLandmarkerOptions(
        base_options=mp_python.BaseOptions(model_asset_path=modelos.caminho("face_landmarker")),
        running_mode=vision.RunningMode.IMAGE,
        num_faces=1,
        output_face_blendshapes=True,
        min_face_detection_confidence=0.5,
        min_face_presence_confidence=0.5,
    )
    _local.landmarker = vision.FaceLandmarker.create_from_options(opcoes)
    return _local.landmarker


def _dist(a, b) -> float:
    return math.hypot(a.x - b.x, a.y - b.y)


def _ear(pontos, idx) -> float:
    p1, p2, p3, p4, p5, p6 = (pontos[i] for i in idx)
    horizontal = _dist(p1, p4)
    if horizontal <= 1e-6:
        return 0.0
    return (_dist(p2, p6) + _dist(p3, p5)) / (2.0 * horizontal)


def _blendshape(cats, nome: str) -> float:
    for c in cats:
        if c.category_name == nome:
            return float(c.score)
    return 0.0


def extrair(imagem_rgb) -> SinaisQuadro:
    """Extrai os sinais de UM quadro (ndarray RGB). Não levanta se não achar
    rosto -- devolve tem_rosto=False para o chamador decidir."""
    import mediapipe as mp

    landmarker = _obter_landmarker()
    mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=imagem_rgb)
    r = landmarker.detect(mp_img)
    if not r.face_landmarks:
        return SinaisQuadro(tem_rosto=False)
    pts = r.face_landmarks[0]
    cats = r.face_blendshapes[0] if r.face_blendshapes else []

    ear = (_ear(pts, _OLHO_ESQ) + _ear(pts, _OLHO_DIR)) / 2.0
    larg_boca = _dist(pts[_BOCA_H[0]], pts[_BOCA_H[1]])
    mar = _dist(pts[_BOCA_V[0]], pts[_BOCA_V[1]]) / larg_boca if larg_boca > 1e-6 else 0.0
    nariz, be, bd = pts[_NARIZ], pts[_BOCHECHA_ESQ], pts[_BOCHECHA_DIR]
    larg_rosto = abs(bd.x - be.x) or 1.0
    yaw = (nariz.x - (be.x + bd.x) / 2.0) / larg_rosto

    return SinaisQuadro(
        tem_rosto=True,
        ear=ear,
        mar=mar,
        jaw_open=_blendshape(cats, "jawOpen"),
        blink=max(_blendshape(cats, "eyeBlinkLeft"), _blendshape(cats, "eyeBlinkRight")),
        smile=(_blendshape(cats, "mouthSmileLeft") + _blendshape(cats, "mouthSmileRight")) / 2.0,
        yaw=yaw,
    )
