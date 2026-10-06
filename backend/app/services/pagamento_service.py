"""
Transferência com Split Payment (IBS/CBS) e MFA condicional ao valor.

Fluxo (nesta ordem, de propósito):
1. Validações baratas (valor, origem != destino).
2. AUTORIZAÇÃO: o usuário autenticado (JWT) só pode transferir da carteira DELE
   -- fecha o buraco de alguém mover a carteira de outra pessoa (item #1).
3. Resolve destino e calcula o split conforme o tipo do destino (PJ retém IBS/CBS).
4. MFA facial SÓ quando o valor passa do limite (LIMITE_FACIAL_REAIS, padrão R$ 500)
   -- espelha o design. Abaixo do limite, o próprio login (JWT) autoriza. O MFA é
   rate-limitado por usuário (item #3) e cada tentativa vai pra auditoria (item #5).
5. Débito + crédito do líquido + repasse do imposto à conta Governo + registro,
   tudo atômico no repositório (condição de corrida fechada) e idempotente
   (item #11: double-click não duplica).
"""

import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi import HTTPException

from app.core import security
from app.core.config import get_settings
from app.db.models import AuthMetodo, TipoPessoa
from app.repositories.exceptions import SaldoInsuficienteError
from app.repositories.repository import Repositorio
from app.services import biometria_service, split_service

logger = logging.getLogger("payflow.pagamento")


def _checar_rate_limit_biometria(repo: Repositorio, usuario_id: int) -> None:
    s = get_settings()
    desde = datetime.now(timezone.utc) - timedelta(minutes=s.biometria_janela_min)
    falhas = repo.contar_falhas_recentes(tipo="transferencia", desde=desde, usuario_id=usuario_id)
    if falhas >= s.biometria_max_tentativas:
        raise HTTPException(
            status_code=429,
            detail="Muitas tentativas de verificação facial. Tente novamente em alguns minutos.",
        )


def realizar_transferencia(
    repo: Repositorio,
    *,
    usuario: dict,
    origem_carteira_id: int,
    destino_carteira_id: int,
    valor: Decimal,
    foto_verificacao_base64: str | None = None,
    idempotency_key: str | None = None,
    ip: str | None = None,
) -> dict:
    valor = Decimal(valor)
    if valor <= 0:
        raise HTTPException(status_code=400, detail="O valor deve ser maior que zero.")
    if origem_carteira_id == destino_carteira_id:
        raise HTTPException(status_code=400, detail="Não é possível transferir para si mesmo.")

    # 2) Só a própria carteira.
    minha = repo.obter_carteira_do_usuario(usuario["id"])
    if not minha or minha["carteira_id"] != origem_carteira_id:
        raise HTTPException(status_code=403, detail="Você só pode transferir da sua própria carteira.")

    destino = repo.obter_conta_por_carteira(destino_carteira_id)
    if not destino:
        raise HTTPException(status_code=404, detail="Carteira de destino não encontrada.")

    # 3) Split conforme o tipo do destino.
    tipo_destino = TipoPessoa(destino["tipo"])
    split = split_service.calcular_split(valor, tipo_destino)

    # 4) MFA facial condicional ao valor.
    limite_facial = Decimal(str(get_settings().limite_facial_reais))
    verificacao = None
    auth_metodo = AuthMetodo.SENHA
    if valor > limite_facial:
        auth_metodo = AuthMetodo.SELFIE
        if not foto_verificacao_base64:
            raise HTTPException(
                status_code=400,
                detail=f"Transferências acima de R$ {limite_facial:.2f} exigem verificação facial (selfie).",
            )
        _checar_rate_limit_biometria(repo, usuario["id"])

        blob = repo.obter_embedding_cifrado(origem_carteira_id)
        embedding = security.decifrar_embedding(blob) if blob else None
        if embedding is None:
            raise HTTPException(status_code=400, detail="Carteira sem biometria cadastrada. Transferência bloqueada.")

        try:
            verificacao = biometria_service.verificar_biometria(foto_verificacao_base64, embedding)
        except HTTPException as e:
            # 401 = rosto não bateu / liveness; registra a falha pro rate-limit e auditoria.
            if e.status_code == 401:
                repo.registrar_sessao_mfa(
                    tipo="transferencia", sucesso=False, usuario_id=usuario["id"], ip=ip,
                    detalhe={"motivo": "biometria_reprovada"},
                )
            raise
        repo.registrar_sessao_mfa(
            tipo="transferencia", sucesso=True, usuario_id=usuario["id"], ip=ip,
            detalhe={"distancia": verificacao["distancia"], "confianca": verificacao["confianca"]},
        )

    # 5) Executa de forma atômica e idempotente.
    try:
        transacao = repo.executar_transferencia(
            origem_carteira_id=origem_carteira_id,
            destino_carteira_id=destino_carteira_id,
            split=split,
            verificacao_facial=verificacao,
            auth_metodo=auth_metodo,
            idempotency_key=idempotency_key,
        )
    except SaldoInsuficienteError:
        raise HTTPException(status_code=400, detail="Saldo insuficiente.")

    repo.registrar_log(
        ator=usuario["email"], acao="transferencia", ip=ip,
        detalhe={
            "transacao_id": transacao["id"],
            "valor_bruto": str(transacao["valor_bruto"]),
            "imposto_total": str(transacao["imposto_total"]),
            "destino": destino_carteira_id,
            "auth": auth_metodo.value,
        },
    )
    return transacao


def listar_transacoes(repo: Repositorio, *, usuario: dict, limite: int, offset: int) -> list[dict]:
    """Admin vê tudo; usuário comum vê só as transações da própria carteira
    (fecha o item #1: antes qualquer um via o histórico do sistema inteiro)."""
    if usuario["papel"] == "admin":
        return repo.listar_transacoes(limite=limite, offset=offset)
    minha = repo.obter_carteira_do_usuario(usuario["id"])
    if not minha:
        return []
    return repo.listar_transacoes(carteira_id=minha["carteira_id"], limite=limite, offset=offset)
