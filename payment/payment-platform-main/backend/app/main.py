"""
App FastAPI do PayFlow (v6). Novidades em relação à v5:
- Routers de autenticação (JWT), admin (depósito/governo) além de usuários/pagamentos.
- CORS restrito à lista de origins da config (não mais "*") -- item #17.
- Middleware que rejeita corpos gigantes antes de processar (defesa extra do item #4).
- Logging configurado (item #17: o código não gravava log nenhum).
- No boot: cria tabelas, seeda as alíquotas de split e garante a conta Governo/admin.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.core.security import hash_senha
from app.db.base import usando_postgres
from app.repositories import get_repository
from app.routers import admin, auth, pagamentos, usuarios

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("payflow")

settings = get_settings()


def _preparar():
    """Boot: cria tabelas, seeda alíquotas de split e garante a conta Governo/admin."""
    repo = get_repository()
    repo.seed_split_regras()

    senha_admin = settings.admin_senha
    if not senha_admin:
        if settings.em_producao:
            raise RuntimeError("ADMIN_SENHA é obrigatória em produção.")
        senha_admin = "payflow-admin-dev"
        logger.warning(
            "ADMIN_SENHA não definida -- usando senha de DESENVOLVIMENTO para a conta "
            "admin/Governo (%s / %s). NÃO use em produção.",
            settings.admin_email, senha_admin,
        )

    repo.garantir_conta_governo(
        carteira_id=settings.conta_governo_carteira_id,
        nome="Governo (Tesouro)",
        email=settings.admin_email,
        senha_hash=hash_senha(senha_admin),
        documento=settings.conta_governo_documento,
    )
    logger.info("PayFlow pronto -- banco: %s | split vigência: %s",
                "postgres" if usando_postgres() else "sqlite", settings.split_vigencia)


@asynccontextmanager
async def lifespan(app: FastAPI):
    _preparar()
    yield


app = FastAPI(title="PayFlow", version="6.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_lista,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Idempotency-Key"],
    allow_credentials=True,
)

# Teto duro de corpo da requisição (base64 de foto + folga). Rejeita antes de ler
# o corpo inteiro na memória -- defesa de borda contra payload gigante.
_LIMITE_CORPO = settings.foto_max_bytes * 2


@app.middleware("http")
async def limitar_tamanho_corpo(request: Request, call_next):
    cl = request.headers.get("content-length")
    if cl and cl.isdigit() and int(cl) > _LIMITE_CORPO:
        return JSONResponse(status_code=413, content={"detail": "Requisição muito grande."})
    return await call_next(request)


app.include_router(auth.router)
app.include_router(usuarios.router)
app.include_router(pagamentos.router)
app.include_router(admin.router)


@app.get("/")
def raiz():
    return {
        "status": "ok",
        "servico": "payflow",
        "versao": "6.0",
        "repositorio": "postgres" if usando_postgres() else "sqlite",
        "split_vigencia": settings.split_vigencia,
    }
