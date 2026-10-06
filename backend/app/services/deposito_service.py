"""
Depósito controlado. Substitui o `saldo_inicial` livre do cadastro (item #2: criava
dinheiro do nada). Só um admin pode depositar, e o crédito sai da conta Governo
(emissor) -- deixa rastro de quanto dinheiro foi colocado em circulação, no
histórico de saldo e nas transações.
"""

from decimal import Decimal

from fastapi import HTTPException

from app.repositories.exceptions import CarteiraGovernoAusenteError
from app.repositories.repository import Repositorio


def depositar(repo: Repositorio, *, admin: dict, carteira_id: int, valor: Decimal, ip: str | None = None) -> dict:
    valor = Decimal(valor)
    if valor <= 0:
        raise HTTPException(status_code=400, detail="O valor do depósito deve ser maior que zero.")
    if not repo.carteira_existe(carteira_id):
        raise HTTPException(status_code=404, detail="Carteira de destino não encontrada.")
    try:
        transacao = repo.depositar(carteira_id=carteira_id, valor=valor)
    except CarteiraGovernoAusenteError:
        raise HTTPException(status_code=503, detail="Conta Governo não inicializada. Tente novamente após o boot.")

    repo.registrar_log(
        ator=admin["email"], acao="deposito", ip=ip,
        detalhe={"carteira_id": carteira_id, "valor": str(valor), "transacao_id": transacao["id"]},
    )
    return transacao
