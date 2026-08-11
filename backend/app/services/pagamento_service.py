from fastapi import HTTPException

from app.repositories.memoria_repository import MemoriaRepository


def realizar_transferencia(
    repo: MemoriaRepository, origem_id: int, destino_id: int, valor: float
) -> dict:
    if valor <= 0:
        raise HTTPException(status_code=400, detail="O valor deve ser maior que zero.")

    if origem_id == destino_id:
        raise HTTPException(
            status_code=400,
            detail="Não é possível transferir para a mesma carteira.",
        )

    usuario_origem = repo.obter_usuario(origem_id)
    usuario_destino = repo.obter_usuario(destino_id)

    if not usuario_origem:
        raise HTTPException(status_code=404, detail="Carteira de origem não encontrada.")

    if not usuario_destino:
        raise HTTPException(status_code=404, detail="Carteira de destino não encontrada.")

    if usuario_origem["saldo"] < valor:
        raise HTTPException(status_code=400, detail="Saldo insuficiente.")

    # TODO FUTURO [MFA]: validar o segundo fator antes de autorizar a transferência.
    #
    # TODO FUTURO [Liveness Detection]: executar prova de vida quando a
    # transferência exigir validação biométrica.
    #
    # TODO FUTURO [Reconhecimento Facial]: validar a identidade do pagador
    # por reconhecimento facial quando aplicável.
    #
    # TODO FUTURO [Split Payment / CNPJ]: calcular e separar a parcela
    # tributária antes de creditar o destinatário.
    #
    # TODO FUTURO [Azure DB]: substituir as operações em memória por uma
    # transação atômica no Azure Cosmos DB ou Azure SQL Database.

    repo.atualizar_saldo(origem_id, usuario_origem["saldo"] - valor)
    repo.atualizar_saldo(destino_id, usuario_destino["saldo"] + valor)

    return repo.criar_transacao(origem_id, destino_id, valor)
