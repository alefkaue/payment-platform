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
# Piscadas naturais toleradas além do pedido (ninguém controla 100% o piscar).
PISCADAS_EXTRAS = 1
PISCADAS_NATURAIS_MAX = 2
# Sorriso: neutro abaixo de NEUTRO; sorrindo acima de ALVO (blendshape).
SORRISO_NEUTRO = 0.20
SORRISO_ALVO = 0.45
# Giro: frontal se |yaw| < FRONTAL; virado "de verdade" se |yaw| > GIRO em pelo
# menos GIRO_QUADROS quadros.
YAW_FRONTAL = 0.08
YAW_GIRO = 0.22
GIRO_QUADROS = 2

MIN_QUADROS = 6

_rng = secrets.SystemRandom()
_PISCAR_RE = re.compile(r"^piscar([23])$")


# =============================================================================
# Sorteio e (de)codificação do desafio
# =============================================================================


def sortear_passos(modo: str, rng=_rng) -> tuple[str, ...]:
    """Passos do desafio, sorteados com gerador criptográfico."""
    piscar = rng.choice(("piscar2", "piscar3"))
    acoes = [piscar, "sorrir", "virar_esquerda", "virar_direita"]
    if modo == "cadastro":
        rng.shuffle(acoes)
        return tuple(acoes)
    if modo == "login":
        return tuple(rng.sample(acoes, 2))
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


def _giros(seq: list[SinaisQuadro], lado: str) -> int:
    if lado == "esquerda":
        return sum(1 for s in seq if s.yaw > YAW_GIRO)
    return sum(1 for s in seq if s.yaw < -YAW_GIRO)


def melhores_frontais(seq: list[SinaisQuadro], n: int = 2) -> list[int]:
    """Índices dos quadros mais frontais com olhos abertos (para face match)."""
    candidatos = [i for i, s in enumerate(seq) if s.tem_rosto and s.ear > EAR_ABERTO]
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
        n = contar_piscadas([s.ear for s in seq])
        if n >= pedidas:
            return True, ""
        return False, f"Pisque os olhos {pedidas} vezes, devagar (detectamos {n})."

    if passo == "sorrir":
        smiles = [s.smile for s in seq]
        if smiles and min(smiles) < SORRISO_NEUTRO and max(smiles) > SORRISO_ALVO:
            return True, ""
        return False, "Não identificamos o sorriso. Fique neutro e depois sorria."

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
    """Motivo, se a série mostra uma ação que o desafio NÃO pediu."""
    for lado in ("esquerda", "direita"):
        if f"virar_{lado}" not in passos and _giros(seq, lado) >= GIRO_QUADROS:
            return "Faça só o que foi pedido: não vire o rosto para os lados fora do passo."
    if "sorrir" not in passos and max(s.smile for s in seq) > SORRISO_ALVO:
        return "Faça só o que foi pedido: mantenha a expressão neutra fora do passo de sorrir."
    pedidas = next((int(m.group(1)) for p in passos if (m := _PISCAR_RE.match(p))), None)
    limite = PISCADAS_NATURAIS_MAX if pedidas is None else pedidas + PISCADAS_EXTRAS
    if contar_piscadas([s.ear for s in seq]) > limite:
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

    inicio = 0
    for passo in passos:
        fim = _fim_do_passo(seq, inicio, passo)
        if fim is None:
            # Diz o que faltou; se o passo existe na série inteira, foi fora de ordem.
            ok_fora_de_ordem = _checar_passo(seq, passo)[0]
            if ok_fora_de_ordem:
                return False, "Faça os passos na ordem pedida."
            return False, _checar_passo(seq[inicio:], passo)[1]
        # O passo seguinte pode começar no último quadro deste (ex.: o quadro
        # frontal que encerra uma virada abre a próxima).
        inicio = max(fim - 1, inicio)

    motivo = _acoes_nao_pedidas(seq, passos)
    if motivo:
        return False, motivo
    return True, ""
