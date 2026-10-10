"""Lista as rotas de verdade da API.

Desde o FastAPI 0.13x, `app.routes` guarda cada `include_router` como um nó
(`_IncludedRouter`) em vez de copiar as rotas: quem percorre `app.routes` só vê as
rotas do próprio app. Os testes de "nada abre sem login" e o inventário de endpoints
usam esta função para não passarem "vazios"."""

from fastapi.routing import APIRoute


def todas_as_rotas(app) -> list[APIRoute]:
    saida: list[APIRoute] = []

    def visitar(rotas):
        for r in rotas:
            if isinstance(r, APIRoute):
                saida.append(r)
            elif hasattr(r, "original_router"):
                visitar(r.original_router.routes)

    visitar(app.routes)
    return saida
