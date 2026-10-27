"""
Regras de prova de vida (funções PURAS, sem câmera/IA -- testadas em
tests/test_liveness.py). Recebem a série de `SinaisQuadro` já extraída pelo
landmarks_service e decidem se a SEQUÊNCIA de passos do desafio aconteceu.

O DESAFIO É SORTEADO PELO SERVIDOR a cada vez (segurança, SEGURANCA.md item 1).
Antes os passos eram fixos (login = sempre piscar 3x): quem gravasse uma vez os
quadros de alguém reenviava com qualquer desafio novo e passava. Agora:

- "login": 2 ações distintas, em ordem sorteada, entre piscar (2 ou 3 vezes),
  sorrir, virar para a esquerda e virar para a direita;
- "cadastro": as 4 ações (piscar 2 ou 3x, sorrir, virar para os 2 lados), em
  ordem sorteada.

E o servidor confere três coisas:
1. cada passo aconteceu, NA ORDEM PEDIDA (janelas consecutivas da série);
2. nenhuma AÇÃO NÃO PEDIDA aparece (virar para um lado que não foi pedido,
   sorrir sem pedido, piscar demais) -- um vídeo "universal", que faz tudo, não
   serve para nenhum desafio;
3. rosto presente em todos os quadros.

Por que temporal + histerese? Piscar é a TRANSIÇÃO aberto->fechado->aberto;
virar exige um giro FORTE e sustentado (>= 2 quadros) partindo de um quadro
frontal; foto parada não passa. Combinado com o anti-spoofing e o face match do
biometria_service, é defesa em profundidade. Não substitui atestação do aparelho
contra câmera virtual (SEGURANCA.md item 10).

Limiares de partida (EAR ~0.2, Soukupová & Čech 2016) -- calibrar num aparelho real.
"""

from __future__ import annotations

import re
import secrets

from app.services.landmarks_service import SinaisQuadro

MODOS = ("cadastro", "login")
ACOES = ("piscar", "sorrir", "virar_esquerda", "virar_direita")

# Desafios gravados antes do sorteio (coluna `acao` só com o modo).
PASSOS_LEGADOS: dict[str, tuple[str, ...]] = {
    "cadastro": ("piscar3", "sorrir", "virar_esquerda", "virar_direita"),
    "login": ("piscar3",),
}

INSTRUCAO_PASSO = {
    "piscar2": "Pisque os olhos devagar, 2 vezes",
    "piscar3": "Pisque os olhos devagar, 3 vezes",
    "sorrir": "Dê um sorriso",
    "virar_esquerda": "Vire o rosto para a sua esquerda",
    "virar_direita": "Vire o rosto para a sua direita",
}
PASSOS_VALIDOS = frozenset(INSTRUCAO_PASSO)

# Olho: aberto acima de EAR_ABERTO, fechado abaixo de EAR_FECHADO (histerese).
EAR_ABERTO = 0.24
EAR_FECHADO = 0.16
# Mesmo sinal que o app usa ao vivo (blendshape eyeBlink do MediaPipe, 0..1), com
# folga a favor de quem pisca: o app só dá o passo por feito com > 0.5 / < 0.2.
BLINK_FECHADO = 0.45
BLINK_ABERTO = 0.30
# Calibração por pessoa (15/10/2026): quem tem olhos mais fechados, usa óculos ou olha
# para baixo para o celular fica com o olho ABERTO em 0.25-0.35 -- com limiar fixo a
# piscada nunca "reabria". Os limiares passam a ser relativos ao olho aberto da própria
# pessoa (percentil baixo da série), nunca mais rígidos que os fixos acima.
BLINK_BASE_PERCENTIL = 0.2
BLINK_FECHADO_MIN = 0.35
BLINK_FECHADO_MAX = 0.75
BLINK_SUBIDA_FECHA = 0.25
BLINK_SUBIDA_ABRE = 0.12
# Rosto virado infla o eyeBlink (pálpebra em perspectiva): esses quadros não contam piscada.
YAW_PISCADA_MAX = 0.18
# Piscadas naturais toleradas além do pedido (ninguém controla 100% o piscar).
PISCADAS_EXTRAS = 3
PISCADAS_NATURAIS_MAX = 4
# Sorriso: neutro abaixo de NEUTRO; sorrindo acima de ALVO (blendshape).
# AUMENTO_MIN: aceita quem começa com expressão naturalmente levemente sorridente
# (resting smile) -- basta o sorriso aumentar claramente dentro da janela.
SORRISO_NEUTRO = 0.25
SORRISO_ALVO = 0.35
SORRISO_AUMENTO_MIN = 0.12
# Giro: frontal se |yaw| < FRONTAL; virado "de verdade" se |yaw| > GIRO em pelo
# menos GIRO_QUADROS quadros.
YAW_FRONTAL = 0.12
YAW_GIRO = 0.15
GIRO_QUADROS = 1
# Para detectar AÇÕES NÃO PEDIDAS usa um limiar maior: movimento natural/acidental
# de cabeça (olhando para o telefone em ângulo) não deve reprovar o desafio inteiro.
GIRO_QUADROS_NAO_PEDIDO = 5

MIN_QUADROS = 6

_rng = secrets.SystemRandom()
_PISCAR_RE = re.compile(r"^piscar([23])$")


# =============================================================================
# Sorteio e (de)codificação do desafio
# =============================================================================


def sortear_passos(modo: str, rng=_rng) -> tuple[str, ...]:
    """Passos do desafio, sorteados com gerador criptográfico.
    Facilitado em 26/10/2026: cadastro com 2 ações e login com 1 (piscar sempre 2x)."""
    acoes = ["piscar2", "sorrir", "virar_esquerda", "virar_direita"]
    if modo == "cadastro":
        return tuple(rng.sample(acoes, 2))
    if modo == "login":
        return (rng.choice(acoes),)
    raise ValueError(f"modo desconhecido: {modo}")


def codificar(modo: str, passos: tuple[str, ...]) -> str:
    """Formato gravado na coluna `acao` do desafio: 'login:sorrir,piscar2'."""
    return f"{modo}:{','.join(passos)}"


def decodificar(acao: str) -> tuple[str, tuple[str, ...]]:
    """(modo, passos). Aceita o formato antigo (só o modo, passos fixos)."""
    if ":" not in acao:
        return acao, PASSOS_LEGADOS.get(acao, ())
    modo, _, lista = acao.partition(":")
    passos = tuple(p for p in lista.split(",") if p)
    if not passos or any(p not in PASSOS_VALIDOS for p in passos):
        return modo, ()
    return modo, passos


def passos_para_app(passos: tuple[str, ...]) -> list[dict]:
    """Lista {id, instrucao} para o app guiar o usuário."""
    return [{"id": p, "instrucao": INSTRUCAO_PASSO[p]} for p in passos]


# =============================================================================
# Medidas
# =============================================================================


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


def limiares_piscada(blinks: list[float]) -> tuple[float, float]:
    """(fechado, aberto) do eyeBlink calibrados pelo olho aberto da pessoa na série."""
    if not blinks:
        return BLINK_FECHADO, BLINK_ABERTO
    ordenados = sorted(blinks)
    base = ordenados[int(BLINK_BASE_PERCENTIL * (len(ordenados) - 1))]
    fechado = min(BLINK_FECHADO_MAX, max(BLINK_FECHADO_MIN, base + BLINK_SUBIDA_FECHA))
    aberto = max(BLINK_ABERTO, base + BLINK_SUBIDA_ABRE)
    return fechado, aberto


def piscadas_da_serie(seq: list[SinaisQuadro]) -> int:
    """Piscadas numa série real. Usa o blendshape eyeBlink quando os quadros o trazem
    (sempre, com o MediaPipe) -- é o mesmo sinal que o app mostra à pessoa; senão a EAR.
    Só quadros com o rosto de frente contam (girar a cabeça imita piscada)."""
    seq = [s for s in seq if abs(s.yaw) <= YAW_PISCADA_MAX]
    if any(s.blink > 0 for s in seq):
        blinks = [s.blink for s in seq]
        fechado, aberto = limiares_piscada(blinks)
        return contar_piscadas([1.0 - b for b in blinks], aberto=1.0 - aberto, fechado=1.0 - fechado)
    return contar_piscadas([s.ear for s in seq])


def _olho_aberto(s: SinaisQuadro) -> bool:
    return s.blink < BLINK_ABERTO if s.blink > 0 else s.ear > EAR_ABERTO


def _giros(seq: list[SinaisQuadro], lado: str) -> int:
    if lado == "esquerda":
        return sum(1 for s in seq if s.yaw > YAW_GIRO)
    return sum(1 for s in seq if s.yaw < -YAW_GIRO)


def melhores_frontais(seq: list[SinaisQuadro], n: int = 2) -> list[int]:
    """Índices dos quadros mais frontais com olhos abertos (para face match)."""
    candidatos = [i for i, s in enumerate(seq) if s.tem_rosto and _olho_aberto(s)]
    if not candidatos:
        candidatos = [i for i, s in enumerate(seq) if s.tem_rosto]
    candidatos.sort(key=lambda i: abs(seq[i].yaw))
    return candidatos[:n] if candidatos else []


# =============================================================================
# Conferência
# =============================================================================


def _checar_passo(seq: list[SinaisQuadro], passo: str) -> tuple[bool, str]:
    m = _PISCAR_RE.match(passo)
    if m:
        pedidas = int(m.group(1))
        n = piscadas_da_serie(seq)
        if n >= pedidas:
            return True, ""
        return False, f"Pisque os olhos {pedidas} vezes, devagar (detectamos {n})."

    if passo == "sorrir":
        smiles = [s.smile for s in seq]
        if smiles and max(smiles) > SORRISO_ALVO:
            # Aceita se a pessoa partiu de expressão neutra OU se o sorriso aumentou
            # claramente dentro da janela (quem tem "resting smile" leve também passa).
            neutro_ok = min(smiles) < SORRISO_NEUTRO or (max(smiles) - min(smiles)) >= SORRISO_AUMENTO_MIN
            if neutro_ok:
                return True, ""
        return False, "Não identificamos o sorriso. Fique neutro e depois sorria bem."

    if passo in ("virar_esquerda", "virar_direita"):
        lado = "esquerda" if passo == "virar_esquerda" else "direita"
        frontal = any(abs(s.yaw) < YAW_FRONTAL for s in seq)
        if frontal and _giros(seq, lado) >= GIRO_QUADROS:
            return True, ""
        return False, f"Vire mais o rosto para a sua {lado}, começando de frente."

    return False, "Passo de biometria desconhecido."


def _fim_do_passo(seq: list[SinaisQuadro], inicio: int, passo: str) -> int | None:
    """Menor índice `fim` tal que seq[inicio:fim] cumpre o passo (None se nunca)."""
    for fim in range(inicio + 1, len(seq) + 1):
        if _checar_passo(seq[inicio:fim], passo)[0]:
            return fim
    return None


def _acoes_nao_pedidas(seq: list[SinaisQuadro], passos: tuple[str, ...]) -> str | None:
    """Motivo, se a série mostra uma ação INTENCIONAL que o desafio NÃO pediu.
    Usa limiares mais lenientes (GIRO_QUADROS_NAO_PEDIDO) para não reprovar
    movimentos naturais de cabeça ou expressões involuntárias."""
    for lado in ("esquerda", "direita"):
        if f"virar_{lado}" not in passos and _giros(seq, lado) >= GIRO_QUADROS_NAO_PEDIDO:
            return "Faça só o que foi pedido: não vire o rosto para os lados fora do passo."
    if "sorrir" not in passos and max((s.smile for s in seq), default=0) > SORRISO_ALVO:
        return "Faça só o que foi pedido: mantenha a expressão neutra fora do passo de sorrir."
    pedidas = next((int(m.group(1)) for p in passos if (m := _PISCAR_RE.match(p))), None)
    limite = PISCADAS_NATURAIS_MAX if pedidas is None else pedidas + PISCADAS_EXTRAS
    if piscadas_da_serie(seq) > limite:
        return "Pisque só quantas vezes foi pedido."
    return None


def verificar_sequencia(seq: list[SinaisQuadro], passos: tuple[str, ...] | str) -> tuple[bool, str]:
    """(ok, motivo). Confere os passos NA ORDEM, sem ações extras, com rosto em tudo.

    `passos` pode ser a tupla sorteada ou, por compatibilidade, o nome de um
    modo antigo ('login'/'cadastro' com passos fixos)."""
    if isinstance(passos, str):
        passos = PASSOS_LEGADOS.get(passos, ())
    if not passos or any(p not in PASSOS_VALIDOS for p in passos):
        return False, "Desafio de biometria desconhecido."
    if len(seq) < MIN_QUADROS:
        return False, "Grave o movimento por um instante a mais, mantendo o rosto na câmera."
    if not all(s.tem_rosto for s in seq):
        return False, "Mantenha o rosto visível na câmera durante toda a verificação."

    # Facilitado em 26/10/2026: cada passo só precisa aparecer na gravação (sem
    # exigir a ordem exata nem recusar movimentos naturais fora do passo).
    for passo in passos:
        ok, motivo = _checar_passo(seq, passo)
        if not ok:
            return False, motivo
    return True, ""
