"""
Webhooks para o ERP da empresa.

- Eventos: cobranca.paga, cobranca.estornada, pix.recebido, operacao.pendente.
- Cada entrega vai num POST JSON com os headers:
    X-PayFlow-Evento, X-PayFlow-Entrega (id, para deduplicar no ERP) e
    X-PayFlow-Assinatura: sha256=<HMAC-SHA256 do corpo com o segredo do webhook>.
- A entrega é tentada logo após o evento (thread em segundo plano, se
  WEBHOOK_ENTREGA_IMEDIATA) e reenviada pelo job POST /admin/jobs/webhooks até
  WEBHOOK_MAX_TENTATIVAS. Só https é aceito no cadastro.
- SSRF (SECURITY_AUDIT.md A-04): a URL é do cliente, mas quem faz o POST é o
  servidor, de dentro da rede da nuvem. Por isso: só https nas portas 443/8443, sem
  usuário/senha na URL, sem IP interno, sem redirecionamento; e, na entrega, o nome
  é resolvido e TODOS os endereços precisam ser públicos. O erro guardado é genérico
  (não diz "porta fechada" x "tempo esgotado", que serviria para mapear a rede).
"""

import hashlib
import hmac
import ipaddress
import json
import logging
import secrets
import socket
import threading
from urllib.parse import urlsplit

from fastapi import HTTPException

from app.core.config import get_settings
from app.repositories.repository import Repositorio

logger = logging.getLogger("payflow.webhook")

EVENTOS = {"cobranca.paga", "cobranca.estornada", "pix.recebido", "operacao.pendente"}


def assinar(segredo: str, corpo: bytes) -> str:
    return "sha256=" + hmac.new(segredo.encode(), corpo, hashlib.sha256).hexdigest()


PORTAS = {443, 8443}
_NOMES_INTERNOS = ("localhost", ".localhost", ".local", ".internal", ".localdomain", ".home.arpa")


class DestinoRecusado(ValueError):
    pass


def _ip_publico(ip: str) -> bool:
    try:
        end = ipaddress.ip_address(ip.split("%")[0])
    except ValueError:
        return False
    if isinstance(end, ipaddress.IPv6Address) and end.ipv4_mapped:
        end = end.ipv4_mapped
    return end.is_global and not end.is_multicast


def validar_url(url: str) -> tuple[str, int]:
    """Confere a URL sem rede (cadastro). Devolve (host, porta)."""
    try:
        partes = urlsplit(url)
        porta = partes.port or 443
    except ValueError:
        raise DestinoRecusado("URL inválida.") from None
    host = (partes.hostname or "").lower().rstrip(".")
    if partes.scheme != "https" or not host:
        raise DestinoRecusado("Use uma URL https com o nome do servidor.")
    if partes.username or partes.password:
        raise DestinoRecusado("Não coloque usuário ou senha na URL: use o segredo de assinatura.")
    if porta not in PORTAS:
        raise DestinoRecusado("Use a porta 443 (padrão do https) ou 8443.")
    if host == "localhost" or host.endswith(_NOMES_INTERNOS):
        raise DestinoRecusado("Endereço interno não é aceito.")
    try:
        ipaddress.ip_address(host)
        literal = True
    except ValueError:
        literal = False
    if literal and not _ip_publico(host):
        raise DestinoRecusado("Endereço interno não é aceito.")
    return host, porta


def resolver_publico(host: str, porta: int) -> None:
    """Na entrega: todos os endereços do nome precisam ser públicos (um nome que
    resolve para 10.x / 169.254.169.254 / ::1 não recebe nada)."""
    try:
        infos = socket.getaddrinfo(host, porta, proto=socket.IPPROTO_TCP)
    except OSError:
        raise DestinoRecusado("Não foi possível resolver o endereço.") from None
    if not infos or not all(_ip_publico(i[4][0]) for i in infos):
        raise DestinoRecusado("O endereço resolve para uma rede interna.")


def criar(repo: Repositorio, *, empresa_id: int, url: str, eventos: list[str]) -> dict:
    try:
        validar_url(url)
    except DestinoRecusado as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
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
        resolver_publico(*validar_url(url))
    except DestinoRecusado as e:
        return False, f"recusado: {e}"
    try:
        r = httpx.post(url, content=corpo, headers=headers, timeout=get_settings().webhook_timeout_seg,
                       follow_redirects=False)
    except httpx.HTTPError as e:
        logger.info("Webhook para %s falhou: %s", urlsplit(url).hostname, type(e).__name__)
        return False, "falha de conexão"
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
