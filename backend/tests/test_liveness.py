"""
Testes das regras de prova de vida (liveness_logic) -- funções puras, sem câmera
nem IA. Montamos séries de SinaisQuadro na mão.

O desafio é SORTEADO pelo servidor: os testes conferem que cada passo precisa
acontecer na ordem pedida, que ação não pedida reprova (vídeo "universal" não
serve) e que uma gravação feita para um desafio não serve para outro (replay).
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
        assert len(login) == 2 and len(set(login)) == 2
        assert all(p in L.PASSOS_VALIDOS for p in login)
        assert sum(p.startswith("piscar") for p in login) <= 1
        vistos.add(login)
        cad = L.sortear_passos("cadastro", rng)
        assert len(cad) == 4
        assert {"sorrir", "virar_esquerda", "virar_direita"} <= set(cad)
    # 4 ações x 2 contagens de piscada, 2 na ordem: 18 combinações possíveis
    assert len(vistos) >= 15


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


def test_fora_de_ordem_reprova():
    passos = ("sorrir", "virar_esquerda")
    ok, motivo = L.verificar_sequencia(gravar(("virar_esquerda", "sorrir")), passos)
    assert ok is False and "ordem" in motivo


def test_replay_de_outro_desafio_reprova():
    """Gravação feita para um desafio de login não serve para outro sorteio."""
    gravacao = gravar(("piscar3", "virar_direita"))
    for outro in [("sorrir", "virar_esquerda"), ("virar_direita", "piscar3"), ("piscar2", "sorrir"),
                  ("virar_esquerda", "virar_direita")]:
        assert L.verificar_sequencia(gravacao, outro)[0] is False, outro


def test_video_universal_reprova():
    """Um vídeo que faz TUDO (para servir a qualquer desafio) não passa no login."""
    tudo = gravar(("piscar3", "sorrir", "virar_esquerda", "virar_direita"))
    ok, motivo = L.verificar_sequencia(tudo, ("piscar3", "sorrir"))
    assert ok is False and "pedido" in motivo


def test_acao_nao_pedida_reprova():
    ok, motivo = L.verificar_sequencia(gravar(("sorrir", "virar_esquerda")) + VIRAR_DIR, ("sorrir", "virar_esquerda"))
    assert ok is False and "lados" in motivo
    ok, motivo = L.verificar_sequencia(gravar(("piscar2", "virar_esquerda")) + SORRIR, ("piscar2", "virar_esquerda"))
    assert ok is False and "neutra" in motivo
    # piscar demais além da folga natural
    ok, motivo = L.verificar_sequencia(gravar(("piscar2", "sorrir")) + PISCAR2, ("piscar2", "sorrir"))
    assert ok is False and "Pisque" in motivo


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


def test_giro_leve_ou_de_um_quadro_nao_conta():
    leve = list(NEUTRO) + [q(yaw=0.0), q(yaw=0.15), q(yaw=0.15)] + SORRISO_E_FIM()
    assert L.verificar_sequencia(leve, ("virar_esquerda", "sorrir"))[0] is False
    um_so = list(NEUTRO) + [q(yaw=0.0), q(yaw=0.30)] + SORRISO_E_FIM()
    assert L.verificar_sequencia(um_so, ("virar_esquerda", "sorrir"))[0] is False


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


def test_blendshape_continua_barrando_piscar_demais():
    seq = [b(0.05)] * 3 + [b(0.8), b(0.05)] * 5  # pediu 2, piscou 5
    ok, motivo = L.verificar_sequencia(seq, ("piscar2",))
    assert not ok and "Pisque só" in motivo
