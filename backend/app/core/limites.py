"""
Limite de requisições por IP para rotas sem login (SEGURANCA.md item 4).

Os eventos ficam no banco (tabela sessoes_mfa, a mesma do limite de login), e
não na memória do processo: com várias instâncias da API no Azure o limite
continua valendo. O IP vem de `deps.ip_cliente` (X-Forwarded-For só de proxy
confiável), então o atacante não escapa trocando o header.
"""

from fastapi import HTTPException


def limitar_por_ip(repo, *, tipo: str, ip: str | None, maximo: int, janela_min: int, mensagem: str) -> None:
    """Conta esta chamada e levanta 429 (com Retry-After) se passou do máximo na janela."""
    if not ip:
        return
    if not repo.consumir_orcamento(tipo=tipo, ip=ip, maximo=maximo, janela_min=janela_min):
        raise HTTPException(status_code=429, detail=mensagem, headers={"Retry-After": str(janela_min * 60)})
