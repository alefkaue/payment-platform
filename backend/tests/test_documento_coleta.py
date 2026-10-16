from datetime import date
import pytest
from fastapi import HTTPException


def test_coleta_academica_nao_confere_a_pessoa(monkeypatch):
    # Desde 15/10/2026 a coleta confere que a imagem É um documento (documento_forma),
    # mas continua sem conferir QUEM é a pessoa: CPF, nome e rosto não são comparados.
    from app.services import documento_service as d
    from app.services.documento_forma import Evidencias
    from app.core.config import get_settings
    monkeypatch.setattr(get_settings(), "documento_verificar_identidade", False)
    monkeypatch.setattr(d.arquivos, "validar_arquivo", lambda *args, **kw: (b"imagem", "image/png", "hash"))
    monkeypatch.setattr(d, "_decodificar", lambda *args: object())
    monkeypatch.setattr(d.ocr_service, "provedor", lambda: "tesseract")
    conferidas = []
    monkeypatch.setattr(d.documento_forma, "conferir", lambda imgs, prov: conferidas.append(len(imgs)) or Evidencias(texto=""))
    def proibido(*args, **kw):
        pytest.fail("Coleta documental não deve conferir a identidade da pessoa")
    monkeypatch.setattr(d.ocr_service, "encontrar_cpfs", proibido)
    monkeypatch.setattr(d.ocr_service, "nome_confere", proibido)
    resultado = d.analisar_documento_pessoa(tipo="rg", frente_b64="frente", verso_b64="verso",
        nome="Pessoa Teste", cpf="52998224725", data_nascimento=date(1990, 1, 1), template_selfie={"vetor": [1]})
    assert conferidas == [2]
    assert resultado["provedor"] == "coleta_academica"
    assert resultado["status"] == "em_analise"
    assert resultado["verificacoes"]["rosto"] == "nao_comparado"


def test_coleta_continua_rejeitando_arquivo_invalido(monkeypatch):
    from app.services import documento_service as d
    from app.core.config import get_settings
    monkeypatch.setattr(get_settings(), "documento_verificar_identidade", False)
    def invalido(*args, **kw):
        raise HTTPException(400, "Arquivo inválido")
    monkeypatch.setattr(d.arquivos, "validar_arquivo", invalido)
    with pytest.raises(HTTPException) as exc:
        d.analisar_documento_pessoa(tipo="passaporte", frente_b64="inválido", verso_b64=None,
            nome="Pessoa Teste", cpf="52998224725", data_nascimento=None, template_selfie=None)
    assert exc.value.status_code == 400
