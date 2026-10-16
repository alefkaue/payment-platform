"""A foto enviada precisa SER um documento de identidade (sem conferir a pessoa)."""
import numpy as np
import pytest
from fastapi import HTTPException

from app.services import documento_forma as f


def _vazia(cor=200):
    return np.full((400, 600, 3), cor, dtype=np.uint8)


def _com_conteudo():
    import cv2
    img = np.full((400, 600, 3), 235, dtype=np.uint8)
    cv2.rectangle(img, (30, 30), (570, 370), (40, 40, 40), 2)
    cv2.rectangle(img, (50, 80), (190, 260), (90, 90, 90), -1)
    for i, linha in enumerate(("LINHA UM 1234", "OUTRA LINHA 5678", "TEXTO QUALQUER", "MAIS 0000")):
        cv2.putText(img, linha, (220, 110 + 50 * i), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (20, 20, 20), 2)
    return img


@pytest.fixture
def sinais(monkeypatch):
    estado = {"texto": "", "qr": [], "rosto": False}
    monkeypatch.setattr(f.ocr_service, "extrair_texto", lambda img: estado["texto"])
    monkeypatch.setattr(f.ocr_service, "ler_qr", lambda img: estado["qr"])
    monkeypatch.setattr(f, "_rosto_impresso", lambda imgs: estado["rosto"])
    return estado


@pytest.mark.parametrize("cor", [0, 128, 255])
def test_foto_sem_conteudo_e_recusada(sinais, cor):
    with pytest.raises(HTTPException) as exc:
        f.conferir([_vazia(cor)], "tesseract")
    assert exc.value.status_code == 400 and "vazia" in exc.value.detail


def test_verso_vazio_tambem_e_recusado(sinais):
    sinais["texto"] = "REPUBLICA FEDERATIVA DO BRASIL CARTEIRA DE IDENTIDADE"
    with pytest.raises(HTTPException):
        f.conferir([_com_conteudo(), _vazia()], "tesseract")


def test_imagem_qualquer_sem_sinais_de_documento_e_recusada(sinais):
    sinais["texto"] = "promoção imperdível hoje"
    with pytest.raises(HTTPException) as exc:
        f.conferir([_com_conteudo()], "tesseract")
    assert "documento de identidade" in exc.value.detail


def test_selfie_com_rosto_mas_sem_texto_de_documento_e_recusada(sinais):
    sinais["rosto"] = True
    sinais["texto"] = "oi"
    with pytest.raises(HTTPException):
        f.conferir([_com_conteudo()], "tesseract")


def test_rg_com_textos_impressos_passa(sinais):
    sinais["texto"] = "REPÚBLICA FEDERATIVA DO BRASIL\nCARTEIRA DE IDENTIDADE\nNOME\nFILIAÇÃO"
    ev = f.conferir([_com_conteudo(), _com_conteudo()], "tesseract")
    assert ev.pontos >= f.PONTOS_SO_TEXTO
    assert "CARTEIRA DE IDENTIDADE" in ev.termos


def test_ocr_parcial_com_foto_3x4_passa(sinais):
    sinais["texto"] = "HABILITACAO  x1z"
    sinais["rosto"] = True
    assert f.conferir([_com_conteudo()], "tesseract").rosto_impresso


def test_qr_code_de_documento_passa(sinais):
    sinais["qr"] = ["https://exemplo.gov.br/validar"]
    assert f.conferir([_com_conteudo()], "tesseract").qr


def test_sem_ocr_exige_foto_3x4(sinais):
    with pytest.raises(HTTPException):
        f.conferir([_com_conteudo()], "sem_ocr")
    sinais["rosto"] = True
    f.conferir([_com_conteudo()], "sem_ocr")


def test_ocr_que_falha_nao_derruba_e_cai_na_regra_sem_ocr(monkeypatch, sinais):
    def quebra(img):
        raise RuntimeError("tesseract caiu")
    monkeypatch.setattr(f.ocr_service, "extrair_texto", quebra)
    sinais["rosto"] = True
    assert f.conferir([_com_conteudo()], "tesseract").texto is None


def test_pontuacao_do_texto():
    pontos, termos = f.pontuar_texto("CARTEIRA NACIONAL DE HABILITAÇÃO  CPF 529.982.247-25  VALIDADE 01/02/2030")
    assert "HABILITACAO" in termos and "formato_cpf" in termos and "formato_data" in termos
    assert pontos >= 6
    assert f.pontuar_texto("bom dia, tudo bem?")[0] == 0
