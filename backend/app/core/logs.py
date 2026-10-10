"""
Logs estruturados (SECURITY_AUDIT.md, seção de logs).

- Em produção (ou LOG_JSON=1) cada linha é um objeto JSON: horário, nível, origem,
  mensagem, `request_id` da requisição em curso e os campos extras do evento. O JSON
  escapa quebra de linha e aspas: um dado do usuário não consegue forjar outra linha.
- `request_id` vem de um ContextVar preenchido pelo middleware (main.seguranca_http);
  é o mesmo devolvido no header X-Request-Id e no corpo dos erros, então dá para ligar
  a reclamação do cliente à linha de log e à transação.
- Eventos de segurança/auditoria saem pelo logger "astro.auditoria" com ids internos e
  o tipo do evento -- sem senha, token, documento, imagem ou o `detalhe` livre.
"""

import json
import logging
import os
from contextvars import ContextVar
from datetime import datetime, timezone

request_id_atual: ContextVar[str | None] = ContextVar("request_id_atual", default=None)

_PADRAO = set(vars(logging.makeLogRecord({})).keys()) | {"message", "asctime"}


class FormatoJson(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        linha = {
            "ts": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
            "nivel": record.levelname,
            "origem": record.name,
            "msg": record.getMessage(),
            "request_id": request_id_atual.get(),
        }
        linha.update({k: v for k, v in vars(record).items() if k not in _PADRAO and not k.startswith("_")})
        if record.exc_info:
            linha["erro"] = self.formatException(record.exc_info)
        return json.dumps(linha, ensure_ascii=False, default=str)


class _ComRequestId(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_atual.get()
        return True


def configurar(em_producao: bool) -> None:
    json_ligado = em_producao or os.environ.get("LOG_JSON") == "1"
    h = logging.StreamHandler()
    if json_ligado:
        h.setFormatter(FormatoJson())
    else:
        h.addFilter(_ComRequestId())
        h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s [%(request_id)s] %(message)s"))
    raiz = logging.getLogger()
    raiz.handlers[:] = [h]
    raiz.setLevel(logging.INFO)


auditoria = logging.getLogger("astro.auditoria")


def evento(acao: str, **ids) -> None:
    """Evento de segurança no log (além da tabela de auditoria). Só ids e o tipo."""
    auditoria.info(acao, extra={"evento": acao, **{k: v for k, v in ids.items() if v is not None}})
