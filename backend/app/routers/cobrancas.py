"""Cobranças (onde o split acontece) e Pix Automático."""

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from app.core.documentos import mascarar_cnpj, mascarar_cpf
from app.deps import (chave_idempotencia, conta_atual, dispositivo_atual, escolher_chave, exigir_pj, get_repo,
                      ip_cliente, usuario_atual)
from app.repositories.repository import Repositorio
from app.routers.pagamentos import resposta_pendente
from app.schemas.comum import PendenteResponse, TransacaoResponse
from app.schemas.pagamentos import (
    AutorizacaoCreate,
    AutorizacaoResponse,
    CobrancaCreate,
    CobrancaRecorrenteCreate,
    CobrancaResponse,
    PagarCobranca,
)
from app.services import cobranca_service

router = APIRouter(tags=["cobrancas"])


@router.post("/cobrancas", response_model=list[CobrancaResponse], status_code=201)
def criar_cobranca(
    dados: CobrancaCreate,
    usuario: dict = Depends(usuario_atual),
    conta: dict = Depends(conta_atual),
    repo: Repositorio = Depends(get_repo),
    ip: str | None = Depends(ip_cliente),
):
    """PJ cobra um cliente. Com `nota_fiscal`, o pagamento retém a CBS e o IBS
    destacados na nota (empresa do regime regular). Com `parcelas`, gera uma
    cobrança por mês."""
    return [cobranca_service.para_resposta(c) for c in cobranca_service.criar(repo, usuario=usuario, conta=conta, dados=dados, ip=ip)]


@router.get("/cobrancas", response_model=list[CobrancaResponse])
def listar_cobrancas(
    conta: dict = Depends(conta_atual),
    repo: Repositorio = Depends(get_repo),
    status: str | None = None,
    limite: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    exigir_pj(conta)
    return [cobranca_service.para_resposta(c) for c in repo.listar_cobrancas(conta["carteira_id"], status=status, limite=limite, offset=offset)]


@router.get("/cobrancas/{txid}", response_model=CobrancaResponse)
def ver_cobranca(txid: str, usuario: dict = Depends(usuario_atual), repo: Repositorio = Depends(get_repo)):
    """O que o pagador vê antes de pagar (quem cobra, valor, imposto que será retido).

    Quem tem o txid (QR/copia e cola) vê a cobrança, como no Pix. Mas só quem cobra e o
    próprio pagador veem o documento do pagador e os ids internos (SECURITY_AUDIT.md A-10)."""
    c = repo.obter_cobranca(txid=txid)
    if not c:
        raise HTTPException(status_code=404, detail="Cobrança não encontrada.")
    resposta = cobranca_service.para_resposta(c)
    empresa = c["recebedor"].get("empresa_id")
    e_quem_cobra = empresa is not None and repo.obter_vinculo(usuario["id"], empresa) is not None
    e_o_pagador = bool(c["pagador_documento"]) and c["pagador_documento"] == usuario.get("cpf")
    if not (e_quem_cobra or e_o_pagador):
        doc = c["pagador_documento"]
        resposta.update(
            pagador_documento=(mascarar_cnpj(doc) if len(doc) == 14 else mascarar_cpf(doc)) if doc else None,
            transacao_id=None, autorizacao_id=None, grupo_parcelamento=None,
        )
    return resposta


@router.post("/cobrancas/{txid}/pagar", response_model=TransacaoResponse, responses={202: {"model": PendenteResponse}})
def pagar_cobranca(
    txid: str,
    dados: PagarCobranca,
    usuario: dict = Depends(usuario_atual),
    conta: dict = Depends(conta_atual),
    dispositivo: dict | None = Depends(dispositivo_atual),
    repo: Repositorio = Depends(get_repo),
    ip: str | None = Depends(ip_cliente),
    chave_header: str | None = Depends(chave_idempotencia),
):
    r = cobranca_service.pagar(repo, usuario=usuario, conta=conta, dispositivo=dispositivo, txid=txid,
                               biometria=dados.biometria, idempotency_key=escolher_chave(chave_header, dados.idempotency_key), ip=ip)
    return resposta_pendente(r["pendente"]) if "pendente" in r else r["transacao"]


@router.post("/cobrancas/{txid}/cancelar", status_code=204)
def cancelar_cobranca(txid: str, usuario: dict = Depends(usuario_atual), conta: dict = Depends(conta_atual),
                      repo: Repositorio = Depends(get_repo), ip: str | None = Depends(ip_cliente)):
    cobranca_service.cancelar(repo, usuario=usuario, conta=conta, txid=txid, ip=ip)
    return Response(status_code=204)


@router.post("/cobrancas/{txid}/estornar", response_model=TransacaoResponse)
def estornar_cobranca(txid: str, usuario: dict = Depends(usuario_atual), conta: dict = Depends(conta_atual),
                      repo: Repositorio = Depends(get_repo), ip: str | None = Depends(ip_cliente)):
    """Devolve o valor ao pagador (nota cancelada / devolução). O imposto ainda
    não repassado volta da conta de tributos; o já repassado vira crédito informado."""
    return cobranca_service.estornar(repo, usuario=usuario, conta=conta, txid=txid, ip=ip)


# ---------------------------------------------------------------- Pix Automático


@router.post("/pix-automatico/autorizacoes", response_model=AutorizacaoResponse, status_code=201)
def solicitar_autorizacao(dados: AutorizacaoCreate, usuario: dict = Depends(usuario_atual), conta: dict = Depends(conta_atual),
                          repo: Repositorio = Depends(get_repo), ip: str | None = Depends(ip_cliente)):
    """A empresa pede ao cliente autorização para cobranças recorrentes."""
    return cobranca_service.criar_autorizacao(repo, usuario=usuario, conta=conta, dados=dados, ip=ip)


@router.get("/pix-automatico/autorizacoes", response_model=list[AutorizacaoResponse])
def listar_autorizacoes(conta: dict = Depends(conta_atual), repo: Repositorio = Depends(get_repo)):
    return repo.listar_autorizacoes(conta["carteira_id"])


@router.post("/pix-automatico/autorizacoes/{autorizacao_id}/aceitar", response_model=AutorizacaoResponse)
def aceitar_autorizacao(autorizacao_id: int, usuario: dict = Depends(usuario_atual), conta: dict = Depends(conta_atual),
                        dispositivo: dict | None = Depends(dispositivo_atual), repo: Repositorio = Depends(get_repo),
                        ip: str | None = Depends(ip_cliente)):
    return cobranca_service.responder_autorizacao(repo, usuario=usuario, conta=conta, dispositivo=dispositivo,
                                                  autorizacao_id=autorizacao_id, aceitar=True, ip=ip)


@router.post("/pix-automatico/autorizacoes/{autorizacao_id}/recusar", response_model=AutorizacaoResponse)
def recusar_autorizacao(autorizacao_id: int, usuario: dict = Depends(usuario_atual), conta: dict = Depends(conta_atual),
                        dispositivo: dict | None = Depends(dispositivo_atual), repo: Repositorio = Depends(get_repo),
                        ip: str | None = Depends(ip_cliente)):
    return cobranca_service.responder_autorizacao(repo, usuario=usuario, conta=conta, dispositivo=dispositivo,
                                                  autorizacao_id=autorizacao_id, aceitar=False, ip=ip)


@router.post("/pix-automatico/autorizacoes/{autorizacao_id}/cancelar", response_model=AutorizacaoResponse)
def cancelar_autorizacao(autorizacao_id: int, usuario: dict = Depends(usuario_atual), conta: dict = Depends(conta_atual),
                         repo: Repositorio = Depends(get_repo), ip: str | None = Depends(ip_cliente)):
    return cobranca_service.cancelar_autorizacao(repo, usuario=usuario, conta=conta, autorizacao_id=autorizacao_id, ip=ip)


@router.post("/pix-automatico/autorizacoes/{autorizacao_id}/cobrancas", response_model=CobrancaResponse, status_code=201)
def cobrar_recorrente(autorizacao_id: int, dados: CobrancaRecorrenteCreate, usuario: dict = Depends(usuario_atual),
                      conta: dict = Depends(conta_atual), repo: Repositorio = Depends(get_repo),
                      ip: str | None = Depends(ip_cliente)):
    c = cobranca_service.cobrar_recorrente(repo, usuario=usuario, conta=conta, autorizacao_id=autorizacao_id, dados=dados, ip=ip)
    return cobranca_service.para_resposta(c)
