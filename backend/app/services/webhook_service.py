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
import http.client
import ssl
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


def resolver_publico(host: str, porta: int) -> list[str]:
    """Na entrega: todos os endereços do nome precisam ser públicos (um nome que
    resolve para 10.x / 169.254.169.254 / ::1 não recebe nada)."""
    try:
        infos = socket.getaddrinfo(host, porta, proto=socket.IPPROTO_TCP)
    except OSError:
        raise DestinoRecusado("Não foi possível resolver o endereço.") from None
    if not infos or not all(_ip_publico(i[4][0]) for i in infos):
        raise DestinoRecusado("O endereço resolve para uma rede interna.")
    return list(dict.fromkeys(i[4][0] for i in infos))


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


class _HTTPSFixado(http.client.HTTPSConnection):
    """Conecta ao IP que foi validado; TLS continua verificando o hostname.
    Não há segunda resolução DNS nem proxy/redirect decidido pelo ambiente.
    """
    def __init__(self, host: str, porta: int, ip: str, timeout: float):
        super().__init__(host, porta, timeout=timeout, context=ssl.create_default_context())
        self._ip_validado = ip

    def connect(self):
        family = socket.AF_INET6 if ":" in self._ip_validado else socket.AF_INET
        raw = socket.socket(family, socket.SOCK_STREAM)
        raw.settimeout(self.timeout)
        try:
            raw.connect((self._ip_validado, self.port))
            self.sock = self._context.wrap_socket(raw, server_hostname=self.host)
        except BaseException:
            raw.close()
            raise


def _enviar(url: str, corpo: bytes, headers: dict) -> tuple[bool, str]:
    """POST com DNS fixado no IP público validado (fecha DNS rebinding)."""
    try:
        host, porta = validar_url(url)
        ips = resolver_publico(host, porta)
    except DestinoRecusado as e:
        return False, f"recusado: {e}"
    partes = urlsplit(url)
    caminho = partes.path or "/"
    if partes.query:
        caminho += "?" + partes.query
    conexao = _HTTPSFixado(host, porta, ips[0], get_settings().webhook_timeout_seg)
    try:
        conexao.request("POST", caminho, body=corpo, headers=headers)
        resposta = conexao.getresponse()
        # Só precisamos do status; não carregamos um corpo remoto ilimitado.
        return 200 <= resposta.status < 300, f"HTTP {resposta.status}"
    except (OSError, http.client.HTTPException, ValueError) as e:
        logger.info("Webhook para %s falhou: %s", host, type(e).__name__)
        return False, "falha de conexão"
    finally:
        conexao.close()


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


def entregar_agora(repo: Repositorio, entregas: list[int] | None) -> None:
    """Tenta já as entregas gravadas no outbox (o job de webhooks garante as que falharem)."""
    if not entregas or not get_settings().webhook_entrega_imediata:
        return
    for entrega_id in entregas:
        threading.Thread(target=entregar, args=(repo, entrega_id), daemon=True).start()


def processar_pendentes(repo: Repositorio) -> dict:
    pendentes = repo.entregas_pendentes(get_settings().webhook_max_tentativas)
    for e in pendentes:
        entregar(repo, e["id"])
    return {"processadas": len(pendentes)}
