"""
App FastAPI do PayFlow (v7). Ver HANDOFF.md para o mapa completo.

No boot: cria as tabelas (dev/SQLite; em produção o Alembic roda antes, ver
entrypoint.sh), as contas de sistema (CAIXA, TRIBUTOS, FISCO) e a pessoa admin.
"""

import logging
from contextlib import asynccontextmanager
from decimal import Decimal

import fastapi.encoders
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.core.security import hash_senha
from app.db.base import usando_postgres
from app.repositories import get_repository
from app.routers import admin, auth, beneficios, biometria, cobrancas, contas, pagamentos, seguranca
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


app = FastAPI(title="Astro", version="7.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_lista,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Conta", "X-Dispositivo-Id"],
    allow_credentials=True,
)

# Teto de corpo: lote de até 5 quadros de biometria + folga.
_LIMITE_CORPO = settings.foto_max_bytes * 8


@app.middleware("http")
async def limitar_tamanho_corpo(request: Request, call_next):
    cl = request.headers.get("content-length")
    if cl and cl.isdigit() and int(cl) > _LIMITE_CORPO:
        return JSONResponse(status_code=413, content={"detail": "Requisição muito grande."})
    return await call_next(request)


for r in (auth, contas, biometria, pagamentos, cobrancas, beneficios, seguranca, admin):
    app.include_router(r.router)


@app.get("/")
def raiz():
    return {"status": "ok", "servico": "payflow", "versao": "7.0",
            "repositorio": "postgres" if usando_postgres() else "sqlite"}
