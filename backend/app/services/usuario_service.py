from fastapi import HTTPException

from app.repositories.memoria_repository import MemoriaRepository


def criar_usuario(
    repo: MemoriaRepository,
    nome: str,
    carteira_id: int,
    saldo_inicial: float,
) -> dict:
    if repo.carteira_existe(carteira_id):
        raise HTTPException(
            status_code=409,
            detail="O ID da carteira já está cadastrado.",
        )

    # TODO FUTURO [Azure DB]: substituir a persistência em memória por
    # Azure Cosmos DB ou Azure SQL Database neste ponto.
    #
    # TODO FUTURO [MFA]: integrar MFA no fluxo de autenticação antes
    # de permitir operações sensíveis.
    #
    # TODO FUTURO [Liveness Detection]: adicionar prova de vida para
    # operações que exigirem validação biométrica.
    #
    # TODO FUTURO [Reconhecimento Facial]: integrar reconhecimento facial
    # para validação de identidade em operações de maior risco.

    return repo.criar_usuario(
        nome=nome,
        carteira_id=carteira_id,
        saldo_inicial=saldo_inicial,
    )


def login_basico(repo: MemoriaRepository, carteira_id: int) -> dict:
    usuario = repo.obter_usuario(carteira_id)

    if not usuario:
        raise HTTPException(
            status_code=404,
            detail="Carteira não encontrada. Crie a conta primeiro.",
        )

    # TODO FUTURO [MFA]: substituir este login simples por autenticação
    # com senha + segundo fator (MFA).
    #
    # TODO FUTURO [Reconhecimento Facial]: adicionar reconhecimento facial
    # como fator adicional de autenticação.
    #
    # TODO FUTURO [Liveness Detection]: executar prova de vida durante
    # uma autenticação biométrica.
    #
    # TODO FUTURO [Azure DB]: buscar o usuário em Azure Cosmos DB ou
    # Azure SQL Database em vez do repositório em memória.

    return usuario
