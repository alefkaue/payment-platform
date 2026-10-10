"""Qualidade da captura: luz e óculos (app/services/qualidade_rosto.py), com imagens sintéticas."""

from types import SimpleNamespace

import numpy as np
import pytest

from app.services import qualidade_rosto as q

CAIXA = (60, 40, 120, 160)  # x, y, w, h do rosto numa imagem 240x240


def _pontos():
    """478 landmarks normalizados; só os usados pela checagem de óculos importam."""
    pts = [SimpleNamespace(x=0.5, y=0.5) for _ in range(478)]
    pts[133] = SimpleNamespace(x=100 / 240, y=100 / 240)   # canto interno do olho esquerdo
    pts[362] = SimpleNamespace(x=140 / 240, y=100 / 240)   # canto interno do olho direito
    pts[168] = SimpleNamespace(x=120 / 240, y=100 / 240)   # entre os olhos
    pts[10] = SimpleNamespace(x=120 / 240, y=55 / 240)     # testa
    return pts


def _imagem(rosto=140, fundo=120, ruido=4, seed=1):
    rng = np.random.default_rng(seed)
    img = np.full((240, 240), fundo, dtype=np.float32)
    x, y, w, h = CAIXA
    img[y:y + h, x:x + w] = rosto
    img += rng.normal(0, ruido, img.shape)
    return np.clip(img, 0, 255).astype(np.uint8)


def _com_oculos(img):
    out = img.copy()
    out[96:100, 104:136] = 20     # ponte da armação
    out[86:114, 102:105] = 20     # aro esquerdo (lado de dentro)
    out[86:114, 135:138] = 20     # aro direito (lado de dentro)
    return out


def test_boa_captura_passa():
    med = q.medir(_imagem(), CAIXA, _pontos())
    assert q.problema(med, checar_oculos=True) is None


@pytest.mark.parametrize(("img", "trecho"), [
    (_imagem(rosto=30, fundo=25), "escuro"),
    (_imagem(rosto=252, fundo=200, ruido=1), "Luz forte"),
    (_imagem(rosto=90, fundo=235), "atrás de você"),
])
def test_luz_ruim_orienta(img, trecho):
    assert trecho in q.problema(q.medir(img, CAIXA, _pontos()), checar_oculos=False)


def test_oculos_detectados_so_quando_pedido():
    med = q.medir(_com_oculos(_imagem()), CAIXA, _pontos())
    assert "óculos" in q.problema(med, checar_oculos=True)
    assert q.problema(med, checar_oculos=False) is None  # login aceita óculos


def test_sem_landmarks_nao_inventa_oculos():
    med = q.medir(_com_oculos(_imagem()), CAIXA, None)
    assert med.oculos == 0 and q.problema(med, checar_oculos=True) is None


def test_mesmo_documento_nao_abre_segunda_conta(cliente, monkeypatch):
    """Uma conta por documento: as mesmas imagens de RG não abrem outra conta (resposta genérica)."""
    from app.core import config
    from tests.helpers import SENHA, gerar_cpf, prova_cadastro
    from tests.test_v9_seguranca import _cadastro_com_documento, _png

    monkeypatch.setattr(config.get_settings(), "kyc_documento_obrigatorio", True)
    documento = {"tipo": "rg", "frente": _png(), "verso": _png(130)}
    primeira = _cadastro_com_documento(cliente, cpf=gerar_cpf(), documento=documento)
    assert primeira.status_code == 201, primeira.text
    r = cliente.post("/usuarios", headers={"X-Dispositivo-Id": "outro-cel"}, json={
        "nome": "Outra Pessoa Silva", "email": "outra.doc@ex.com", "senha": SENHA, "cpf": gerar_cpf(),
        "data_nascimento": "1991-02-03", "celular": "11987654322", "biometria": prova_cadastro(cliente),
        "documento": documento})
    assert r.status_code == 409, r.text
