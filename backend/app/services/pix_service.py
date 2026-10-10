"""
Chaves Pix e resolução do destino de um pagamento.

Antes (v6) o destino era um `carteira_id` numérico de 6 dígitos e GET
/usuarios/{id} devolvia o nome do dono a qualquer logado -- dava para varrer a
base. Agora:
- O destino é uma chave (CPF, CNPJ, e-mail, celular, aleatória) ou agência +
  número da conta gerado pelo banco.
- A consulta de chave devolve só o nome mascarado e o documento mascarado, como
  no Pix real, e é limitada por pessoa por hora (CONSULTA_CHAVE_MAX_HORA).
- Limite de chaves por conta: 5 (PF) e 20 (PJ), como no regulamento do Pix.
"""

import re
import uuid
from datetime import timedelta

from fastapi import HTTPException

from app.core import tempo
from app.core.config import get_settings
from app.core.documentos import (
    cnpj_valido,
    cpf_valido,
    mascarar_cnpj,
    mascarar_cpf,
    mascarar_nome,
    normalizar_celular,
    somente_digitos,
)
from app.repositories.repository import Repositorio

MAX_CHAVES = {"PF": 5, "PJ": 20}
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def candidatos(chave: str) -> list[tuple[str, str]]:
    """Interpretações possíveis de uma chave digitada, na ordem de tentativa."""
    bruto = chave.strip()
    res: list[tuple[str, str]] = []
    try:
        res.append(("aleatoria", str(uuid.UUID(bruto))))
    except ValueError:
        pass
    if _EMAIL.match(bruto):
        res.append(("email", bruto.lower()))
    d = somente_digitos(bruto)
    if len(d) == 11 and cpf_valido(d):
        res.append(("cpf", d))
    if len(d) == 14 and cnpj_valido(d):
        res.append(("cnpj", d))
    cel = normalizar_celular(bruto)
    if cel and (bruto.startswith("+") or len(d) in (10, 11, 12, 13)):
        res.append(("celular", cel))
    return res


_NUMERO_CONTA = re.compile(r"^\d{8}-\d$")


def resolver_chave(repo: Repositorio, chave: str) -> dict:
    """Chave Pix ou, como atalho, número de conta da agência 0001 ("12345678-9")."""
    if _NUMERO_CONTA.match(chave.strip()):
        conta = repo.obter_conta_por_numero(chave.strip())
        if conta and conta["titular_tipo"] != "SISTEMA":
            return conta
    for tipo, valor in candidatos(chave):
        carteira_id = repo.buscar_chave(tipo, valor)
        if carteira_id:
            return repo.obter_conta(carteira_id)
    raise HTTPException(status_code=404, detail="Chave Pix não encontrada.")


def resolver_destino(repo: Repositorio, destino) -> dict:
    if destino.chave:
        return resolver_chave(repo, destino.chave)
    conta = repo.obter_conta_por_numero(destino.numero, destino.agencia or "0001")
    if not conta or conta["titular_tipo"] == "SISTEMA":
        raise HTTPException(status_code=404, detail="Conta de destino não encontrada.")
    return conta


def consultar(repo: Repositorio, *, usuario: dict, chave: str, ip: str | None) -> dict:
    s = get_settings()
    desde = tempo.agora() - timedelta(hours=1)
    if repo.contar_eventos(tipo="consulta_chave", desde=desde, sucesso=None, usuario_id=usuario["id"]) >= s.consulta_chave_max_hora:
        raise HTTPException(status_code=429, detail="Muitas consultas de chave. Tente de novo mais tarde.")
    repo.registrar_sessao_mfa(tipo="consulta_chave", sucesso=True, usuario_id=usuario["id"], ip=ip)
    conta = resolver_chave(repo, chave)
    doc = conta["documento"] or ""
    return {
        "nome": mascarar_nome(conta["nome"]) if conta["titular_tipo"] == "PF" else conta["nome"],
        "documento": mascarar_cpf(doc) if conta["titular_tipo"] == "PF" else mascarar_cnpj(doc),
        "titular_tipo": conta["titular_tipo"],
        "instituicao": "Astro",
    }


def criar_chave(repo: Repositorio, *, conta: dict, tipo: str, valor: str | None, ip: str | None, autor: dict) -> dict:
    if repo.contar_chaves(conta["carteira_id"]) >= MAX_CHAVES[conta["titular_tipo"]]:
        raise HTTPException(status_code=400, detail=f"Limite de {MAX_CHAVES[conta['titular_tipo']]} chaves por conta atingido.")
    if get_settings().em_producao and tipo in ("email", "celular"):
        raise HTTPException(status_code=409, detail="Chaves de e-mail/celular exigem confirmação de posse, ainda não disponível.")
    if tipo == "aleatoria":
        valor_final = str(uuid.uuid4())
    elif tipo == "cpf":
        if conta["titular_tipo"] != "PF":
            raise HTTPException(status_code=400, detail="Chave CPF só para conta pessoal.")
        valor_final = conta["documento"]
    elif tipo == "cnpj":
        if conta["titular_tipo"] != "PJ":
            raise HTTPException(status_code=400, detail="Chave CNPJ só para conta de empresa.")
        valor_final = conta["documento"]
    elif tipo == "email":
        if not valor or not _EMAIL.match(valor.strip()):
            raise HTTPException(status_code=400, detail="E-mail inválido.")
        valor_final = valor.strip().lower()
    else:  # celular
        valor_final = normalizar_celular(valor or "")
        if not valor_final:
            raise HTTPException(status_code=400, detail="Celular inválido. Use DDD + número.")
    # TODO(produção): e-mail e celular precisam de confirmação por código antes de valer.
    k = repo.criar_chave(carteira_id=conta["carteira_id"], tipo=tipo, valor=valor_final)
    if k is None:
        raise HTTPException(status_code=409, detail="Esta chave já está cadastrada.")
    repo.registrar_log(ator=autor["email"], acao="chave_pix_criada", ip=ip, usuario_id=autor["id"], empresa_id=conta.get("empresa_id"), detalhe={"tipo": tipo, "carteira_id": conta["carteira_id"]})
    return k
