"""
App FastAPI da Astro (v9). Ver SECURITY.md (controles) e AZURE.md (deploy).

No boot: cria as tabelas (dev/SQLite; em produção o Alembic roda antes, ver
entrypoint.sh), as contas de sistema (CAIXA, TRIBUTOS, FISCO) e a pessoa admin.
"""

import logging
import re
import uuid
from contextlib import asynccontextmanager
from decimal import Decimal
from http import HTTPStatus

import fastapi.encoders
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.config import get_settings
from app.core.security import hash_senha
from app.db.base import usando_postgres
from app.repositories import get_repository
from app.routers import admin, auth, beneficios, biometria, cobrancas, contas, identidade, pagamentos, seguranca
from app.services import beneficios_service, split_service

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

# Dinheiro sai SEMPRE como string decimal ("1500.00"). Respostas com
# response_model já fazem isso (Pydantic v2); as sem modelo passam pelo
# jsonable_encoder, que por padrão converteria Decimal em float.
fastapi.encoders.ENCODERS_BY_TYPE[Decimal] = str
logger = logging.getLogger("payflow")

settings = get_settings()

# Senha do admin quando ADMIN_SENHA não vem no ambiente (só em desenvolvimento;
# em produção o boot falha). Documentada no README -- não vai para o log.
SENHA_ADMIN_DEV = "payflow-admin-dev"


def _preparar():
    repo = get_repository()
    repo.garantir_contas_sistema()
    senha_admin = settings.admin_senha
    if not senha_admin:
        if settings.em_producao:
            raise RuntimeError("ADMIN_SENHA é obrigatória em produção.")
        senha_admin = SENHA_ADMIN_DEV
        logger.warning("ADMIN_SENHA não definida: admin %s com a senha padrão de desenvolvimento (ver README).",
                       settings.admin_email)
    repo.garantir_admin(email=settings.admin_email, senha_hash=hash_senha(senha_admin))
    beneficios_service.garantir_catalogo(repo)
    logger.info("Astro pronto -- banco: %s | ano do simulador de split: %s",
                "postgres" if usando_postgres() else "sqlite", split_service.ano_padrao())


@asynccontextmanager
async def lifespan(app: FastAPI):
    _preparar()
    yield


_docs = settings.docs_ligados
app = FastAPI(
    title="Astro", version="9.0", lifespan=lifespan,
    # Swagger/OpenAPI desligados em produção (DOCS_HABILITADOS=1 religa). Reduz
    # exposição; a segurança de verdade está na autenticação/autorização.
    docs_url="/docs" if _docs else None, redoc_url=None, openapi_url="/openapi.json" if _docs else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_lista,
    allow_origin_regex=settings.cors_origin_regex or None,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Conta", "X-Dispositivo-Id", "X-Request-Id",
                   "Idempotency-Key", "DPoP"],
    expose_headers=["X-Request-Id"],
    allow_credentials=True,
)

# Teto de corpo: até 40 quadros de biometria ou documentos (base64) + folga.
_LIMITE_CORPO = 48 * 1024 * 1024
_REQ_ID_RE = re.compile(r"^[A-Za-z0-9._-]{8,64}$")


@app.middleware("http")
async def seguranca_http(request: Request, call_next):
    """Request-ID, teto de corpo e cabeçalhos de segurança em TODA resposta
    (inclusive erro)."""
    recebido = request.headers.get("x-request-id", "")
    request.state.request_id = recebido if _REQ_ID_RE.match(recebido) else uuid.uuid4().hex
    cl = request.headers.get("content-length")
    if cl and cl.isdigit() and int(cl) > _LIMITE_CORPO:
        resp = _problema(request, 413, "Requisição muito grande.")
    else:
        resp = await call_next(request)
    h = resp.headers
    h["X-Request-Id"] = request.state.request_id
    h["X-Content-Type-Options"] = "nosniff"
    h["X-Frame-Options"] = "DENY"
    h["Referrer-Policy"] = "no-referrer"
    h["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), payment=()"
    h["Cross-Origin-Opener-Policy"] = "same-origin"
    if not request.url.path.startswith("/docs"):
        # API JSON: nada de executar/embutir nada daqui; e dado bancário não fica em cache.
        h["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"
        h["Cache-Control"] = "no-store"
    if settings.em_producao:
        h["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return resp


# ------------------------------------------------------------------ erros (RFC 9457 problem+json)


def _problema(request: Request, status: int, detail: str, headers: dict | None = None, **extra) -> JSONResponse:
    """Formato padrão de erro. Mantém `detail` (o app lê esse campo)."""
    try:
        titulo = HTTPStatus(status).phrase
    except ValueError:
        titulo = "Erro"
    corpo = {"type": "about:blank", "title": titulo, "status": status, "detail": detail,
             "request_id": getattr(request.state, "request_id", None), **extra}
    return JSONResponse(status_code=status, content=corpo, headers=headers, media_type="application/problem+json")


@app.exception_handler(StarletteHTTPException)
async def _erro_http(request: Request, exc: StarletteHTTPException):
    detalhe = exc.detail if isinstance(exc.detail, str) else "Requisição inválida."
    return _problema(request, exc.status_code, detalhe, headers=getattr(exc, "headers", None))


@app.exception_handler(RequestValidationError)
async def _erro_validacao(request: Request, exc: RequestValidationError):
    # Nunca ecoa o valor enviado (pode ser senha, documento, imagem...): só o campo e o motivo.
    erros = [{"campo": ".".join(str(p) for p in e.get("loc", ())[1:]), "motivo": e.get("msg", "")} for e in exc.errors()]
    return _problema(request, 422, "Dados inválidos: confira os campos.", erros=erros[:20])


@app.exception_handler(Exception)
async def _erro_inesperado(request: Request, exc: Exception):
    logger.exception("Erro inesperado (request_id=%s)", getattr(request.state, "request_id", None))
    return _problema(request, 500, "Erro interno. Tente de novo; se continuar, informe o código da requisição.")


for r in (auth, contas, identidade, biometria, pagamentos, cobrancas, beneficios, seguranca, admin):
    app.include_router(r.router)


@app.get("/")
def raiz():
    return {"status": "ok", "servico": "astro", "versao": "9.0"}


@app.get("/saude")
def saude():
    """Liveness/readiness para o Azure Container Apps (sem dados internos)."""
    return {"status": "ok"}
