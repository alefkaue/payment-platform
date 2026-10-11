"""Cifra/rotaciona registros numa transação, com API parada e papel migrador."""
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import create_engine, text
from app.core.dados_pessoais import cifrar, decifrar, validar_configuracao
from app.core.config import get_settings
from app.db.dados_cifrados import CAMPOS, JSON_CAMPOS


def migrar(connection):
    validar_configuracao(get_settings())
    total = 0
    # O dono pode transformar a representação, preservando a trilha; rollback
    # também reverte o DDL se alguma autenticação/cifragem falhar.
    postgres = connection.dialect.name == "postgresql"
    pausar_trilha = postgres and bool(connection.scalar(text(
        "SELECT EXISTS(SELECT 1 FROM pg_trigger WHERE tgname='trg_logs_auditoria_imutavel' AND tgrelid='public.logs_auditoria'::regclass)")))
    if pausar_trilha:
        connection.execute(text("ALTER TABLE logs_auditoria DISABLE TRIGGER trg_logs_auditoria_imutavel"))
    for tabela, campos in CAMPOS.items():
        nomes = ','.join('"'+c+'"' for c in campos)
        ultimo = 0
        while True:
            sql = f'SELECT id,{nomes} FROM "{tabela}" WHERE id > :ultimo ORDER BY id LIMIT 500'
            if postgres:
                sql += ' FOR UPDATE'
            rows = connection.execute(text(sql), {'ultimo': ultimo}).mappings().all()
            if not rows:
                break
            for row in rows:
                valores = {'id': row['id']}
                for coluna, dominio in campos.items():
                    formato = 'data' if coluna == 'data_nascimento' else ('json' if coluna in JSON_CAMPOS else 'texto')
                    claro = decifrar(row[coluna], tabela+'.'+coluna, dominio, formato, permitir_legado=True)
                    valores[coluna] = cifrar(claro, tabela+'.'+coluna, dominio, formato)
                connection.execute(text(f'UPDATE "{tabela}" SET '+','.join(f'"{c}" = :{c}' for c in campos)+' WHERE id=:id'), valores)
                total += 1
                ultimo = row['id']
    if pausar_trilha:
        connection.execute(text("ALTER TABLE logs_auditoria ENABLE TRIGGER trg_logs_auditoria_imutavel"))
    if postgres:
        for tabela, campos in CAMPOS.items():
            for coluna in campos:
                connection.execute(text(f"ALTER TABLE {tabela} VALIDATE CONSTRAINT ck_pii_{tabela}_{coluna}"))
    return total


if __name__ == '__main__':
    url = os.environ.get('DATABASE_MIGRATION_URL')
    if not url:
        raise SystemExit('Defina DATABASE_MIGRATION_URL, PII_KEYS e PII_INDEX_KEY no ambiente protegido.')
    engine = create_engine(url,hide_parameters=True)
    try:
        with engine.begin() as conn:
            total = migrar(conn)
        print('Registros cifrados/rotacionados:',total)
    except Exception:
        raise SystemExit('Cifragem não concluída; transação revertida. Confira configuração e esquema.') from None
    finally:
        engine.dispose()
