"""
Tempo no horário de Brasília. O Brasil não tem horário de verão desde 2019,
então um deslocamento fixo de -3h basta e evita depender do banco de fusos do
sistema (o Windows não traz o tzdata que o `zoneinfo` precisa).
"""

from datetime import date, datetime, timedelta, timezone

BRT = timezone(timedelta(hours=-3), name="BRT")


def agora() -> datetime:
    return datetime.now(timezone.utc)


def em_brt(momento: datetime) -> datetime:
    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=timezone.utc)
    return momento.astimezone(BRT)


def eh_noturno(momento: datetime, hora_inicio: int, hora_fim: int) -> bool:
    h = em_brt(momento).hour
    if hora_inicio > hora_fim:  # atravessa a meia-noite (padrão 20h -> 6h)
        return h >= hora_inicio or h < hora_fim
    return hora_inicio <= h < hora_fim


def inicio_periodo(momento: datetime, hora_inicio: int, hora_fim: int) -> datetime:
    """Início (em UTC) do período diurno ou noturno em que `momento` está. Usado
    para somar o que já saiu da conta no período corrente."""
    local = em_brt(momento)
    noturno = eh_noturno(momento, hora_inicio, hora_fim)
    if noturno:
        inicio = local.replace(hour=hora_inicio, minute=0, second=0, microsecond=0)
        if hora_inicio > hora_fim and local.hour < hora_fim:
            inicio -= timedelta(days=1)
    else:
        inicio = local.replace(hour=hora_fim, minute=0, second=0, microsecond=0)
    return inicio.astimezone(timezone.utc)


def inicio_do_dia(momento: datetime) -> datetime:
    local = em_brt(momento).replace(hour=0, minute=0, second=0, microsecond=0)
    return local.astimezone(timezone.utc)


def hoje_brt() -> date:
    return em_brt(agora()).date()


def dia_util(d: date) -> bool:
    """Segunda a sexta. Feriados nacionais ficam de fora (TODO: calendário ANBIMA)."""
    return d.weekday() < 5
