"""Limites, aparelhos, chaves Pix, tributos da empresa, créditos e webhooks."""

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from app.db.models import PapelVinculo
from app.deps import (
    conta_atual,
    dispositivo_atual,
    exigir_papel,
    exigir_pj,
    get_repo,
    ip_cliente,
    usuario_atual,
)
from app.repositories.repository import Repositorio
from app.schemas.comum import ProvaBiometrica
from app.schemas.pagamentos import ChaveCreate, CreditoCreate, LimiteUpdate, WebhookCreate
from app.services import pix_service, rendimento_service, seguranca_service, tributos_service, webhook_service

router = APIRouter(tags=["seguranca"])


# ------------------------------------------------------------------ limites


@router.get("/seguranca/limites")
def ver_limites(conta: dict = Depends(conta_atual), repo: Repositorio = Depends(get_repo)):
    lim = repo.obter_limite(conta["carteira_id"])
    if lim is None:
        raise HTTPException(status_code=404, detail="Conta sem limites configurados.")
    return lim


@router.put("/seguranca/limites")
def alterar_limites(dados: LimiteUpdate, usuario: dict = Depends(usuario_atual), conta: dict = Depends(conta_atual),
                    repo: Repositorio = Depends(get_repo), ip: str | None = Depends(ip_cliente)):
    """Reduzir vale na hora. Aumentar fica agendado (carência de LIMITE_CARENCIA_HORAS)."""
    exigir_papel(conta, PapelVinculo.ADMIN)
    r = seguranca_service.atualizar_limites(repo, conta=conta, novos=dados.model_dump())
    repo.registrar_log(ator=usuario["email"], acao="limites_alterados", ip=ip, usuario_id=usuario["id"], empresa_id=conta.get("empresa_id"),
                       detalhe={"carteira_id": conta["carteira_id"], **{k: str(v) for k, v in dados.model_dump().items() if v is not None}})
    return r


# ------------------------------------------------------------------ aparelhos


@router.get("/seguranca/dispositivos")
def listar_dispositivos(usuario: dict = Depends(usuario_atual), repo: Repositorio = Depends(get_repo)):
    return repo.listar_dispositivos(usuario["id"])


@router.get("/seguranca/dispositivos/atual")
def aparelho_atual(dispositivo: dict | None = Depends(dispositivo_atual)):
    """O aparelho do header X-Dispositivo-Id e se ele já é confiável."""
    if dispositivo is None:
        raise HTTPException(status_code=400, detail="Envie o header X-Dispositivo-Id.")
    return dispositivo


@router.post("/seguranca/dispositivos/atual/confiar")
def confiar_aparelho(prova: ProvaBiometrica, usuario: dict = Depends(usuario_atual),
                     dispositivo: dict | None = Depends(dispositivo_atual), repo: Repositorio = Depends(get_repo),
                     ip: str | None = Depends(ip_cliente)):
    """Confirma este aparelho com verificação facial e libera os limites normais."""
    return seguranca_service.confiar_dispositivo(repo, usuario=usuario, dispositivo=dispositivo, prova=prova, ip=ip)


@router.delete("/seguranca/dispositivos/{dispositivo_id}", status_code=204)
def remover_aparelho(dispositivo_id: int, usuario: dict = Depends(usuario_atual), repo: Repositorio = Depends(get_repo),
                     ip: str | None = Depends(ip_cliente)):
    repo.revogar_sessoes_do_dispositivo(usuario["id"], dispositivo_id)
    if not repo.remover_dispositivo(usuario["id"], dispositivo_id):
        raise HTTPException(status_code=404, detail="Aparelho não encontrado.")
    repo.registrar_log(ator=usuario["email"], acao="dispositivo_removido", ip=ip, usuario_id=usuario["id"],
                       detalhe={"dispositivo_id": dispositivo_id})
    return Response(status_code=204)


@router.post("/seguranca/dispositivos/{dispositivo_id}/bloquear")
def bloquear_aparelho(dispositivo_id: int, usuario: dict = Depends(usuario_atual), repo: Repositorio = Depends(get_repo),
                      ip: str | None = Depends(ip_cliente)):
    """Celular perdido/roubado: o aparelho deixa de ser confiável, TODAS as sessões
    dele caem na hora e novos logins nele são recusados."""
    d = repo.bloquear_dispositivo(usuario["id"], dispositivo_id)
    if d is None:
        raise HTTPException(status_code=404, detail="Aparelho não encontrado.")
    n = repo.revogar_sessoes_do_dispositivo(usuario["id"], dispositivo_id)
    repo.registrar_log(ator=usuario["email"], acao="dispositivo_bloqueado", ip=ip, usuario_id=usuario["id"],
                       detalhe={"dispositivo_id": dispositivo_id, "sessoes_encerradas": n})
    return {**d, "sessoes_encerradas": n}


@router.post("/seguranca/dispositivos/{dispositivo_id}/desbloquear")
def desbloquear_aparelho(dispositivo_id: int, prova: ProvaBiometrica, usuario: dict = Depends(usuario_atual),
                         repo: Repositorio = Depends(get_repo), ip: str | None = Depends(ip_cliente)):
    """Exige o rosto. O aparelho volta como NÃO confiável (precisa de um login com rosto nele)."""
    seguranca_service.verificar_rosto(repo, usuario=usuario, prova=prova, ip=ip, tipo="desbloquear_dispositivo")
    d = repo.desbloquear_dispositivo(usuario["id"], dispositivo_id)
    if d is None:
        raise HTTPException(status_code=404, detail="Aparelho não encontrado.")
    repo.registrar_log(ator=usuario["email"], acao="dispositivo_desbloqueado", ip=ip, usuario_id=usuario["id"],
                       detalhe={"dispositivo_id": dispositivo_id})
    return d


# ------------------------------------------------------------------ atividade e auditoria


@router.get("/seguranca/atividade")
def minha_atividade(usuario: dict = Depends(usuario_atual), repo: Repositorio = Depends(get_repo),
                    limite: int = Query(default=50, ge=1, le=200)):
    """O que eu fiz (logins, aparelhos, pagamentos, aprovações...)."""
    return repo.listar_auditoria(usuario_id=usuario["id"], limite=limite)


@router.get("/empresas/atual/auditoria")
def auditoria_da_empresa(conta: dict = Depends(conta_atual), repo: Repositorio = Depends(get_repo),
                         limite: int = Query(default=100, ge=1, le=200)):
    """Trilha da empresa: quem convidou quem, quem mudou alçada, quem lançou e quem
    aprovou cada pagamento. Admin e aprovador."""
    exigir_pj(conta)
    exigir_papel(conta, PapelVinculo.ADMIN, PapelVinculo.APROVADOR)
    return repo.listar_auditoria(empresa_id=conta["empresa_id"], limite=limite)


# ------------------------------------------------------------------ chaves Pix


@router.get("/pix/chaves")
def minhas_chaves(conta: dict = Depends(conta_atual), repo: Repositorio = Depends(get_repo)):
    return repo.listar_chaves(conta["carteira_id"])


@router.post("/pix/chaves", status_code=201)
def criar_chave(dados: ChaveCreate, usuario: dict = Depends(usuario_atual), conta: dict = Depends(conta_atual),
                repo: Repositorio = Depends(get_repo), ip: str | None = Depends(ip_cliente)):
    exigir_papel(conta, PapelVinculo.ADMIN)
    return pix_service.criar_chave(repo, conta=conta, tipo=dados.tipo, valor=dados.valor, ip=ip, autor=usuario)


@router.delete("/pix/chaves/{chave_id}", status_code=204)
def remover_chave(chave_id: int, conta: dict = Depends(conta_atual), repo: Repositorio = Depends(get_repo)):
    exigir_papel(conta, PapelVinculo.ADMIN)
    if not repo.remover_chave(conta["carteira_id"], chave_id):
        raise HTTPException(status_code=404, detail="Chave não encontrada.")
    return Response(status_code=204)


@router.get("/pix/consultar/{chave}")
def consultar_chave(chave: str, usuario: dict = Depends(usuario_atual), repo: Repositorio = Depends(get_repo),
                    ip: str | None = Depends(ip_cliente)):
    """Quem é o dono da chave: nome e documento mascarados, como no Pix."""
    return pix_service.consultar(repo, usuario=usuario, chave=chave, ip=ip)


# ------------------------------------------------------------------ empresa: tributos, créditos, webhooks


@router.get("/empresas/atual/tributos")
def tributos_da_empresa(conta: dict = Depends(conta_atual), repo: Repositorio = Depends(get_repo)):
    exigir_pj(conta)
    return tributos_service.resumo_empresa(repo, conta)


@router.get("/empresas/atual/creditos")
def creditos(conta: dict = Depends(conta_atual), repo: Repositorio = Depends(get_repo)):
    exigir_pj(conta)
    return repo.listar_creditos(conta["empresa_id"])


@router.post("/empresas/atual/creditos", status_code=201)
def declarar_credito(dados: CreditoCreate, usuario: dict = Depends(usuario_atual), conta: dict = Depends(conta_atual),
                     repo: Repositorio = Depends(get_repo), ip: str | None = Depends(ip_cliente)):
    """A empresa informa um crédito de IBS/CBS (ex.: apurado pelo contador). É
    informação para a estimativa de restituição, não dinheiro."""
    exigir_pj(conta)
    exigir_papel(conta, PapelVinculo.ADMIN)
    c = repo.registrar_credito(empresa_id=conta["empresa_id"], tributo=dados.tributo, valor=dados.valor,
                               fonte="declarado", referencia=dados.referencia)
    repo.registrar_log(ator=usuario["email"], acao="credito_declarado", ip=ip, usuario_id=usuario["id"], empresa_id=conta.get("empresa_id"), detalhe={"credito_id": c["id"]})
    return c


@router.get("/empresas/atual/webhooks")
def listar_webhooks(conta: dict = Depends(conta_atual), repo: Repositorio = Depends(get_repo)):
    exigir_pj(conta)
    exigir_papel(conta, PapelVinculo.ADMIN)
    return repo.listar_webhooks(conta["empresa_id"])


@router.post("/empresas/atual/webhooks", status_code=201)
def criar_webhook(dados: WebhookCreate, conta: dict = Depends(conta_atual), repo: Repositorio = Depends(get_repo)):
    """Cadastra uma URL https do ERP. O `segredo` (para conferir a assinatura) só aparece nesta resposta."""
    exigir_pj(conta)
    exigir_papel(conta, PapelVinculo.ADMIN)
    return webhook_service.criar(repo, empresa_id=conta["empresa_id"], url=dados.url, eventos=dados.eventos)


@router.delete("/empresas/atual/webhooks/{webhook_id}", status_code=204)
def remover_webhook(webhook_id: int, conta: dict = Depends(conta_atual), repo: Repositorio = Depends(get_repo)):
    exigir_pj(conta)
    exigir_papel(conta, PapelVinculo.ADMIN)
    if not repo.desativar_webhook(conta["empresa_id"], webhook_id):
        raise HTTPException(status_code=404, detail="Webhook não encontrado.")
    return Response(status_code=204)


@router.get("/empresas/atual/webhooks/entregas")
def entregas(conta: dict = Depends(conta_atual), repo: Repositorio = Depends(get_repo)):
    exigir_pj(conta)
    exigir_papel(conta, PapelVinculo.ADMIN)
    return repo.listar_entregas(conta["empresa_id"])


# ------------------------------------------------------------------ rendimento


@router.get("/rendimento")
def meu_rendimento(conta: dict = Depends(conta_atual), repo: Repositorio = Depends(get_repo)):
    return {"taxa_diaria": rendimento_service.taxa_diaria(), "historico": repo.listar_rendimentos(conta["carteira_id"])}
