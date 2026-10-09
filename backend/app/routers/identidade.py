"""Verificação de identidade da pessoa logada (KYC): status e reenvio de documento."""

from fastapi import APIRouter, Depends, HTTPException

from app.core import security
from app.deps import get_repo, ip_cliente, usuario_atual
from app.repositories.repository import Repositorio
from app.schemas.contas import DocumentoIdentidadeEnvio
from app.services import documento_service

router = APIRouter(prefix="/identidade", tags=["identidade"])


@router.get("/kyc")
def meu_kyc(usuario: dict = Depends(usuario_atual), repo: Repositorio = Depends(get_repo)):
    """Situação da verificação de identidade e o resultado da última análise
    (campos mascarados -- a imagem do documento nunca é guardada)."""
    return {"status": usuario.get("kyc_status"), "caso": repo.ultimo_caso_kyc(usuario_id=usuario["id"])}


@router.post("/documentos", status_code=201)
def reenviar_documento(dados: DocumentoIdentidadeEnvio, usuario: dict = Depends(usuario_atual),
                       repo: Repositorio = Depends(get_repo), ip: str | None = Depends(ip_cliente)):
    """Novo documento (ex.: o primeiro ficou em análise ou venceu). O rosto do
    documento é comparado com o template facial já cadastrado da pessoa."""
    if usuario.get("kyc_status") == "aprovado":
        raise HTTPException(status_code=409, detail="Sua identidade já está verificada.")
    blob = repo.obter_embedding_cifrado(usuario["id"])
    template = security.decifrar_embedding(blob) if blob else None
    r = documento_service.analisar_documento_pessoa(
        tipo=dados.tipo, frente_b64=dados.frente, verso_b64=dados.verso, nome=usuario["nome"], cpf=usuario["cpf"] or "",
        data_nascimento=usuario.get("data_nascimento"), template_selfie=template,
    )
    caso = documento_service.registrar_caso_pessoa(repo, r, usuario_id=usuario["id"])
    if r["status"] != "reprovado":
        repo.atualizar_kyc_status(usuario["id"], r["status"])
    repo.registrar_log(ator=usuario["email"], acao="kyc_documento_reenviado", ip=ip, usuario_id=usuario["id"],
                       detalhe={"status": r["status"]})
    return {"status": r["status"], "motivos": r["motivos"], "caso_id": caso["id"]}
