"""Piscar calibrado pelo olho aberto da pessoa (revisão de 15/10/2026)."""
from app.services import liveness_logic as L
from app.services.landmarks_service import SinaisQuadro


def _serie(blinks, yaw=0.0):
    return [SinaisQuadro(tem_rosto=True, ear=0.3, blink=b, yaw=yaw) for b in blinks]


def _piscadas(base, pico, n, abertos=4, fechados=2):
    serie = [base] * abertos
    for _ in range(n):
        serie += [pico] * fechados + [base] * abertos
    return serie


def test_olho_aberto_alto_ainda_conta_piscadas():
    # Olhando para baixo / olhos mais fechados: aberto em 0.34 (antes nunca "reabria").
    assert L.piscadas_da_serie(_serie(_piscadas(0.34, 0.85, 3))) == 3


def test_olho_aberto_normal_continua_igual():
    assert L.piscadas_da_serie(_serie(_piscadas(0.05, 0.7, 2))) == 2


def test_tremor_pequeno_nao_vira_piscada():
    tremor = [0.30, 0.38, 0.31, 0.40, 0.33, 0.39, 0.30, 0.37] * 3
    assert L.piscadas_da_serie(_serie(tremor)) == 0


def test_rosto_virado_nao_conta_piscada():
    assert L.piscadas_da_serie(_serie(_piscadas(0.05, 0.7, 2), yaw=0.3)) == 0


def test_limiares_nunca_mais_rigidos_que_os_fixos():
    fechado, aberto = L.limiares_piscada([0.0] * 10)
    assert fechado <= L.BLINK_FECHADO and aberto >= L.BLINK_ABERTO
    fechado, aberto = L.limiares_piscada([0.34] * 10)
    assert fechado - aberto >= 0.1


def test_passo_piscar3_aceita_olho_aberto_alto():
    ok, motivo = L._checar_passo(_serie(_piscadas(0.32, 0.8, 3)), "piscar3")
    assert ok, motivo
