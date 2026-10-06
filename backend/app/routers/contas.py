"""Cadastro de pessoa, contas, empresas e vínculos."""

from fastapi import APIRouter, Depends, Header, HTTPException, Response

from app.db.models import PapelVinculo
from app.deps import conta_atual, exigir_papel, exigir_pj, get_repo, hash_dispositivo, ip_cliente, usuario_atual
from app.repositories.repository import Repositorio
from app.schemas.comum import ContaResponse
from app.schemas.contas import EmpresaCreate, EmpresaResponse, PessoaCreate, VinculoCreate, VinculoResponse
from app.services import contas_service

router = APIRouter(tags=["contas"])


@router.post("/usuarios", response_model=ContaResponse, status_code=201)
def cadastrar_pessoa(
    dados: PessoaCreate,
    repo: Repositorio = Depends(get_repo),
    ip: str | None = Depends(ip_cliente),
    x_dispositivo_id: str | None = Header(default=None, max_length=128),
):
    """Cadastro público da pessoa: conta PF com saldo zero + biometria com desafio
    (peça antes um desafio em POST /biometria/desafios)."""
    return contas_service.criar_pessoa(
        repo, nome=dados.nome, email=dados.email, senha=dados.senha, cpf=dados.cpf, prova=dados.biometria,
        dispositivo_hash=hash_dispositivo(x_dispositivo_id) if x_dispositivo_id else None, ip=ip,
    )


@router.get("/contas", response_model=list[ContaResponse])
def minhas_contas(usuario: dict = Depends(usuario_atual), repo: Repositorio = Depends(get_repo)):
    """Contas que a pessoa pode operar: a PF e as das empresas em que tem vínculo."""
    return repo.contas_do_usuario(usuario["id"])


@router.get("/contas/atual", response_model=ContaResponse)
def conta_em_uso(conta: dict = Depends(conta_atual)):
    """Saldo e dados da conta em uso (PF, ou a PJ do header X-Conta)."""
    v = conta.get("vinculo")
    return {**conta, "papel": v["papel"] if v else None, "alcada": v["alcada"] if v else None}


@router.post("/empresas", response_model=ContaResponse, status_code=201)
def abrir_empresa(
    dados: EmpresaCreate,
    usuario: dict = Depends(usuario_atual),
    repo: Repositorio = Depends(get_repo),
    ip: str | None = Depends(ip_cliente),
):
    conta = contas_service.criar_empresa(
        repo, usuario=usuario, cnpj=dados.cnpj, razao_social=dados.razao_social, nome_fantasia=dados.nome_fantasia,
        porte=dados.porte, regime=dados.regime_apuracao, ip=ip,
    )
    return {**conta, "papel": "admin", "alcada": None}


@router.get("/empresas/atual", response_model=EmpresaResponse)
def empresa_em_uso(conta: dict = Depends(conta_atual), repo: Repositorio = Depends(get_repo)):
    exigir_pj(conta)
    return repo.obter_empresa(conta["empresa_id"])


@router.get("/empresas/atual/vinculos", response_model=list[VinculoResponse])
def listar_vinculos(conta: dict = Depends(conta_atual), repo: Repositorio = Depends(get_repo)):
    exigir_pj(conta)
    exigir_papel(conta, PapelVinculo.ADMIN, PapelVinculo.APROVADOR)
    return repo.listar_vinculos(conta["empresa_id"])


@router.post("/empresas/atual/vinculos", response_model=VinculoResponse, status_code=201)
def definir_vinculo(
    dados: VinculoCreate,
    usuario: dict = Depends(usuario_atual),
    conta: dict = Depends(conta_atual),
    repo: Repositorio = Depends(get_repo),
    ip: str | None = Depends(ip_cliente),
):
    """Adiciona (ou atualiza papel/alçada de) uma pessoa na empresa. Só ADMIN."""
    exigir_pj(conta)
    exigir_papel(conta, PapelVinculo.ADMIN)
    return contas_service.adicionar_vinculo(repo, conta=conta, autor=usuario, email=dados.email, papel=dados.papel,
                                            alcada=dados.alcada, ip=ip)


@router.delete("/empresas/atual/vinculos/{vinculo_id}", status_code=204)
def remover_vinculo(
    vinculo_id: int,
    usuario: dict = Depends(usuario_atual),
    conta: dict = Depends(conta_atual),
    repo: Repositorio = Depends(get_repo),
    ip: str | None = Depends(ip_cliente),
):
    exigir_pj(conta)
    exigir_papel(conta, PapelVinculo.ADMIN)
    contas_service.remover_vinculo(repo, conta=conta, autor=usuario, vinculo_id=vinculo_id, ip=ip)
    return Response(status_code=204)


@router.get("/empresas/atual/pendentes")
def operacoes_pendentes(conta: dict = Depends(conta_atual), repo: Repositorio = Depends(get_repo), status: str | None = "pendente"):
    exigir_pj(conta)
    if conta["vinculo"]["papel"] == PapelVinculo.CONSULTA.value:
        raise HTTPException(status_code=403, detail="Seu papel não permite ver operações pendentes.")
    return repo.listar_pendentes(conta["empresa_id"], status=status)
