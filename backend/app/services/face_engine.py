"""
Motor facial: detecção, anti-spoofing passivo e reconhecimento (template).

Interface única (`MotorFacial`) com dois backends, escolhidos por BIOMETRIA_MOTOR:

- "opencv" (padrão): YuNet (detector, 230 KB) + SFace (reconhecimento, 128-d,
  similaridade de cosseno) do OpenCV Zoo, e MiniFASNetV2 (anti-spoofing) rodando
  no próprio cv2.dnn. Tudo CPU, sem TensorFlow/PyTorch -- cabe num container
  pequeno no Azure e não tem os problemas de encoding do DeepFace no Windows.
- "deepface" (legado da v7): Facenet + MiniFASNet do DeepFace. Pesado; mantido
  só para quem já tem templates Facenet cadastrados.

A prova de vida ATIVA (piscar/sorrir/virar) fica em landmarks_service +
liveness_logic; o anti-spoofing aqui é a camada PASSIVA (foto/tela/máscara
impressa). Nenhuma das duas sozinha é suficiente -- juntas com o desafio do
servidor e o aparelho confiável é que formam a defesa.

Os objetos do OpenCV não são thread-safe: cada thread da API tem os seus
(threading.local). A concorrência total é limitada pelo semáforo do
biometria_service.
"""

from __future__ import annotations

import logging
import math
import threading
from dataclasses import dataclass

from fastapi import HTTPException

from app.core import modelos
from app.core.config import get_settings

logger = logging.getLogger("payflow.face")


@dataclass
class Rosto:
    x: float
    y: float
    w: float
    h: float
    score: float
    bruto: object = None  # linha do YuNet (15 valores) -- usada no alinhamento do SFace


def _cosseno(a: list[float], b: list[float]) -> float:
    if len(a) != len(b) or not a:
        return -1.0
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return -1.0
    return sum(x * y for x, y in zip(a, b)) / (na * nb)


class MotorFacial:
    nome = "base"

    @property
    def limiar(self) -> float:
        return get_settings().face_limiar_cosseno

    def rosto_unico(self, img, *, score_minimo: float = 0.85, minimo_px: int = 60) -> Rosto:  # pragma: no cover
        raise NotImplementedError

    def anti_spoof(self, img, rosto: Rosto) -> tuple[bool, float]:  # pragma: no cover
        raise NotImplementedError

    def embedding(self, img, rosto: Rosto) -> list[float]:  # pragma: no cover
        raise NotImplementedError

    def similaridade(self, a: list[float], b: list[float]) -> float:
        return _cosseno(a, b)


class MotorOpenCV(MotorFacial):
    nome = "sface"
    _local = threading.local()

    def _det(self):
        if getattr(self._local, "det", None) is None:
            import cv2

            self._local.det = cv2.FaceDetectorYN.create(modelos.caminho("yunet"), "", (320, 320), 0.6, 0.3, 50)
        return self._local.det

    def _rec(self):
        if getattr(self._local, "rec", None) is None:
            import cv2

            self._local.rec = cv2.FaceRecognizerSF.create(modelos.caminho("sface"), "")
        return self._local.rec

    def _spoof_net(self):
        if not hasattr(self._local, "spoof"):
            import cv2

            caminho = modelos.caminho("antispoof", obrigatorio=get_settings().em_producao)
            self._local.spoof = cv2.dnn.readNetFromONNX(caminho) if caminho else None
            if caminho is None:
                logger.warning("Modelo anti-spoofing indisponível -- camada passiva DESLIGADA (só em dev).")
        return self._local.spoof

    def detectar(self, img) -> list[Rosto]:
        h, w = img.shape[:2]
        det = self._det()
        det.setInputSize((w, h))
        _, faces = det.detect(img)
        if faces is None:
            return []
        return [Rosto(float(f[0]), float(f[1]), float(f[2]), float(f[3]), float(f[14]), f) for f in faces]

    def rosto_unico(self, img, *, score_minimo: float = 0.85, minimo_px: int = 60) -> Rosto:
        rostos = [r for r in self.detectar(img) if r.score >= score_minimo]
        if not rostos:
            raise HTTPException(status_code=400, detail="Não encontramos um rosto nítido. Aproxime o rosto e melhore a luz.")
        if len(rostos) > 1:
            raise HTTPException(status_code=400, detail="Há mais de um rosto na imagem. Fique sozinho(a) na câmera.")
        r = rostos[0]
        if min(r.w, r.h) < minimo_px:
            raise HTTPException(status_code=400, detail="Rosto muito pequeno na imagem. Aproxime a câmera.")
        return r

    def anti_spoof(self, img, rosto: Rosto) -> tuple[bool, float]:
        """MiniFASNetV2: crop quadrado 1.5x em volta do rosto, RGB, letterbox 128
        com reflexo, /255. Saída [real, spoof]; devolve (é_real, prob_real)."""
        net = self._spoof_net()
        if net is None:
            return True, 1.0
        import cv2
        import numpy as np

        rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        lado_rosto = max(rosto.w, rosto.h)
        cx, cy = rosto.x + rosto.w / 2, rosto.y + rosto.h / 2
        lado = int(lado_rosto * 1.5)
        x1, y1 = int(cx - lado / 2), int(cy - lado / 2)
        borda = lado  # reflete as bordas para o crop nunca sair da imagem
        ampliada = cv2.copyMakeBorder(rgb, borda, borda, borda, borda, cv2.BORDER_REFLECT_101)
        crop = ampliada[y1 + borda: y1 + borda + lado, x1 + borda: x1 + borda + lado]
        if crop.size == 0:
            return False, 0.0
        r = 128 / max(crop.shape[:2])
        crop = cv2.resize(crop, (max(1, int(crop.shape[1] * r)), max(1, int(crop.shape[0] * r))),
                          interpolation=cv2.INTER_AREA if r < 1 else cv2.INTER_LANCZOS4)
        dh, dw = 128 - crop.shape[0], 128 - crop.shape[1]
        crop = cv2.copyMakeBorder(crop, dh // 2, dh - dh // 2, dw // 2, dw - dw // 2, cv2.BORDER_REFLECT_101)
        blob = (crop.transpose(2, 0, 1).astype(np.float32) / 255.0)[None]
        net.setInput(blob)
        real, spoof = (float(x) for x in net.forward()[0][:2])
        prob_real = 1.0 / (1.0 + math.exp(-(real - spoof)))
        return prob_real >= get_settings().antispoof_limiar, prob_real

    def embedding(self, img, rosto: Rosto) -> list[float]:
        rec = self._rec()
        alinhado = rec.alignCrop(img, rosto.bruto)
        return [float(x) for x in rec.feature(alinhado).flatten()]


class MotorDeepFace(MotorFacial):
    """Legado (v7). Similaridade = 1 - distância de cosseno do Facenet."""

    nome = "facenet"

    @property
    def limiar(self) -> float:
        return 0.60  # 1 - 0.40 (limiar de cosseno do Facenet no DeepFace)

    @staticmethod
    def _df():
        from deepface import DeepFace

        return DeepFace

    def rosto_unico(self, img, *, score_minimo: float = 0.85, minimo_px: int = 60) -> Rosto:
        try:
            rostos = self._df().extract_faces(img_path=img, anti_spoofing=False, detector_backend="opencv")
        except ValueError:
            raise HTTPException(status_code=400, detail="Não encontramos um rosto nítido.")
        if len(rostos) != 1:
            raise HTTPException(status_code=400, detail="A imagem precisa ter exatamente 1 rosto.")
        a = rostos[0]["facial_area"]
        return Rosto(a["x"], a["y"], a["w"], a["h"], float(rostos[0].get("confidence", 1.0)))

    def anti_spoof(self, img, rosto: Rosto) -> tuple[bool, float]:
        r = self._df().extract_faces(img_path=img, anti_spoofing=True, detector_backend="opencv")
        real = bool(r and r[0].get("is_real"))
        return real, float(r[0].get("antispoof_score", 1.0 if real else 0.0)) if r else 0.0

    def embedding(self, img, rosto: Rosto) -> list[float]:
        reps = self._df().represent(img_path=img, model_name="Facenet", detector_backend="opencv")
        if len(reps) != 1:
            raise HTTPException(status_code=400, detail="A imagem precisa ter exatamente 1 rosto.")
        return reps[0]["embedding"]


_motores: dict[str, MotorFacial] = {}


def motor() -> MotorFacial:
    nome = get_settings().biometria_motor
    if nome not in _motores:
        _motores[nome] = MotorDeepFace() if nome == "deepface" else MotorOpenCV()
    return _motores[nome]
