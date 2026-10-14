from types import SimpleNamespace
import numpy as np
import pytest
from fastapi import HTTPException


@pytest.mark.parametrize("falha,esperado", [(None, None), ("frontal", 401), ("identidade", 401), ("sem_frontal", 400)])
def test_passivo_frontal_preserva_identidade_e_recusa(monkeypatch, falha, esperado):
    from app.services import biometria_service as b, qualidade_rosto as q
    imagens = [np.full((128, 128, 3), i, dtype=np.uint8) for i in range(6)]
    sinais = [SimpleNamespace(yaw=0.3 if i in (0, 3, 5) else 0, pontos=None) for i in range(6)]
    if falha == "sem_frontal":
        sinais[1].yaw = 0.3
    monkeypatch.setattr(b, "decodificar_imagem", lambda x: imagens[int(x)])
    monkeypatch.setattr(b.landmarks_service, "extrair", lambda x: sinais[int(x[0, 0, 0])])
    monkeypatch.setattr(b.liveness_logic, "verificar_sequencia", lambda *args: (True, ""))
    monkeypatch.setattr(b.liveness_logic, "melhores_frontais", lambda *args, **kw: [1, 2])
    monkeypatch.setattr(q, "medir", lambda *args: SimpleNamespace(oculos=0))
    monkeypatch.setattr(q, "problema", lambda *args, **kw: None)
    passivos = []

    class Motor:
        nome, limiar = "sface", 0.5
        def rosto_unico(self, *args, **kw):
            return SimpleNamespace(x=0, y=0, w=100, h=100)
        def anti_spoof(self, imagem, rosto):
            i = int(imagem[0, 0, 0])
            passivos.append(i)
            return (i in (1, 2) and falha != "frontal", 0.9)
        def embedding(self, imagem, rosto):
            return [int(imagem[0, 0, 0])]
        def similaridade(self, a, c):
            return 0 if falha == "identidade" and c == [3] else 1

    monkeypatch.setattr(b.face_engine, "motor", lambda: Motor())
    if esperado:
        with pytest.raises(HTTPException) as exc:
            b._analisar_sequencia([str(i) for i in range(6)], ("sorrir",))
        assert exc.value.status_code == esperado
    else:
        resultado = b._analisar_sequencia([str(i) for i in range(6)], ("sorrir",))
        assert len(resultado["templates"]) == 2
        assert passivos == [1, 2]
