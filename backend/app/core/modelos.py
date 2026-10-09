"""
Modelos de visão computacional usados pela biometria, com integridade fixada.

Cada arquivo tem URL de origem e SHA-256 conhecidos. Ao carregar, conferimos o
hash: um modelo trocado (cadeia de suprimentos, cache adulterado) NÃO é usado.

- Em produção os modelos vêm embutidos na imagem Docker (o Dockerfile roda
  `python -m app.core.modelos baixar`) e MODELOS_DOWNLOAD=0 -- o container nunca
  baixa nada em runtime.
- Em desenvolvimento são baixados uma vez para MODELOS_DIR (padrão
  ~/.cache/astro/modelos).

Licenças: YuNet e SFace (OpenCV Zoo, Apache-2.0 / MIT), Face Landmarker
(MediaPipe, Apache-2.0), MiniFASNetV2 anti-spoofing (suriAI/face-antispoof-onnx,
Apache-2.0).
"""

from __future__ import annotations

import hashlib
import logging
import os
import sys
import tempfile
import threading
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from fastapi import HTTPException

from app.core.config import get_settings

logger = logging.getLogger("payflow.modelos")


@dataclass(frozen=True)
class Modelo:
    arquivo: str
    url: str
    sha256: str
    tamanho_aprox: str


MODELOS: dict[str, Modelo] = {
    "yunet": Modelo(
        "face_detection_yunet_2023mar.onnx",
        "https://huggingface.co/opencv/opencv_zoo/resolve/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx",
        "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4",
        "230 KB",
    ),
    "sface": Modelo(
        "face_recognition_sface_2021dec.onnx",
        "https://huggingface.co/opencv/opencv_zoo/resolve/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx",
        "0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79",
        "37 MB",
    ),
    "antispoof": Modelo(
        "minifasv2_antispoof_98_20.onnx",
        "https://raw.githubusercontent.com/suriAI/face-antispoof-onnx/main/models/best/98.20/best_model.onnx",
        "af2381b88f38769222ed93379e12444e2a50814575de1c46170de570c55a42b6",
        "1.9 MB",
    ),
    "face_landmarker": Modelo(
        "face_landmarker.task",
        "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task",
        "64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff",
        "3.6 MB",
    ),
}

_lock = threading.Lock()
_verificados: dict[str, str] = {}


def pasta() -> Path:
    s = get_settings()
    p = Path(s.modelos_dir) if s.modelos_dir else Path.home() / ".cache" / "astro" / "modelos"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _sha256(caminho: Path) -> str:
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def _baixar(m: Modelo, destino: Path) -> None:
    logger.info("Baixando modelo %s (%s)...", m.arquivo, m.tamanho_aprox)
    fd, tmp = tempfile.mkstemp(dir=destino.parent, suffix=".parcial")
    os.close(fd)
    try:
        req = urllib.request.Request(m.url, headers={"User-Agent": "astro-backend"})
        with urllib.request.urlopen(req, timeout=60) as r, open(tmp, "wb") as f:  # noqa: S310 (URL fixa)
            while bloco := r.read(1 << 20):
                f.write(bloco)
        if _sha256(Path(tmp)) != m.sha256:
            raise RuntimeError(f"SHA-256 de {m.arquivo} não confere -- download recusado.")
        os.replace(tmp, destino)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def caminho(nome: str, *, obrigatorio: bool = True) -> str | None:
    """Caminho local do modelo, conferido por SHA-256. Baixa se permitido.
    obrigatorio=False devolve None quando indisponível (ex.: anti-spoof em dev)."""
    if nome in _verificados:
        return _verificados[nome]
    m = MODELOS[nome]
    destino = pasta() / m.arquivo
    with _lock:
        if nome in _verificados:
            return _verificados[nome]
        try:
            if not destino.exists():
                if not get_settings().modelos_download:
                    raise RuntimeError(f"Modelo {m.arquivo} ausente e MODELOS_DOWNLOAD=0.")
                _baixar(m, destino)
            if _sha256(destino) != m.sha256:
                raise RuntimeError(f"Modelo {m.arquivo} adulterado (SHA-256 diferente). Apague e baixe de novo.")
        except Exception as e:  # noqa: BLE001
            logger.error("Modelo %s indisponível: %s", nome, e)
            if obrigatorio:
                raise HTTPException(status_code=503, detail="Verificação facial indisponível neste servidor agora.") from e
            return None
        _verificados[nome] = str(destino)
        return _verificados[nome]


def baixar_todos() -> None:
    """Usado no build da imagem Docker: deixa todos os modelos prontos e conferidos."""
    for nome in MODELOS:
        print(f"{nome}: {caminho(nome)}")


if __name__ == "__main__":  # python -m app.core.modelos baixar
    if len(sys.argv) > 1 and sys.argv[1] == "baixar":
        baixar_todos()
    else:
        print("uso: python -m app.core.modelos baixar")
