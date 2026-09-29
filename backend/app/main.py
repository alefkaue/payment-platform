from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db.base import postgres_disponivel
from app.repositories import get_repository
from app.routers import usuarios, pagamentos

app = FastAPI(title="PayFlow - MVP")

# Em produção (Azure), restrinja allow_origins ao domínio do front-end publicado
# (ex: Azure Static Web Apps / Azure App Service).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(usuarios.router)
app.include_router(pagamentos.router)


@app.on_event("startup")
def preparar_repositorio():
    # Se DATABASE_URL estiver configurada, cria as tabelas que ainda não
    # existirem (idempotente) e falha rápido no boot se o Postgres estiver
    # inacessível, em vez de só a primeira requisição do primeiro usuário dar
    # erro. Sem DATABASE_URL, isso só instancia o repositório em memória --
    # nenhum efeito colateral.
    get_repository()


@app.get("/")
def raiz():
    modo = "postgres" if postgres_disponivel() else "memoria"
    return {"status": "ok", "servico": "payflow", "repositorio": modo}
