"""
Limites de saída, aparelhos confiáveis e regra de risco (bloqueio cautelar).

Regras (configuráveis em core/config.py):
- Limite por transação, diurno e noturno por carteira. Noturno = 20h às 6h
  (horário de Brasília), como na Res. BCB 142/2021. Redução vale na hora; aumento
  só depois de LIMITE_CARENCIA_HORAS (o cliente não consegue subir o limite na
  hora de um golpe).
- Aparelho novo (IN BCB 491/2024): pessoa física num aparelho ainda não
  confiável faz no máximo R$ 200 por transação e R$ 1.000 por dia NAQUELE
  aparelho. O aparelho vira confiável com uma verificação facial feita nele.
- Bloqueio cautelar: transferência a partir de RISCO_VALOR_MINIMO para alguém com
  quem a conta nunca transacionou fica retida no recebedor por até
  BLOQUEIO_CAUTELAR_HORAS. Nesse prazo o pagador pode contestar (MED).

As checagens de limite rodam DENTRO do lock da carteira de origem
(Repositorio.executar_movimento -> `checar`), então duas transferências
simultâneas não passam juntas pelo mesmo limite.
"""

from datetime import timedelta
from decimal import Decimal

from fastapi import HTTPException

from app.core import security, tempo
from app.core.config import get_settings
from app.repositories.repository import Repositorio
from app.services import biometria_service

LIMITES_PADRAO = {
    "PF": {"por_transacao": Decimal("5000.00"), "diurno": Decimal("10000.00"), "noturno": Decimal("1000.00")},
    "PJ": {"por_transacao": Decimal("50000.00"), "diurno": Decimal("200000.00"), "noturno": Decimal("20000.00")},
}


def _brl(v: Decimal) -> str:
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def checador_de_limites(*, valor: Decimal, titular_tipo: str, dispositivo: dict | None):
    """Devolve o callback que o repositório chama com a carteira travada."""
    s = get_settings()

    def checar(sessao, origem) -> None:
        agora = tempo.agora()
        lim = Repositorio.limite_na_sessao(sessao, origem.id)
        if lim is not None:
            if valor > lim.por_transacao:
                raise HTTPException(status_code=403, detail=f"Valor acima do seu limite por transação ({_brl(lim.por_transacao)}).")
            noturno = tempo.eh_noturno(agora, s.noturno_hora_inicio, s.noturno_hora_fim)
            teto = lim.noturno if noturno else lim.diurno
            inicio = tempo.inicio_periodo(agora, s.noturno_hora_inicio, s.noturno_hora_fim)
            usado = Repositorio.soma_saidas(sessao, origem.id, inicio)
            if usado + valor > teto:
                periodo = "noturno (20h às 6h)" if noturno else "diurno"
                raise HTTPException(
                    status_code=403,
                    detail=f"Limite {periodo} excedido: disponível {_brl(max(teto - usado, Decimal('0')))}.",
                )
        if titular_tipo == "PF" and (dispositivo is None or not dispositivo["confiavel"]):
            teto_tx = Decimal(str(s.dispositivo_novo_por_transacao))
            teto_dia = Decimal(str(s.dispositivo_novo_diario))
            if valor > teto_tx:
                raise HTTPException(
                    status_code=403,
                    detail=f"Neste aparelho novo o limite é {_brl(teto_tx)} por transação. Confirme o aparelho com verificação facial para liberar.",
                )
            if dispositivo is not None:
                usado_dia = Repositorio.soma_saidas(sessao, origem.id, tempo.inicio_do_dia(agora), dispositivo_id=dispositivo["id"])
                if usado_dia + valor > teto_dia:
                    raise HTTPException(
                        status_code=403,
                        detail=f"Neste aparelho novo o limite é {_brl(teto_dia)} por dia. Confirme o aparelho com verificação facial para liberar.",
                    )

    return checar


def bloqueio_cautelar(repo: Repositorio, *, origem_id: int, destino: dict, valor: Decimal) -> object:
    """Data até quando o valor fica retido, ou None."""
    s = get_settings()
    if destino["titular_tipo"] not in ("PF", "PJ"):
        return None
    if valor < Decimal(str(s.risco_valor_minimo)):
        return None
    if repo.ja_transacionou(origem_id, destino["carteira_id"]):
        return None
    return tempo.agora() + timedelta(hours=s.bloqueio_cautelar_horas)


def atualizar_limites(repo: Repositorio, *, conta: dict, novos: dict) -> dict:
    atual = repo.obter_limite(conta["carteira_id"])
    if atual is None:
        raise HTTPException(status_code=404, detail="Esta conta não tem limites configurados.")
    imediatos, pendentes = {}, {}
    for campo, valor in novos.items():
        if valor is None:
            continue
        (imediatos if valor <= atual[campo] else pendentes)[campo] = valor
    vigente = tempo.agora() + timedelta(hours=get_settings().limite_carencia_horas) if pendentes else None
    return repo.salvar_limite(conta["carteira_id"], imediatos=imediatos, pendentes=pendentes, vigente_em=vigente)


def confiar_dispositivo(repo: Repositorio, *, usuario: dict, dispositivo: dict | None, prova, ip: str | None) -> dict:
    if dispositivo is None:
        raise HTTPException(status_code=400, detail="Envie o header X-Dispositivo-Id do aparelho a confirmar.")
    if dispositivo["confiavel"]:
        return dispositivo
    verificacao = verificar_rosto(repo, usuario=usuario, prova=prova, ip=ip, tipo="confiar_dispositivo")
    d = repo.marcar_dispositivo_confiavel(usuario["id"], dispositivo["id"])
    repo.registrar_log(ator=usuario["email"], acao="dispositivo_confiavel", ip=ip,
                       detalhe={"dispositivo_id": d["id"], "distancia": verificacao.get("distancia")})
    return d


def checar_rate_limit_biometria(repo: Repositorio, usuario_id: int) -> None:
    s = get_settings()
    desde = tempo.agora() - timedelta(minutes=s.biometria_janela_min)
    if repo.contar_eventos(tipo="biometria", desde=desde, usuario_id=usuario_id) >= s.biometria_max_tentativas:
        raise HTTPException(status_code=429, detail="Muitas tentativas de verificação facial. Tente novamente em alguns minutos.")


def verificar_rosto(repo: Repositorio, *, usuario: dict, prova, ip: str | None, tipo: str) -> dict:
    """MFA facial com rate limit e auditoria. Usado por transferência, lote,
    aprovação, pagamento de cobrança e confirmação de aparelho."""
    if prova is None:
        raise HTTPException(status_code=400, detail="Esta operação exige verificação facial (envie `biometria`).")
    checar_rate_limit_biometria(repo, usuario["id"])
    blob = repo.obter_embedding_cifrado(usuario["id"])
    embedding = security.decifrar_embedding(blob) if blob else None
    if embedding is None:
        raise HTTPException(status_code=400, detail="Sua conta não tem biometria cadastrada. Operação bloqueada.")
    try:
        v = biometria_service.verificar(repo, prova, usuario_id=usuario["id"], embedding_cadastrado=embedding)
    except HTTPException as e:
        if e.status_code == 401:
            repo.registrar_sessao_mfa(tipo="biometria", sucesso=False, usuario_id=usuario["id"], ip=ip,
                                      detalhe={"operacao": tipo, "motivo": e.detail})
        raise
    repo.registrar_sessao_mfa(tipo="biometria", sucesso=True, usuario_id=usuario["id"], ip=ip,
                              detalhe={"operacao": tipo, "distancia": v.get("distancia")})
    return v


def exigir_dispositivo(dispositivo: dict | None) -> None:
    if dispositivo is None:
        raise HTTPException(status_code=400, detail="Envie o header X-Dispositivo-Id (identificador do aparelho) para movimentar dinheiro.")
