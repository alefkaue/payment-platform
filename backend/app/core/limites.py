"""
Limite de requisições por IP para rotas sem login (SEGURANCA.md item 4).

Os eventos ficam no banco (tabela sessoes_mfa, a mesma do limite de login), e
não na memória do processo: com várias instâncias da API no Azure o limite
continua valendo. O IP vem de `deps.ip_cliente` (X-Forwarded-For só de proxy
confiável), então o atacante não escapa trocando o header.
"""

from datetime import timedelta

from fastapi import HTTPException

from app.core import tempo


def limitar_por_ip(repo, *, tipo: str, ip: str | None, maximo: int, janela_min: int, mensagem: str) -> None:
    """Conta esta chamada e levanta 429 (com Retry-After) se passou do máximo na janela."""
    if not ip:
        return
    desde = tempo.agora() - timedelta(minutes=janela_min)
    if repo.contar_eventos(tipo=tipo, desde=desde, sucesso=None, ip=ip) >= maximo:
        raise HTTPException(status_code=429, detail=mensagem, headers={"Retry-After": str(janela_min * 60)})
    repo.registrar_sessao_mfa(tipo=tipo, sucesso=True, ip=ip)
