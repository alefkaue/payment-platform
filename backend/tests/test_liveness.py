"""
Testes das regras de prova de vida (liveness_logic) -- funções puras, sem câmera
nem IA. Montamos séries de SinaisQuadro na mão.

O desafio é SORTEADO pelo servidor. Desde 26/10/2026 a prova de vida é facilitada:
cadastro com 2 ações, login com 1, cada passo só precisa aparecer na gravação (a ordem
e movimentos naturais fora do passo não reprovam). Uma gravação que não mostra a ação
pedida continua reprovando.
"""

import random

from app.services.landmarks_service import SinaisQuadro
from app.services import liveness_logic as L


def q(ear: float = 0.30, smile: float = 0.0, yaw: float = 0.0, rosto: bool = True) -> SinaisQuadro:
    return SinaisQuadro(tem_rosto=rosto, ear=ear, smile=smile, yaw=yaw)


# Trechos reaproveitáveis (cada um exercita um passo, começando e terminando neutro).
PISCAR2 = [q(0.30), q(0.10), q(0.30), q(0.10), q(0.30)]
PISCAR3 = [q(0.30), q(0.10), q(0.30), q(0.10), q(0.30), q(0.10), q(0.30)]
SORRIR = [q(smile=0.05), q(smile=0.60), q(smile=0.05)]
VIRAR_ESQ = [q(yaw=0.0), q(yaw=0.30), q(yaw=0.30), q(yaw=0.0)]   # frontal + giro forte > 0.22
VIRAR_DIR = [q(yaw=0.0), q(yaw=-0.30), q(yaw=-0.30), q(yaw=0.0)]
TRECHO = {"piscar2": PISCAR2, "piscar3": PISCAR3, "sorrir": SORRIR,
          "virar_esquerda": VIRAR_ESQ, "virar_direita": VIRAR_DIR}
NEUTRO = [q(), q(), q()]


def gravar(passos) -> list[SinaisQuadro]:
    """Série de quem fez exatamente os passos pedidos, na ordem."""
    seq = list(NEUTRO)
    for p in passos:
        seq += TRECHO[p]
    return seq


def test_contar_piscadas_conta_a_transicao():
    assert L.contar_piscadas([0.30, 0.10, 0.30, 0.10, 0.30, 0.10, 0.30]) == 3
    assert L.contar_piscadas([0.30, 0.29, 0.31]) == 0
    assert L.contar_piscadas([0.30, 0.10, 0.10, 0.12]) == 0  # fechou e não reabriu


def test_sorteio_de_login_e_cadastro():
    rng = random.Random(7)
    vistos = set()
    for _ in range(200):
        login = L.sortear_passos("login", rng)
        assert len(login) == 1 and login[0] in L.PASSOS_VALIDOS
        assert login[0] != "piscar3"
        cad = L.sortear_passos("cadastro", rng)
        assert len(cad) == 2 and len(set(cad)) == 2
        assert all(p in L.PASSOS_VALIDOS and p != "piscar3" for p in cad)
        vistos.add(cad)
    # 4 ações, 2 na ordem: 12 combinações possíveis
    assert len(vistos) >= 10


def test_codificar_e_decodificar():
    passos = ("sorrir", "piscar2")
    assert L.decodificar(L.codificar("login", passos)) == ("login", passos)
    # formato antigo (só o modo): passos fixos de antes
    assert L.decodificar("login") == ("login", ("piscar3",))
    # passo inventado não vale
    assert L.decodificar("login:voar") == ("login", ())


def test_quem_faz_o_que_foi_pedido_passa():
    rng = random.Random(1)
    for modo in ("login", "cadastro"):
        for _ in range(30):
            passos = L.sortear_passos(modo, rng)
            ok, motivo = L.verificar_sequencia(gravar(passos), passos)
            assert ok, (passos, motivo)


def test_fora_de_ordem_passa():
    passos = ("sorrir", "virar_esquerda")
    assert L.verificar_sequencia(gravar(("virar_esquerda", "sorrir")), passos) == (True, "")


def test_gravacao_sem_a_acao_pedida_reprova():
    """Gravação feita para outro desafio, sem a ação pedida, não serve."""
    gravacao = gravar(("piscar3", "virar_direita"))
    for outro in [("sorrir", "virar_esquerda"), ("piscar2", "sorrir"), ("virar_esquerda", "virar_direita")]:
        assert L.verificar_sequencia(gravacao, outro)[0] is False, outro


def test_movimentos_fora_do_passo_sao_tolerados():
    passos = ("sorrir", "virar_esquerda")
    assert L.verificar_sequencia(gravar(passos) + VIRAR_DIR, passos)[0] is True
    assert L.verificar_sequencia(gravar(("piscar2", "virar_esquerda")) + SORRIR, ("piscar2", "virar_esquerda"))[0] is True
    assert L.verificar_sequencia(gravar(("piscar2", "sorrir")) + PISCAR2, ("piscar2", "sorrir"))[0] is True


def test_piscadas_naturais_sao_toleradas():
    # pediu sorrir + virar, a pessoa piscou 1 vez sem querer: passa
    seq = gravar(("sorrir",)) + [q(0.30), q(0.10), q(0.30)] + VIRAR_ESQ
    assert L.verificar_sequencia(seq, ("sorrir", "virar_esquerda"))[0] is True


def test_piscar_pouco_reprova():
    uma = list(NEUTRO) + [q(0.30), q(0.10), q(0.30)] + SORRIR
    ok, motivo = L.verificar_sequencia(uma, ("piscar2", "sorrir"))
    assert ok is False and "2" in motivo


def test_rosto_ausente_em_qualquer_quadro_reprova():
    seq = gravar(("piscar3", "sorrir"))
    seq[4] = q(rosto=False)
    ok, motivo = L.verificar_sequencia(seq, ("piscar3", "sorrir"))
    assert ok is False and "rosto" in motivo.lower()


def test_giro_leve_nao_conta_mas_um_quadro_virado_basta():
    leve = list(NEUTRO) + [q(yaw=0.0), q(yaw=0.10), q(yaw=0.10)] + SORRISO_E_FIM()
    assert L.verificar_sequencia(leve, ("virar_esquerda", "sorrir"))[0] is False
    um_so = list(NEUTRO) + [q(yaw=0.0), q(yaw=0.30)] + SORRISO_E_FIM()
    assert L.verificar_sequencia(um_so, ("virar_esquerda", "sorrir"))[0] is True


def SORRISO_E_FIM():
    return list(SORRIR) + list(NEUTRO)


def test_poucos_quadros_e_desafio_invalido_reprovam():
    assert L.verificar_sequencia([q(), q()], ("sorrir", "piscar2"))[0] is False
    assert L.verificar_sequencia(gravar(("sorrir",)), ())[0] is False
    assert L.verificar_sequencia(gravar(("sorrir",)), ("voar",))[0] is False


def test_modo_antigo_continua_aceito():
    # desafio emitido antes da mudança (coluna `acao` = "login")
    assert L.verificar_sequencia(gravar(("piscar3",)), "login")[0] is True


def test_melhores_frontais_prefere_olhos_abertos_e_frontal():
    seq = [q(ear=0.30, yaw=0.30), q(ear=0.30, yaw=0.01), q(ear=0.05, yaw=0.0), q(rosto=False)]
    idxs = L.melhores_frontais(seq, n=2)
    assert idxs[0] == 1 and 3 not in idxs


# ------------------------------------------------------------------ sinal real (blendshape eyeBlink)


def b(blink: float, ear: float = 0.20) -> SinaisQuadro:
    # EAR "mediana" de propósito: com webcam a EAR de olho aberto pode ficar abaixo de
    # 0.24; quem decide aqui é o eyeBlink, o mesmo sinal que o app mostra.
    return SinaisQuadro(tem_rosto=True, ear=ear, blink=blink)


def test_piscadas_pelo_blendshape_como_o_app_ve():
    seq = [b(0.05), b(0.80), b(0.05), b(0.70), b(0.04), b(0.90), b(0.06)]
    assert L.piscadas_da_serie(seq) == 3
    assert L.verificar_sequencia([b(0.05)] * 3 + seq, ("piscar3",)) == (True, "")


def test_blendshape_sem_fechar_de_verdade_nao_conta():
    # olho "meio fechado" (0.35) não é piscada; sem reabrir também não
    assert L.piscadas_da_serie([b(0.05), b(0.35), b(0.05), b(0.35), b(0.05)]) == 0
    assert L.piscadas_da_serie([b(0.05), b(0.80), b(0.60), b(0.50)]) == 0


def test_blendshape_tolera_piscar_a_mais():
    seq = [b(0.05)] * 3 + [b(0.8), b(0.05)] * 5  # pediu 2, piscou 5
    assert L.verificar_sequencia(seq, ("piscar2",)) == (True, "")
