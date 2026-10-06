"""
Webhooks para o ERP da empresa.

- Eventos: cobranca.paga, cobranca.estornada, pix.recebido, operacao.pendente.
- Cada entrega vai num POST JSON com os headers:
    X-PayFlow-Evento, X-PayFlow-Entrega (id, para deduplicar no ERP) e
    X-PayFlow-Assinatura: sha256=<HMAC-SHA256 do corpo com o segredo do webhook>.
- A entrega é tentada logo após o evento (thread em segundo plano, se
  WEBHOOK_ENTREGA_IMEDIATA) e reenviada pelo job POST /admin/jobs/webhooks até
  WEBHOOK_MAX_TENTATIVAS. Só https é aceito no cadastro.
"""

import hashlib
import hmac
import json
import logging
import secrets
import threading

from fastapi import HTTPException

from app.core.config import get_settings
from app.repositories.repository import Repositorio

logger = logging.getLogger("payflow.webhook")

EVENTOS = {"cobranca.paga", "cobranca.estornada", "pix.recebido", "operacao.pendente"}


def assinar(segredo: str, corpo: bytes) -> str:
    return "sha256=" + hmac.new(segredo.encode(), corpo, hashlib.sha256).hexdigest()


def criar(repo: Repositorio, *, empresa_id: int, url: str, eventos: list[str]) -> dict:
    invalidos = set(eventos) - EVENTOS
    if invalidos:
        raise HTTPException(status_code=400, detail=f"Eventos desconhecidos: {sorted(invalidos)}. Use {sorted(EVENTOS)}.")
    segredo = secrets.token_urlsafe(32)
    w = repo.criar_webhook(empresa_id=empresa_id, url=url, segredo=segredo, eventos=sorted(set(eventos)))
    return {**w, "segredo": segredo}


def _enviar(url: str, corpo: bytes, headers: dict) -> tuple[bool, str]:
    """Faz o POST. Isolado para os testes substituírem."""
    import httpx

    try:
        r = httpx.post(url, content=corpo, headers=headers, timeout=get_settings().webhook_timeout_seg)
    except httpx.HTTPError as e:
        return False, f"erro: {e}"
    return 200 <= r.status_code < 300, f"HTTP {r.status_code}"


def entregar(repo: Repositorio, entrega_id: int) -> None:
    e = repo.obter_entrega(entrega_id)
    w = repo.obter_webhook_com_segredo(e["webhook_id"]) if e else None
    if not e or not w or not w["ativo"]:
        return
    corpo = json.dumps({"evento": e["evento"], "entrega_id": e["id"], "dados": e["payload"]}, default=str).encode()
    headers = {
        "Content-Type": "application/json",
        "X-PayFlow-Evento": e["evento"],
        "X-PayFlow-Entrega": str(e["id"]),
        "X-PayFlow-Assinatura": assinar(w["segredo"], corpo),
    }
    ok, resposta = _enviar(w["url"], corpo, headers)
    repo.registrar_tentativa_entrega(entrega_id, sucesso=ok, resposta=resposta,
                                     max_tentativas=get_settings().webhook_max_tentativas)
    if not ok:
        logger.info("Webhook %s falhou (%s)", entrega_id, resposta)


def emitir(repo: Repositorio, *, empresa_id: int | None, evento: str, payload: dict) -> None:
    if empresa_id is None:
        return
    for w in repo.listar_webhooks(empresa_id, so_ativos=True):
        if evento not in w["eventos"]:
            continue
        entrega_id = repo.criar_entrega(webhook_id=w["id"], evento=evento, payload=json.loads(json.dumps(payload, default=str)))
        if get_settings().webhook_entrega_imediata:
            threading.Thread(target=entregar, args=(repo, entrega_id), daemon=True).start()


def processar_pendentes(repo: Repositorio) -> dict:
    pendentes = repo.entregas_pendentes(get_settings().webhook_max_tentativas)
    for e in pendentes:
        entregar(repo, e["id"])
    return {"processadas": len(pendentes)}
