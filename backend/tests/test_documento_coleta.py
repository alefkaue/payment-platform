from datetime import date
import pytest
from fastapi import HTTPException


def test_coleta_academica_nao_executa_ocr_ou_compara_rosto(monkeypatch):
    from app.services import documento_service as d
    from app.core.config import get_settings
    monkeypatch.setattr(get_settings(), "documento_verificar_identidade", False)
    monkeypatch.setattr(d.arquivos, "validar_arquivo", lambda *args, **kw: (b"imagem", "image/png", "hash"))
    monkeypatch.setattr(d, "_decodificar", lambda *args: object())
    def proibido(*args, **kw):
        pytest.fail("Coleta documental não deve executar verificação de identidade")
    monkeypatch.setattr(d.ocr_service, "provedor", proibido)
    resultado = d.analisar_documento_pessoa(tipo="rg", frente_b64="frente", verso_b64="verso",
        nome="Pessoa Teste", cpf="52998224725", data_nascimento=date(1990, 1, 1), template_selfie={"vetor": [1]})
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
