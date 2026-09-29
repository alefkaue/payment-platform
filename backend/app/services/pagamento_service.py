from fastapi import HTTPException

from app.repositories import Repositorio
from app.repositories.exceptions import SaldoInsuficienteError
from app.services import biometria_service


def realizar_transferencia(
    repo: Repositorio,
    origem_carteira_id: int,
    destino_carteira_id: int,
    valor: float,
    foto_verificacao_base64: str,
) -> dict:
    # 1) Validações baratas primeiro (mesmo raciocínio do usuario_service: nada de
    # gastar ~5s de DeepFace numa requisição que já falharia por outro motivo).
    if valor <= 0:
        raise HTTPException(status_code=400, detail="O valor deve ser maior que zero.")
    if origem_carteira_id == destino_carteira_id:
        raise HTTPException(status_code=400, detail="Não é possível transferir para si mesmo.")

    usuario_origem = repo.obter_usuario(origem_carteira_id)
    usuario_destino = repo.obter_usuario(destino_carteira_id)

    if not usuario_origem:
        raise HTTPException(status_code=404, detail="Carteira de origem não encontrada.")
    if not usuario_destino:
        raise HTTPException(status_code=404, detail="Carteira de destino não encontrada.")

    # 2) MFA - Liveness Detection + Reconhecimento Facial (implementado):
    # antes de saber se há saldo, confirma QUEM está autorizando. Assim quem manda
    # uma foto qualquer não descobre "saldo insuficiente" de uma carteira que não é
    # dele -- a identidade é checada primeiro.
    embedding_origem = repo.obter_embedding_facial(origem_carteira_id)
    if embedding_origem is None:
        # Defensivo: não deveria acontecer, já que toda conta cadastra biometria
        # na criação -- mas se acontecer (ex: dado corrompido), falha com clareza
        # em vez de deixar a transferência passar sem MFA.
        raise HTTPException(
            status_code=400,
            detail="Carteira de origem não possui biometria cadastrada. Transferência bloqueada.",
        )

    verificacao_facial = biometria_service.verificar_biometria(
        foto_verificacao_base64, embedding_origem
    )

    # TODO[SPLIT PAYMENT - CNPJ]: quando o motor de split entrar, a transferência
    # deixa de ser 1:1 e passa a poder ratear `valor` entre N carteiras de destino
    # identificadas por CNPJ (ex: marketplace repassando % ao vendedor + % de
    # comissão à plataforma). Ponto de entrada: em vez de um único
    # destino_carteira_id, receber uma lista de (cnpj/carteira_id, percentual ou
    # valor fixo), validar que a soma bate com `valor`, e criar um
    # SplitLiquidacao por participante (tabela já existe em app/db/models.py,
    # motor de cálculo ainda não). O MFA acima já corre 1x por transferência,
    # antes do split -- não precisa repetir por destinatário.

    # 3) Checagem de saldo + débito + crédito + registro da transação, tudo numa
    # operação atômica só (lock em memória / SELECT...FOR UPDATE no Postgres --
    # ver executar_transferencia nos dois repositórios). Antes essa checagem
    # rodava aqui no service usando um saldo já lido antes do MFA -- duas
    # transferências simultâneas da mesma carteira podiam ambas passar. Agora
    # não tem mais essa janela.
    #
    # TODO[IDEMPOTENCIA]: um double-click no botão "Transferir" ainda gera 2
    # transações (e cobra o MFA duas vezes) -- precisa de uma chave de
    # idempotência por requisição pra resolver, isso é independente do lock
    # acima (o lock impede saldo errado, não impede duplicar a intenção).
    try:
        return repo.executar_transferencia(
            origem_carteira_id, destino_carteira_id, valor, verificacao_facial
        )
    except SaldoInsuficienteError:
        raise HTTPException(status_code=400, detail="Saldo insuficiente.")
