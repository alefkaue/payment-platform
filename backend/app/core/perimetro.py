"""Controles baratos antes de acessar banco ou processar imagens.

As iscas respondem como uma rota inexistente. Nunca recebem credenciais falsas,
consultam dados ou penalizam permanentemente um IP (redes podem ser compartilhadas).
"""
import asyncio
import hashlib
import hmac
import json
import secrets
import time
import uuid
from collections import OrderedDict

from starlette.requests import Request
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.core import logs
from app.deps import ip_cliente

ISCAS = frozenset({"/.env", "/.git/config", "/wp-login.php", "/phpmyadmin",
                   "/admin/backup.sql", "/api/debug", "/backup/database.sql",
                   "/admin/database", "/admin/export", "/admin/credentials",
                   "/api/internal/users", "/api/internal/tokens", "/api/debug/config",
                   "/backup/astro.dump", "/backup/latest.sql", "/database.sql",
                   "/actuator/env", "/actuator/heapdump", "/server-status",
                   "/.aws/credentials", "/.env.production", "/config/secrets.json"})
METODOS = frozenset({"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"})


class PerimetroHTTP:
    def __init__(self, app, *, limite: int, requisicoes_minuto: int = 600,
                 max_ips: int = 10000, espera_corpo: float = 30,
                 memoria_corpos: int = 96 * 1024 * 1024, producao: bool = False,
                 hosts: list[str] | None = None, relogio=time.monotonic):
        self.app = app
        self.host_filter = TrustedHostMiddleware(self._chamar, allowed_hosts=hosts,
                                                 www_redirect=False) if hosts else None
        self.limite = limite
        self.producao = producao
        self.requisicoes_minuto = requisicoes_minuto
        self.max_ips = max_ips
        self.espera_corpo = espera_corpo
        self.memoria_corpos = memoria_corpos
        self.bytes_em_uso = 0
        self.relogio = relogio
        self.baldes = OrderedDict()
        # Identificador de origem temporário: não registra IP bruto nem segredo JWT.
        self.chave_log = secrets.token_bytes(32)
        self.ultimas_iscas = OrderedDict()

    def _permitir(self, ip):
        agora = self.relogio()
        anterior = self.baldes.pop(ip, None)
        tokens, ultimo = anterior if anterior else (float(self.requisicoes_minuto), agora)
        tokens = min(self.requisicoes_minuto, tokens + max(0, agora - ultimo) * self.requisicoes_minuto / 60)
        permitido = tokens >= 1
        self.baldes[ip] = (tokens - 1 if permitido else tokens, agora)
        while len(self.baldes) > self.max_ips:
            self.baldes.popitem(last=False)
        return permitido

    def _registrar_isca(self, ip, caminho):
        agora = self.relogio()
        ultimo = self.ultimas_iscas.pop(ip, float("-inf"))
        registrar = agora - ultimo >= 60
        self.ultimas_iscas[ip] = agora if registrar else ultimo
        while len(self.ultimas_iscas) > self.max_ips:
            self.ultimas_iscas.popitem(last=False)
        if registrar:
            origem = hmac.new(self.chave_log, ip.encode(), hashlib.sha256).hexdigest()[:24]
            logs.evento("sondagem_rota_isca", origem=origem, isca=caminho)

    async def _erro(self, send, status, detalhe, request_id, retry=False):
        corpo = json.dumps({"type": "about:blank", "status": status,
                            "detail": detalhe, "request_id": request_id}).encode()
        headers = [(b"content-type", b"application/problem+json"),
                   (b"content-length", str(len(corpo)).encode()), (b"cache-control", b"no-store"),
                   (b"x-content-type-options", b"nosniff"), (b"x-frame-options", b"DENY"),
                   (b"content-security-policy", b"default-src 'none'; frame-ancestors 'none'"),
                   (b"x-request-id", request_id.encode())]
        if self.producao:
            headers.append((b"strict-transport-security", b"max-age=31536000; includeSubDomains"))
        if retry:
            headers.append((b"retry-after", b"1"))
        await send({"type": "http.response.start", "status": status, "headers": headers})
        await send({"type": "http.response.body", "body": corpo})

    async def __call__(self, scope, receive, send):
        if self.host_filter:
            return await self.host_filter(scope, receive, send)
        return await self._chamar(scope, receive, send)

    async def _chamar(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        request_id = uuid.uuid4().hex
        token = logs.request_id_atual.set(request_id)
        reservado = 0
        try:
            unicos = {b"host", b"authorization", b"dpop", b"x-conta", b"x-dispositivo-id", b"idempotency-key"}
            vistos = set()
            for nome, _ in scope.get("headers", ()):
                nome = nome.lower()
                if nome in unicos:
                    if nome in vistos:
                        return await self._erro(send, 400, "Cabeçalho de segurança duplicado.", request_id)
                    vistos.add(nome)
            caminho = scope.get("path", "")
            # Sondas locais sem corpo não competem com clientes pelo balde do proxy.
            ip = ip_cliente(Request(scope)) or "desconhecido"
            sem_corpo = not any(k.lower() == b"transfer-encoding" or
                                (k.lower() == b"content-length" and v != b"0")
                                for k, v in scope.get("headers", ()))
            sonda = (ip in {"127.0.0.1", "::1"} and sem_corpo and
                     caminho in {"/saude", "/pronto"} and scope["method"] in {"GET", "HEAD"})
            permitido = True if sonda else self._permitir(ip)
            if not permitido:
                return await self._erro(send, 429, "Muitas requisições. Tente novamente.", request_id, True)
            if caminho.rstrip("/").lower() in ISCAS:
                self._registrar_isca(ip, caminho.rstrip("/").lower())
                return await self._erro(send, 404, "Not Found", request_id)
            if scope["method"] not in METODOS:
                return await self._erro(send, 405, "Método não permitido.", request_id)
            tamanhos = [v for k, v in scope.get("headers", ()) if k.lower() == b"content-length"]
            if tamanhos:
                if len(tamanhos) != 1 or not tamanhos[0].isdigit() or len(tamanhos[0]) > 12:
                    return await self._erro(send, 400, "Tamanho de requisição inválido.", request_id)
                if int(tamanhos[0]) > self.limite:
                    return await self._erro(send, 413, "Requisição muito grande.", request_id)
            corpo = bytearray()
            total = 0
            try:
                async with asyncio.timeout(self.espera_corpo):
                    while True:
                        msg = await receive()
                        if msg["type"] == "http.disconnect":
                            return
                        tamanho = len(msg.get("body", b""))
                        total += tamanho
                        if total > self.limite:
                            return await self._erro(send, 413, "Requisição muito grande.", request_id)
                        if self.bytes_em_uso + tamanho > self.memoria_corpos:
                            return await self._erro(send, 503, "Serviço ocupado. Tente novamente.", request_id, True)
                        self.bytes_em_uso += tamanho
                        reservado += tamanho
                        corpo.extend(msg.get("body", b""))
                        if not msg.get("more_body", False):
                            break
            except TimeoutError:
                return await self._erro(send, 408, "Tempo de envio excedido.", request_id)
            corpo = bytes(corpo)
            entregue = False

            async def reproduzir():
                nonlocal entregue
                if not entregue:
                    entregue = True
                    return {"type": "http.request", "body": corpo, "more_body": False}
                return await receive()

            await self.app(scope, reproduzir, send)
        finally:
            self.bytes_em_uso -= reservado
            logs.request_id_atual.reset(token)
