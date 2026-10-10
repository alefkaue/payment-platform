"""
Qualidade do rosto na prova de vida: iluminação e óculos.

Puro (numpy + OpenCV), testável sem modelos. O app mostra a mesma orientação ao vivo
(app/src/lib/qualidade-rosto.ts), mas quem decide é o servidor.

Iluminação (rosto em tons de cinza):
- escuro: brilho médio do rosto abaixo de ROSTO_BRILHO_MIN;
- estourado: fração de pixels quase brancos acima de ROSTO_ESTOURADO_MAX;
- contraluz: o fundo muito mais claro que o rosto (janela atrás da pessoa).

Óculos (armação): a ponte entre as lentes passa por cima do nariz, entre os olhos. Mede a
densidade de bordas (Canny) nessa faixa, normalizada pela densidade da testa (que não
tem armação e serve de referência de nitidez/ruído da câmera). Pele lisa = pouca borda;
armação = linhas fortes. Os limiares são configuráveis (calibrar com aparelhos reais).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

# Pontos do FaceLandmarker (MediaPipe, 478 pontos).
_CANTO_INTERNO_ESQ, _CANTO_INTERNO_DIR = 133, 362
_ENTRE_OLHOS = 168
_TESTA = 10


@dataclass
class Qualidade:
    brilho: float          # média 0..255 do rosto
    estourado: float       # fração do rosto quase branca (>= 245)
    contraluz: float       # brilho do fundo - brilho do rosto
    oculos: float          # bordas na ponte do nariz / bordas na testa (0 = sem dado)


def _cinza(imagem_bgr) -> np.ndarray:
    import cv2

    return cv2.cvtColor(imagem_bgr, cv2.COLOR_BGR2GRAY) if imagem_bgr.ndim == 3 else imagem_bgr


def _recorte(img: np.ndarray, x0: float, y0: float, x1: float, y1: float) -> np.ndarray:
    h, w = img.shape[:2]
    a, b = max(0, int(min(x0, x1))), min(w, int(max(x0, x1)))
    c, d = max(0, int(min(y0, y1))), min(h, int(max(y0, y1)))
    return img[c:d, a:b]


def _densidade_bordas(regiao: np.ndarray) -> float:
    import cv2

    if regiao.size < 16:
        return 0.0
    bordas = cv2.Canny(regiao, 60, 140)
    return float(np.count_nonzero(bordas)) / bordas.size


def medir(imagem_bgr, caixa_rosto: tuple[int, int, int, int], pontos=None) -> Qualidade:
    """`caixa_rosto` = (x, y, largura, altura) em pixels. `pontos` = landmarks normalizados
    (objetos com .x/.y) do MediaPipe; sem eles, `oculos` fica 0 (não medido)."""
    cinza = _cinza(imagem_bgr)
    h, w = cinza.shape[:2]
    x, y, lw, lh = caixa_rosto
    rosto = _recorte(cinza, x, y, x + lw, y + lh)
    if rosto.size == 0:
        return Qualidade(brilho=0.0, estourado=0.0, contraluz=0.0, oculos=0.0)
    brilho = float(rosto.mean())
    estourado = float(np.count_nonzero(rosto >= 245)) / rosto.size
    mascara = np.ones_like(cinza, dtype=bool)
    mascara[max(0, y):max(0, y) + lh, max(0, x):max(0, x) + lw] = False
    fundo = float(cinza[mascara].mean()) if mascara.any() else brilho
    oculos = 0.0
    if pontos is not None and len(pontos) > max(_CANTO_INTERNO_DIR, _ENTRE_OLHOS, _TESTA):
        p = lambda i: (pontos[i].x * w, pontos[i].y * h)  # noqa: E731
        (ex, ey), (dx, dy) = p(_CANTO_INTERNO_ESQ), p(_CANTO_INTERNO_DIR)
        cx, cy = p(_ENTRE_OLHOS)
        tx, ty = p(_TESTA)
        meia = max(abs(dx - ex) * 0.35, 4.0)
        altura = max(abs(dx - ex) * 0.25, 4.0)
        ponte = _recorte(cinza, cx - meia, cy - altura, cx + meia, cy + altura)
        testa = _recorte(cinza, tx - meia, ty, tx + meia, ty + 2 * altura)
        d_ponte, d_testa = _densidade_bordas(ponte), _densidade_bordas(testa)
        oculos = d_ponte / max(d_testa, 0.01)
    return Qualidade(brilho=brilho, estourado=estourado, contraluz=fundo - brilho, oculos=oculos)


def problema(q: Qualidade, *, checar_oculos: bool) -> str | None:
    """Mensagem para a pessoa, ou None se a captura está boa."""
    from app.core.config import get_settings

    s = get_settings()
    if q.brilho < s.rosto_brilho_min:
        return "Está escuro: vá para um lugar com mais luz, de frente para a luz."
    if q.estourado > s.rosto_estourado_max:
        return "Luz forte demais no rosto: saia do sol direto ou afaste a lâmpada."
    if q.contraluz > s.rosto_contraluz_max:
        return "Há muita luz atrás de você: fique de costas para a janela ou para a lâmpada."
    if checar_oculos and q.oculos >= s.rosto_oculos_limiar:
        return "Tire os óculos para a verificação do rosto."
    return None
