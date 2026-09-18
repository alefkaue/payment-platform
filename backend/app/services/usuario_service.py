"""
Regras de negócio para criação e consulta de usuários/carteiras.
"""

from fastapi import HTTPException

from app.repositories.memoria_repository import MemoriaRepository
from app.services import biometria_service


def criar_usuario(
    repo: MemoriaRepository,
    carteira_id: int,
    nome: str,
    foto_rosto_base64: str,
    saldo_inicial: float = 0.0,
) -> dict:
    # 1) Validações baratas primeiro -- rejeita antes de gastar ~5s processando a
    # foto com o DeepFace (liveness + extração do rosto).
    if repo.carteira_existe(carteira_id):
        raise HTTPException(
            status_code=409,
            detail=f"Já existe uma carteira com o ID {carteira_id}.",
        )

    if saldo_inicial < 0:
        raise HTTPException(status_code=400, detail="Saldo inicial não pode ser negativo.")

    # 2) MFA - Liveness Detection + Reconhecimento Facial (implementado):
    # `cadastrar_biometria` valida que a foto tem exatamente 1 rosto real (não é
    # foto de foto/tela) e devolve o embedding facial -- nunca a imagem em si.
    # Levanta HTTPException (400/401) se liveness ou detecção falharem.
    embedding = biometria_service.cadastrar_biometria(foto_rosto_base64)

    # TODO[AZURE - Persistencia]: quando o MemoriaRepository for trocado por um
    # repositório real (Azure Cosmos DB / Azure SQL Database), este service não
    # muda -- só a implementação injetada via `get_repository()`. O embedding
    # facial deveria ir para um datastore separado dos dados da conta (ver
    # comentário em `memoria_repository.py`), idealmente com o vetor criptografado
    # em repouso -- é dado biométrico, "dado sensível" pela LGPD (art. 5º, XIII).
    usuario = repo.criar_usuario(carteira_id=carteira_id, nome=nome, saldo_inicial=saldo_inicial)
    repo.salvar_embedding_facial(carteira_id, embedding)
    return usuario


def obter_usuario_ou_404(repo: MemoriaRepository, carteira_id: int) -> dict:
    usuario = repo.obter_usuario(carteira_id)
    if not usuario:
        raise HTTPException(status_code=404, detail="Carteira não encontrada.")
    return usuario


def listar_usuarios(repo: MemoriaRepository) -> list[dict]:
    return repo.listar_usuarios()
