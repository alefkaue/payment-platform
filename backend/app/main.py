from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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


@app.get("/")
def raiz():
    return {"status": "ok", "servico": "payflow"}
