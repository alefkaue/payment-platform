"""Imagens estreitas não podem causar uma ampliação gigantesca no OCR."""
import numpy as np
import pytest


@pytest.mark.parametrize("altura,largura", [(6000, 1), (6000, 10), (6000, 300), (3000, 1000)])
def test_redimensionamento_ocr_tem_orcamento(altura, largura, monkeypatch):
    import cv2
    from app.services import ocr_service
    original = cv2.resize
    tamanhos = []

    def limitado(img, tamanho, **kwargs):
        w, h = tamanho
        assert max(w, h) <= 2400
        assert w * h <= 4_000_000
        tamanhos.append(tamanho)
        return original(img, tamanho, **kwargs)

    monkeypatch.setattr(cv2, "resize", limitado)
    resultado = ocr_service._preprocessar(np.zeros((altura, largura, 3), dtype=np.uint8))
    assert tamanhos
    assert max(resultado.shape) <= 2400
    assert resultado.size <= 4_000_000


def test_ocr_imagem_comum_preserva_ampliacao():
    from app.services import ocr_service
    resultado = ocr_service._preprocessar(np.zeros((600, 800, 3), dtype=np.uint8))
    assert resultado.shape == (1200, 1600)
