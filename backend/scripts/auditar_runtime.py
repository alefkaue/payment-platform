"""Auditoria somente leitura, sem dados de clientes nem credenciais na saída."""
import json
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import create_engine
from app.db.seguranca_runtime import problemas_permissoes

if __name__ == '__main__':
    engine = create_engine(os.environ['DATABASE_URL'], hide_parameters=True)
    with engine.connect() as connection:
        problemas = problemas_permissoes(connection)
    print(json.dumps({'seguro_conforme_politica': not problemas, 'problemas': problemas}, ensure_ascii=False))
    sys.exit(1 if problemas else 0)
