from fastapi import APIRouter, Depends, HTTPException, Query

from app.deps import admin_atual, get_repo, ip_cliente, usuario_atual
from app.repositories.repository import Repositorio
from app.schemas.usuario import ContaCreate, ContaResponse
from app.services import usuario_service

router = APIRouter(prefix="/usuarios", tags=["usuarios"])


@router.post("", response_model=ContaResponse, status_code=201)
def registrar(dados: ContaCreate, repo: Repositorio = Depends(get_repo), ip: str | None = Depends(ip_cliente)):
    """Cadastro público: cria a conta (saldo zero), a carteira e a biometria."""
    return usuario_service.criar_conta(
        repo,
        nome=dados.nome,
        email=dados.email,
        senha=dados.senha,
        tipo=dados.tipo,
        documento=dados.documento,
        foto_rosto_base64=dados.foto_rosto_base64,
        carteira_id=dados.carteira_id,
        ip=ip,
    )


@router.get("/eu", response_model=ContaResponse)
def minha_conta(usuario: dict = Depends(usuario_atual), repo: Repositorio = Depends(get_repo)):
    conta = repo.obter_carteira_do_usuario(usuario["id"])
    if not conta:
        raise HTTPException(status_code=404, detail="Carteira não encontrada.")
    return conta


@router.get("", response_model=list[ContaResponse])
def listar(
    _: dict = Depends(admin_atual),  # só admin vê a lista completa (com saldos)
    repo: Repositorio = Depends(get_repo),
    limite: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    return usuario_service.listar_contas(repo, limite=limite, offset=offset)


@router.get("/{carteira_id}")
def consultar(
    carteira_id: int,
    usuario: dict = Depends(usuario_atual),
    repo: Repositorio = Depends(get_repo),
):
    """Consulta uma carteira. O SALDO só aparece para o dono ou para admin --
    para os demais, devolve apenas o mínimo para exibir o destinatário numa
    transferência (fecha o item #1: antes qualquer um via o saldo de todos)."""
    conta = usuario_service.obter_conta_ou_404(repo, carteira_id)
    dono = conta["usuario_id"] == usuario["id"]
    if dono or usuario["papel"] == "admin":
        return conta
    return {"carteira_id": conta["carteira_id"], "nome": conta["nome"], "tipo": conta["tipo"]}
