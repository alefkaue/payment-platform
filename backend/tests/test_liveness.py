"""
Testes das regras de prova de vida (liveness_logic) -- funções puras, sem câmera
nem IA. Montamos séries de SinaisQuadro na mão e conferimos que cada MODO só passa
com toda a sua sequência (cadastro: piscar 3x + sorrir + virar p/ os 2 lados;
login: piscar 3x), e nunca com rosto ausente em algum quadro.
"""

from app.services.landmarks_service import SinaisQuadro
from app.services import liveness_logic as L


def q(ear: float = 0.30, smile: float = 0.0, yaw: float = 0.0, rosto: bool = True) -> SinaisQuadro:
    return SinaisQuadro(tem_rosto=rosto, ear=ear, smile=smile, yaw=yaw)


# Trechos reaproveitáveis (cada um exercita um passo).
PISCAR3 = [q(0.30), q(0.10), q(0.30), q(0.10), q(0.30), q(0.10), q(0.30)]  # 3 piscadas
SORRIR = [q(smile=0.05), q(smile=0.60)]
VIRAR_ESQ = [q(yaw=0.0), q(yaw=0.30), q(yaw=0.30)]   # frontal + giro forte > 0.22
VIRAR_DIR = [q(yaw=0.0), q(yaw=-0.30), q(yaw=-0.30)]
CADASTRO = PISCAR3 + SORRIR + VIRAR_ESQ + VIRAR_DIR


def test_contar_piscadas_conta_a_transicao():
    assert L.contar_piscadas([0.30, 0.10, 0.30, 0.10, 0.30, 0.10, 0.30]) == 3
    assert L.contar_piscadas([0.30, 0.29, 0.31]) == 0
    assert L.contar_piscadas([0.30, 0.10, 0.10, 0.12]) == 0  # fechou e não reabriu


def test_login_exige_3_piscadas():
    assert L.verificar_sequencia(PISCAR3, "login")[0] is True
    # só 1 piscada não basta
    uma = [q(0.30), q(0.10), q(0.30), q(0.30), q(0.30), q(0.30)]
    ok, motivo = L.verificar_sequencia(uma, "login")
    assert ok is False and "3" in motivo


def test_cadastro_completo_passa():
    assert L.verificar_sequencia(CADASTRO, "cadastro")[0] is True


def test_cadastro_reprova_se_faltar_um_passo():
    # sem a virada para a direita
    seq = PISCAR3 + SORRIR + VIRAR_ESQ
    ok, motivo = L.verificar_sequencia(seq, "cadastro")
    assert ok is False and "direita" in motivo.lower()
    # sem sorrir
    ok2, motivo2 = L.verificar_sequencia(PISCAR3 + VIRAR_ESQ + VIRAR_DIR, "cadastro")
    assert ok2 is False and "sorriso" in motivo2.lower()


def test_rosto_ausente_em_qualquer_quadro_reprova():
    seq = list(PISCAR3)
    seq[2] = q(rosto=False)
    ok, motivo = L.verificar_sequencia(seq, "login")
    assert ok is False and "rosto" in motivo.lower()


def test_virar_melhorado_rejeita_giro_leve():
    # giro leve (0.15 < YAW_GIRO 0.22) não conta como virada -> o gingado leve
    # que passava antes agora falha.
    leve = PISCAR3 + SORRIR + [q(yaw=0.0), q(yaw=0.15), q(yaw=0.15)] + VIRAR_DIR
    ok, motivo = L.verificar_sequencia(leve, "cadastro")
    assert ok is False and "esquerda" in motivo.lower()
    # um único quadro forte não basta (exige GIRO_QUADROS >= 2)
    um_so = PISCAR3 + SORRIR + [q(yaw=0.0), q(yaw=0.30)] + VIRAR_DIR
    assert L.verificar_sequencia(um_so, "cadastro")[0] is False


def test_passos_do_modo():
    ids = [p["id"] for p in L.passos_do_modo("cadastro")]
    assert ids == ["piscar3", "sorrir", "virar_esquerda", "virar_direita"]
    assert [p["id"] for p in L.passos_do_modo("login")] == ["piscar3"]
    assert L.passos_do_modo("inexistente") == []


def test_modo_desconhecido_reprova():
    assert L.verificar_sequencia(CADASTRO, "xpto")[0] is False


def test_melhores_frontais_prefere_olhos_abertos_e_frontal():
    seq = [q(ear=0.30, yaw=0.30), q(ear=0.30, yaw=0.01), q(ear=0.05, yaw=0.0), q(rosto=False)]
    idxs = L.melhores_frontais(seq, n=2)
    assert idxs[0] == 1 and 3 not in idxs
