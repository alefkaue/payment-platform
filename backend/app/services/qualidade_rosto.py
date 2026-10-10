"""
Qualidade do rosto na prova de vida: iluminação e óculos.

Puro (numpy + OpenCV), testável sem modelos. O app mostra a mesma orientação ao vivo
(app/src/lib/qualidade-rosto.ts), mas quem decide é o servidor.

Iluminação (rosto em tons de cinza):
- escuro: brilho médio do rosto abaixo de ROSTO_BRILHO_MIN;
- estourado: fração de pixels quase brancos acima de ROSTO_ESTOURADO_MAX;
- contraluz: o fundo muito mais claro que o rosto (janela atrás da pessoa).

Óculos (armação): a ponte entre as lentes é uma BARRA HORIZONTAL por cima do nariz, entre
os olhos. Mede a maior faixa contínua de bordas horizontais (Sobel com |gy| dominante)
nessa região, como fração da largura (0..1). Nariz de lado, sombra e fundo geram bordas
VERTICAIS e não contam. A versão anterior (densidade de bordas da ponte / da testa)
acusava óculos à toa: a testa lisa dá ~0 bordas e qualquer ruído na ponte estourava a
razão. Só é medido nos quadros mais frontais (biometria_service). Limiar configurável.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

# Pontos do FaceLandmarker (MediaPipe, 478 pontos).
_CANTO_INTERNO_ESQ, _CANTO_INTERNO_DIR = 133, 362
_ENTRE_OLHOS = 168


@dataclass
class Qualidade:
    brilho: float          # média 0..255 do rosto
    estourado: float       # fração do rosto quase branca (>= 245)
    contraluz: float       # brilho do fundo - brilho do rosto
    oculos: float          # 0..1: barra horizontal da armação na ponte (0 = sem dado)


def _cinza(imagem_bgr) -> np.ndarray:
    import cv2

    return cv2.cvtColor(imagem_bgr, cv2.COLOR_BGR2GRAY) if imagem_bgr.ndim == 3 else imagem_bgr


def _recorte(img: np.ndarray, x0: float, y0: float, x1: float, y1: float) -> np.ndarray:
    h, w = img.shape[:2]
    a, b = max(0, int(min(x0, x1))), min(w, int(max(x0, x1)))
    c, d = max(0, int(min(y0, y1))), min(h, int(max(y0, y1)))
    return img[c:d, a:b]


_BORDA_MIN = 100.0  # |gy| do Sobel 3x3 (0..1020) ~ contraste de 25 tons


def barra_horizontal(regiao: np.ndarray) -> float:
    """Maior faixa contínua de bordas horizontais (fração da largura). Uma coluna conta se
    alguma linha numa janela de 3 tem borda horizontal; tolera 1 pixel falhado."""
    import cv2

    if regiao.shape[0] < 5 or regiao.shape[1] < 6:
        return 0.0
    # Suaviza o ruído do sensor (pouca luz) sem apagar a armação (>= 2 px).
    f = cv2.GaussianBlur(regiao.astype(np.float32), (3, 3), 0)
    gx = cv2.Sobel(f, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(f, cv2.CV_32F, 0, 1, ksize=3)
    horiz = ((np.abs(gy) >= _BORDA_MIN) & (np.abs(gy) > 2 * np.abs(gx)))[1:-1, 1:-1]
    largura = horiz.shape[1]
    melhor = 0.0
    for r in range(horiz.shape[0]):
        cols = horiz[max(0, r - 1):r + 2].any(axis=0)
        corrida = falhas = maior = 0
        for tem in cols:
            if tem:
                corrida += 1 + falhas
                falhas = 0
                maior = max(maior, corrida)
            elif corrida and falhas < 1:
                falhas += 1
            else:
                corrida = falhas = 0
        melhor = max(melhor, maior / largura)
    return float(melhor)


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
    if pontos is not None and len(pontos) > max(_CANTO_INTERNO_DIR, _ENTRE_OLHOS):
        p = lambda i: (pontos[i].x * w, pontos[i].y * h)  # noqa: E731
        (ex, ey), (dx, dy) = p(_CANTO_INTERNO_ESQ), p(_CANTO_INTERNO_DIR)
        cx, cy = p(_ENTRE_OLHOS)
        dist = float(np.hypot(dx - ex, dy - ey))
        if dist >= 8:
            # +1 px de margem: o Sobel da borda da região usa os vizinhos de fora.
            regiao = _recorte(cinza, cx - 0.25 * dist - 1, cy - 0.2 * dist - 1,
                              cx + 0.25 * dist + 1, cy + 0.35 * dist + 1)
            oculos = barra_horizontal(regiao)
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
