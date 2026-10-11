"""Inspeciona cabeçalhos antes de alocar pixels no decoder nativo."""
import io

from fastapi import HTTPException

MAX_PIXELS = 12_000_000
MAX_LADO = 6000


def conferir_dimensoes(bruto: bytes, *, minimo: int = 1) -> tuple[int, int]:
    from PIL import Image, UnidentifiedImageError

    try:
        # Image.open é lazy: identifica formato/dimensões sem carregar pixels.
        with Image.open(io.BytesIO(bruto), formats=["JPEG", "PNG", "WEBP"]) as img:
            w, h = img.size
            if w > MAX_LADO or h > MAX_LADO or w * h > MAX_PIXELS:
                raise HTTPException(status_code=413, detail="Resolução de imagem acima do limite permitido.")
            if min(w, h) < minimo:
                raise HTTPException(status_code=400, detail="Resolução de imagem fora do aceito.")
            return w, h
    except Image.DecompressionBombError:
        raise HTTPException(status_code=413, detail="Resolução de imagem acima do limite permitido.") from None
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError):
        raise HTTPException(status_code=400, detail="Imagem inválida ou corrompida.") from None
