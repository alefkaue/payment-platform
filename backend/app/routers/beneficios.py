"""Loja, Viagens e pontos (benefícios da conta PF).

DESLIGADO por padrão (BENEFICIOS_HABILITADOS=0): todas as rotas respondem 404.
As telas estão arquivadas em app/src/_arquivado/beneficios (ver o README de lá)."""

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.config import get_settings
from app.deps import conta_atual, dispositivo_atual, get_repo, ip_cliente, usuario_atual
from app.repositories.repository import Repositorio
from app.schemas.comum import ProvaBiometrica, TransacaoResponse
from app.services import beneficios_service

def _beneficios_ligados() -> None:
    if not get_settings().beneficios_habilitados:
        raise HTTPException(status_code=404, detail="Not Found")


router = APIRouter(tags=["beneficios"], dependencies=[Depends(_beneficios_ligados)])


class Produto(BaseModel):
    id: int
    nome: str
    descricao: str
    preco: Decimal
    categoria: str
    emoji: str
    merchant_carteira_id: int
    merchant_nome: str


class Voo(BaseModel):
    id: int
    origem: str
    origemCidade: str
    destino: str
    destinoCidade: str
    companhia: str
    saida: str
    chegada: str
    duracao: str
    direto: bool
    preco: Decimal
    milhas: int
    merchant_carteira_id: int
    merchant_nome: str


class Compra(BaseModel):
    biometria: ProvaBiometrica | None = None


class CompraResponse(BaseModel):
    transacao: TransacaoResponse
    pontos_ganhos: int
    saldo_pontos: int


class ResgateResponse(BaseModel):
    localizador: str
    voo: Voo
    pontos_usados: int
    saldo_pontos: int


@router.get("/loja/produtos", response_model=list[Produto])
def produtos(_: dict = Depends(usuario_atual), repo: Repositorio = Depends(get_repo)):
    return repo.listar_produtos()


@router.get("/loja/produtos/{produto_id}", response_model=Produto)
def produto(produto_id: int, _: dict = Depends(usuario_atual), repo: Repositorio = Depends(get_repo)):
    p = repo.obter_produto(produto_id)
    if not p:
        raise HTTPException(status_code=404, detail="Produto não encontrado.")
    return p


@router.post("/loja/produtos/{produto_id}/comprar", response_model=CompraResponse)
def comprar_produto(produto_id: int, dados: Compra, usuario: dict = Depends(usuario_atual),
                    conta: dict = Depends(conta_atual), dispositivo: dict | None = Depends(dispositivo_atual),
                    repo: Repositorio = Depends(get_repo), ip: str | None = Depends(ip_cliente)):
    """Compra com o saldo. O lojista emite a nota: o imposto dela é separado no ato. Rende 1 ponto por real."""
    return beneficios_service.comprar_produto(repo, usuario=usuario, conta=conta, dispositivo=dispositivo,
                                              produto_id=produto_id, biometria=dados.biometria, ip=ip)


@router.get("/viagens/voos", response_model=list[Voo])
def voos(origem: str | None = None, destino: str | None = None, _: dict = Depends(usuario_atual),
         repo: Repositorio = Depends(get_repo)):
    return repo.listar_voos(origem=origem, destino=destino)


@router.get("/viagens/voos/{voo_id}", response_model=Voo)
def voo(voo_id: int, _: dict = Depends(usuario_atual), repo: Repositorio = Depends(get_repo)):
    v = repo.obter_voo(voo_id)
    if not v:
        raise HTTPException(status_code=404, detail="Voo não encontrado.")
    return v


@router.post("/viagens/voos/{voo_id}/comprar", response_model=CompraResponse)
def comprar_voo(voo_id: int, dados: Compra, usuario: dict = Depends(usuario_atual),
                conta: dict = Depends(conta_atual), dispositivo: dict | None = Depends(dispositivo_atual),
                repo: Repositorio = Depends(get_repo), ip: str | None = Depends(ip_cliente)):
    """Passagem paga em reais (rende 1 ponto por real)."""
    return beneficios_service.comprar_voo(repo, usuario=usuario, conta=conta, dispositivo=dispositivo,
                                          voo_id=voo_id, biometria=dados.biometria, ip=ip)


@router.post("/viagens/voos/{voo_id}/resgatar", response_model=ResgateResponse)
def resgatar_voo(voo_id: int, usuario: dict = Depends(usuario_atual), conta: dict = Depends(conta_atual),
                 dispositivo: dict | None = Depends(dispositivo_atual), repo: Repositorio = Depends(get_repo),
                 ip: str | None = Depends(ip_cliente)):
    """Passagem com pontos: debita `milhas` pontos, sem mexer no saldo em reais."""
    return beneficios_service.resgatar_voo(repo, usuario=usuario, conta=conta, dispositivo=dispositivo,
                                           voo_id=voo_id, ip=ip)


@router.get("/pontos")
def meus_pontos(usuario: dict = Depends(usuario_atual), repo: Repositorio = Depends(get_repo)):
    return repo.extrato_pontos(usuario["id"])
