"""Roda DENTRO do job temporário no Azure: aplica a migração a7f0c2e14d55 (TOTP)
como dono das tabelas (astro_migrator) e libera à API o UPDATE das colunas novas."""
import os

import psycopg2

con = psycopg2.connect(os.environ["DATABASE_ADMIN_URL"])
cur = con.cursor()
cur.execute("SELECT version_num FROM alembic_version")
print("versao antes:", cur.fetchall(), flush=True)
try:
    cur.execute("GRANT astro_migrator TO CURRENT_USER WITH SET TRUE")
    con.commit()
except psycopg2.Error as e:  # já membro: segue
    print("grant:", e.pgerror, flush=True)
    con.rollback()
cur.execute("SET ROLE astro_migrator")
cur.execute("ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS totp_segredo varchar(64)")
cur.execute("ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS totp_passo_usado integer")
cur.execute("GRANT UPDATE (totp_segredo, totp_passo_usado) ON usuarios TO astro_app")
cur.execute("UPDATE alembic_version SET version_num = 'a7f0c2e14d55' WHERE version_num = 'f41b26ce0133'")
cur.execute("RESET ROLE")
con.commit()
cur.execute("SELECT version_num FROM alembic_version")
print("versao depois:", cur.fetchall(), flush=True)
cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='usuarios' AND column_name LIKE 'totp%'")
print("colunas:", cur.fetchall(), flush=True)
print("MIGRACAO OK", flush=True)
