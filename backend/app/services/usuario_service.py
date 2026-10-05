"""
Cadastro e consulta de contas. Mudanças da v6 (auditoria):
- Conta agora nasce com SALDO ZERO. O `saldo_inicial` livre saiu (item #2: criava
  dinheiro do nada). Saldo entra só por depósito da conta Governo (ver
  deposito_service + admin).
- Conta tem credencial (e-mail + senha) e documento (CPF/CNPJ). A senha é hasheada
  (bcrypt) antes de chegar ao repositório.
- O embedding facial é CIFRADO (Fernet) antes de persistir (item #12 / LGPD).
- Cadastro + biometria gravam numa transação só no repositório (item #10:
  atomicidade -- não sobra mais conta sem biometria por falha no meio).
"""

import random

from fastapi import HTTPException

from app.core import security
from app.db.models import Papel, TipoPessoa
from app.repositories.exceptions import (
    DocumentoDuplicadoError,
    EmailDuplicadoError,
    IdDuplicadoError,
)
from app.repositories.repository import Repositorio
from app.services import biometria_service


def _gerar_carteira_id(repo: Repositorio) -> int:
    """Gera uma chave numérica livre quando o usuário não escolhe uma. Tenta
    algumas vezes; a unicidade real é garantida pela constraint no banco."""
    for _ in range(10):
        cid = random.randint(100000, 999999)
        if not repo.carteira_existe(cid):
            return cid
    raise HTTPException(status_code=503, detail="Não foi possível gerar um ID de carteira. Tente de novo.")


def criar_conta(
    repo: Repositorio,
    *,
    nome: str,
    email: str,
    senha: str,
    tipo: TipoPessoa,
    documento: str | None,
    foto_rosto_base64: str,
    carteira_id: int | None = None,
    ip: str | None = None,
) -> dict:
    # 1) Validações baratas antes de gastar ~5s no DeepFace.
    if tipo == TipoPessoa.GOV:
        raise HTTPException(status_code=400, detail="Conta Governo não é criada por este endpoint.")
    if carteira_id is not None and repo.carteira_existe(carteira_id):
        raise HTTPException(status_code=409, detail=f"Já existe uma carteira com o ID {carteira_id}.")
    if repo.obter_usuario_por_email(email):
        raise HTTPException(status_code=409, detail="Já existe uma conta com esse e-mail.")

    # 2) Biometria: valida liveness e extrai o embedding (texto puro); cifra em seguida.
    embedding = biometria_service.cadastrar_biometria(foto_rosto_base64)
    embedding_cifrado = security.cifrar_embedding(embedding)

    senha_hash = security.hash_senha(senha)
    cid = carteira_id if carteira_id is not None else _gerar_carteira_id(repo)

    # 3) Cria conta + carteira + biometria numa transação só.
    try:
        conta = repo.criar_conta(
            carteira_id=cid,
            nome=nome,
            email=email,
            senha_hash=senha_hash,
            tipo=tipo,
            documento=documento,
            embedding_cifrado=embedding_cifrado,
            papel=Papel.USUARIO,
        )
    except IdDuplicadoError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except EmailDuplicadoError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except DocumentoDuplicadoError as e:
        raise HTTPException(status_code=409, detail=str(e))

    repo.registrar_sessao_mfa(tipo="cadastro", sucesso=True, usuario_id=conta["usuario_id"], ip=ip)
    repo.registrar_log(ator=email.lower().strip(), acao="criar_conta", ip=ip, detalhe={"carteira_id": cid, "tipo": tipo.value})
    return conta


def obter_conta_ou_404(repo: Repositorio, carteira_id: int) -> dict:
    conta = repo.obter_conta_por_carteira(carteira_id)
    if not conta:
        raise HTTPException(status_code=404, detail="Carteira não encontrada.")
    return conta


def listar_contas(repo: Repositorio, *, limite: int, offset: int) -> list[dict]:
    return repo.listar_contas(limite=limite, offset=offset)
