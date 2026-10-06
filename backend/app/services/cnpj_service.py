"""
Consulta cadastral de CNPJ (situação, razão social, CNAE e quadro de sócios).

Provedores (CNPJ_PROVEDOR):
- "stub": desenvolvimento e testes. Aceita qualquer CNPJ com dígito válido,
  situação ATIVA, sem quadro de sócios. Proibido em produção (core/config.py).
- "brasilapi": https://brasilapi.com.br/api/cnpj/v1/{cnpj} -- dados públicos da
  Receita. O CPF dos sócios vem mascarado ("***123456**"), então conferimos os
  6 dígitos do meio e o nome.

Para trocar por um bureau pago (Serpro, BigDataCorp...), implemente outra função
com a mesma assinatura de `consultar` e registre em `_PROVEDORES`.
"""

import logging
import unicodedata
from dataclasses import dataclass, field

from fastapi import HTTPException

from app.core.config import get_settings

logger = logging.getLogger("payflow.cnpj")


@dataclass
class Socio:
    nome: str
    cpf_mascarado: str | None


@dataclass
class DadosCnpj:
    cnpj: str
    razao_social: str
    nome_fantasia: str | None
    situacao: str
    cnae: str | None
    socios: list[Socio] | None = field(default=None)  # None = provedor não informa


def _stub(cnpj: str) -> DadosCnpj:
    return DadosCnpj(cnpj=cnpj, razao_social=f"EMPRESA {cnpj}", nome_fantasia=None, situacao="ATIVA", cnae=None)


def _brasilapi(cnpj: str) -> DadosCnpj:
    import httpx

    try:
        r = httpx.get(f"https://brasilapi.com.br/api/cnpj/v1/{cnpj}", timeout=8.0)
    except httpx.HTTPError as e:
        logger.warning("Falha ao consultar CNPJ na BrasilAPI: %s", e)
        raise HTTPException(status_code=503, detail="Consulta de CNPJ indisponível agora. Tente em alguns minutos.")
    if r.status_code == 404:
        raise HTTPException(status_code=400, detail="CNPJ não encontrado na Receita Federal.")
    if r.status_code != 200:
        raise HTTPException(status_code=503, detail="Consulta de CNPJ indisponível agora. Tente em alguns minutos.")
    d = r.json()
    socios = [Socio(nome=s.get("nome_socio", ""), cpf_mascarado=s.get("cnpj_cpf_do_socio")) for s in d.get("qsa") or []]
    return DadosCnpj(
        cnpj=cnpj,
        razao_social=d.get("razao_social") or "",
        nome_fantasia=d.get("nome_fantasia") or None,
        situacao=(d.get("descricao_situacao_cadastral") or "").upper(),
        cnae=str(d.get("cnae_fiscal")) if d.get("cnae_fiscal") else None,
        socios=socios,
    )


_PROVEDORES = {"stub": _stub, "brasilapi": _brasilapi}


def consultar(cnpj: str) -> tuple[DadosCnpj, str]:
    nome = get_settings().cnpj_provedor
    if nome not in _PROVEDORES:
        raise RuntimeError(f"CNPJ_PROVEDOR desconhecido: {nome!r}")
    return _PROVEDORES[nome](cnpj), nome


def _normalizar(nome: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode()
    return " ".join(sem_acento.upper().split())


def eh_socio(dados: DadosCnpj, *, cpf: str, nome: str) -> bool | None:
    """True/False se o provedor traz o quadro de sócios; None se não traz."""
    if dados.socios is None:
        return None
    meio = cpf[3:9]
    alvo = _normalizar(nome)
    for s in dados.socios:
        mascarado = s.cpf_mascarado or ""
        if meio and meio in mascarado:
            return True
        if alvo and _normalizar(s.nome) == alvo:
            return True
    return False
