"""
Regras de prova de vida (funções PURAS, sem câmera/IA -- testadas em
tests/test_liveness.py). Recebem a série de `SinaisQuadro` já extraída pelo
landmarks_service e decidem se a SEQUÊNCIA de passos do desafio aconteceu.

Dois modos, fixos (não aleatórios):
- "cadastro": piscar 3x -> sorrir -> virar p/ esquerda -> virar p/ direita. É o
  processo completo da abertura de conta.
- "login": só piscar 3x. Entrar pela câmera é mais rápido (no celular normalmente
  nem usa a câmera -- usa a biometria do aparelho), mas o faceless continua.

Por que temporal + histerese? Virar a cabeça MUITO rápido ou uma foto parada não
passam: piscar é a TRANSIÇÃO aberto->fechado->aberto (exigimos 3); virar exige um
giro FORTE e sustentado (>= 2 quadros) partindo de um quadro frontal; e todos os
quadros precisam ter rosto (fecha o "aprova até sem rosto"). Combinado com o
anti-spoofing e o face match do biometria_service, é defesa em profundidade.

Limiares de partida (EAR ~0.2, Soukupová & Čech 2016) -- calibrar num aparelho real.
"""

from __future__ import annotations

from app.services.landmarks_service import SinaisQuadro

# Sequência de cada modo (ordem é a que o app mostra; o servidor confere que
# TODOS os passos aconteceram na série de quadros).
PASSOS: dict[str, tuple[str, ...]] = {
    "cadastro": ("piscar3", "sorrir", "virar_esquerda", "virar_direita"),
    "login": ("piscar3",),
}
MODOS = tuple(PASSOS.keys())

INSTRUCAO_PASSO = {
    "piscar3": "Pisque os olhos devagar, 3 vezes",
    "sorrir": "Agora dê um sorriso",
    "virar_esquerda": "Vire o rosto para a sua esquerda",
    "virar_direita": "Vire o rosto para a sua direita",
}

# Olho: aberto acima de EAR_ABERTO, fechado abaixo de EAR_FECHADO (histerese).
EAR_ABERTO = 0.24
EAR_FECHADO = 0.16
PISCADAS_EXIGIDAS = 3
# Sorriso: neutro abaixo de NEUTRO; sorrindo acima de ALVO (blendshape).
SORRISO_NEUTRO = 0.20
SORRISO_ALVO = 0.45
# Giro: frontal se |yaw| < FRONTAL; virado "de verdade" se |yaw| > GIRO (mais
# forte que antes, para um gingado leve não passar) em pelo menos GIRO_QUADROS.
YAW_FRONTAL = 0.08
YAW_GIRO = 0.22
GIRO_QUADROS = 2

MIN_QUADROS = 6


def contar_piscadas(ears: list[float], aberto: float = EAR_ABERTO, fechado: float = EAR_FECHADO) -> int:
    """Conta transições aberto->fechado->aberto numa série de EAR (histerese)."""
    estado = "aberto"
    piscadas = 0
    for e in ears:
        if estado == "aberto" and e < fechado:
            estado = "fechado"
        elif estado == "fechado" and e > aberto:
            estado = "aberto"
            piscadas += 1
    return piscadas


def melhores_frontais(seq: list[SinaisQuadro], n: int = 2) -> list[int]:
    """Índices dos quadros mais frontais com olhos abertos (para face match)."""
    candidatos = [i for i, s in enumerate(seq) if s.tem_rosto and s.ear > EAR_ABERTO]
    if not candidatos:
        candidatos = [i for i, s in enumerate(seq) if s.tem_rosto]
    candidatos.sort(key=lambda i: abs(seq[i].yaw))
    return candidatos[:n] if candidatos else []


def _checar_passo(seq: list[SinaisQuadro], passo: str) -> tuple[bool, str]:
    if passo == "piscar3":
        n = contar_piscadas([s.ear for s in seq])
        if n >= PISCADAS_EXIGIDAS:
            return True, ""
        return False, f"Pisque os olhos {PISCADAS_EXIGIDAS} vezes, devagar (detectamos {n})."

    if passo == "sorrir":
        smiles = [s.smile for s in seq]
        if min(smiles) < SORRISO_NEUTRO and max(smiles) > SORRISO_ALVO:
            return True, ""
        return False, "Não identificamos o sorriso. Fique neutro e depois sorria."

    if passo in ("virar_esquerda", "virar_direita"):
        yaws = [s.yaw for s in seq]
        frontal = any(abs(y) < YAW_FRONTAL for y in yaws)
        if passo == "virar_esquerda":
            fortes = sum(1 for y in yaws if y > YAW_GIRO)
            lado = "esquerda"
        else:
            fortes = sum(1 for y in yaws if y < -YAW_GIRO)
            lado = "direita"
        if frontal and fortes >= GIRO_QUADROS:
            return True, ""
        return False, f"Vire mais o rosto para a sua {lado}, começando de frente."

    return False, "Passo de biometria desconhecido."


def verificar_sequencia(seq: list[SinaisQuadro], modo: str) -> tuple[bool, str]:
    """(ok, motivo). Confere que TODOS os passos do `modo` aconteceram na série."""
    passos = PASSOS.get(modo)
    if passos is None:
        return False, "Desafio de biometria desconhecido."
    if len(seq) < MIN_QUADROS:
        return False, "Grave o movimento por um instante a mais, mantendo o rosto na câmera."
    if not all(s.tem_rosto for s in seq):
        return False, "Mantenha o rosto visível na câmera durante toda a verificação."
    for passo in passos:
        ok, motivo = _checar_passo(seq, passo)
        if not ok:
            return False, motivo
    return True, ""


def passos_do_modo(modo: str) -> list[dict]:
    """Lista {id, instrucao} para o app guiar o usuário."""
    return [{"id": p, "instrucao": INSTRUCAO_PASSO[p]} for p in PASSOS.get(modo, ())]
