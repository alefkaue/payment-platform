"""Prova de compatibilidade: os MODELOS da aplicação (backend/app/db/models.py)
funcionando contra o banco MySQL do laboratório, pela conta svc_astro_api.

Faz o fluxo real: cadastro público (usuário + carteira + limite, com dado
pessoal cifrado pela própria aplicação), login do titular, isolamento entre
titulares, depósito pelo sistema com escopo assinado e extrato.

Uso (a partir da raiz do repositório):
  LAB=<pasta dos .cnf>  PYLIBS=<pasta com pymysql>  backend/.venv/Scripts/python \
      db-mysql/integracao-app/teste_orm_lab.py

As chaves abaixo são as chaves PÚBLICAS de teste do backend/tests/conftest.py.
A chave de contexto do laboratório precisa ser a mesma (ver README, passo 6).
"""
import configparser
import os
import secrets
import sys
from decimal import Decimal
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / 'backend'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
if os.environ.get('PYLIBS'):
    sys.path.insert(0, os.environ['PYLIBS'])

os.environ.update({
    'DATABASE_URL': 'sqlite://',  # o engine padrão da app não é usado aqui
    'JWT_SECRET': 'test-secret-nao-use-em-producao-32b+',
    'EMBEDDING_KEY': 'OTglUQywNhpctpSAKAF71Rz5qH8BLx5plpEZLSij0kk=',
    'WEBHOOK_KEYS': 'd2ViaG9vay10ZXN0ZS1jaGF2ZS0zMi1ieXRlcyEhISE=',
    'PII_KEYS': 'Hx8fHx8fHx8fHx8fHx8fHx8fHx8fHx8fHx8fHx8fHx8=',
    'PII_INDEX_KEY': 'ICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICA=',
    'DATABASE_CONTEXT_KEY': 'ISEhISEhISEhISEhISEhISEhISEhISEhISEhISEhISE=',
    'AMBIENTE': 'desenvolvimento',
})

from sqlalchemy import URL, create_engine, event, func, select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.db import isolamento  # noqa: E402
from app.db import models as m  # noqa: E402
from contexto_mysql import aplicar_contexto_mysql  # noqa: E402

cnf = configparser.RawConfigParser()  # Raw: senha sorteada pode ter '%'
cnf.read(Path(os.environ['LAB']) / 'svc_astro_api.cnf')
api = cnf['client']
senha = api['password']
if len(senha) > 1 and senha[0] == senha[-1] and senha[0] in ('"', "'"):
    senha = senha[1:-1]  # o arquivo .cnf do MySQL aceita o valor entre aspas
engine = create_engine(
    URL.create('mysql+pymysql', username=api['user'], password=senha,
               host=api['host'], port=int(api['port']), database='astro'),
    connect_args={'ssl': {'ca': api['ssl-ca']}}, hide_parameters=True)


@event.listens_for(Session, 'after_begin')
def _contexto(session, _transacao, connection):
    if connection.dialect.name == 'mysql':
        aplicar_contexto_mysql(connection, isolamento._contexto.get(),
                               chave_b64=os.environ['DATABASE_CONTEXT_KEY'],
                               carteiras_operacao=session.info.get('carteiras_operacao'))


falhas = 0


def confere(nome, ok, detalhe=''):
    global falhas
    falhas += 0 if ok else 1
    print(f"{'OK   ' if ok else 'FALHA'} {nome}{(' -> ' + str(detalhe)) if detalhe else ''}")


sufixo = secrets.randbelow(10**8)
email = f'fernanda{sufixo}@astro.test'
cpf = f'{secrets.randbelow(10**11):011d}'

# 1) Cadastro público: usuário + carteira + limite na MESMA transação.
token = isolamento._contexto.set({'modo': 'publico', 'usuario_id': None})
with Session(engine) as s:
    u = m.Usuario(nome='Fernanda Teste', cpf=cpf, email=email,
                  senha_hash='$argon2id$v=19$m=19456,t=2,p=1$c2FsdA$aGFzaA')
    s.add(u)
    s.flush()
    c = m.Carteira(titular_tipo=m.TipoPessoa.PF, usuario_id=u.id, numero=f'{sufixo:08d}-0')
    s.add(c)
    s.flush()
    s.add(m.Limite(carteira_id=c.id, por_transacao=Decimal('1000'), diurno=Decimal('5000'), noturno=Decimal('500')))
    s.commit()
    uid, cid = u.id, c.id
isolamento._contexto.reset(token)
confere('cadastro publico pelo ORM (usuario, carteira, limite)', bool(uid and cid), f'usuario {uid}, carteira {cid}')

with engine.connect() as conn:
    bruto = conn.exec_driver_sql('SELECT 1').scalar()
confere('conexao da API usa TLS e conta sem privilegio extra', bruto == 1)

# 2) Titular logado: busca por e-mail cifrado, isolamento.
with isolamento.contexto_teste(uid), Session(engine) as s:
    achado = s.scalar(select(m.Usuario).where(m.Usuario.email == email))
    confere('busca por e-mail cifrado (indice HMAC) e decifra o nome', achado is not None and achado.nome == 'Fernanda Teste',
            achado.nome if achado else None)
    visiveis = s.scalars(select(m.Carteira.id)).all()
    confere('titular so enxerga a propria carteira', visiveis == [cid], visiveis)
    confere('carteira de outro titular (id 4) nao aparece', s.get(m.Carteira, 4) is None)
    s.rollback()

with isolamento.contexto_teste(uid), Session(engine) as s:
    propria = s.get(m.Carteira, cid)
    propria.saldo = Decimal('1000000')
    try:
        s.commit()
        confere('titular NAO consegue mudar o proprio saldo sem escopo', False)
    except Exception as erro:  # o trigger recusa
        s.rollback()
        confere('titular NAO consegue mudar o proprio saldo sem escopo', 'escopo' in str(erro.orig), erro.orig.args[1])

# 3) Depósito feito pelo sistema, com as duas carteiras no escopo assinado.
with isolamento.contexto_teste(sistema=True), Session(engine) as s:
    s.info['carteiras_operacao'] = {1, cid}
    caixa = s.get(m.Carteira, 1, with_for_update=True)
    destino = s.get(m.Carteira, cid, with_for_update=True)
    valor = Decimal('250.00')
    t = m.Transacao(origem_carteira_id=1, destino_carteira_id=cid, tipo='deposito', valor_bruto=valor,
                    liquido=valor, tipo_destino=m.TipoPessoa.PF, auth_metodo=m.AuthMetodo.SISTEMA,
                    idempotency_key=f'orm-deposito-{sufixo}')
    s.add(t)
    s.flush()
    s.add_all([
        m.HistoricoSaldo(carteira_id=1, saldo_anterior=caixa.saldo, saldo_novo=caixa.saldo - valor,
                         motivo='deposito', transacao_id=t.id),
        m.HistoricoSaldo(carteira_id=cid, saldo_anterior=destino.saldo, saldo_novo=destino.saldo + valor,
                         motivo='deposito', transacao_id=t.id),
    ])
    caixa.saldo -= valor
    destino.saldo += valor
    s.commit()
    confere('deposito do sistema pelo ORM (transacao + saldo + ledger)', True, f'transacao {t.id}')

# 4) Titular vê o saldo e o extrato dele.
with isolamento.contexto_teste(uid), Session(engine) as s:
    saldo = s.scalar(select(m.Carteira.saldo).where(m.Carteira.id == cid))
    extrato = s.scalar(select(func.count()).select_from(m.HistoricoSaldo))
    confere('titular ve saldo 250.00 e 1 linha de extrato', saldo == Decimal('250.00') and extrato == 1,
            f'saldo {saldo}, extrato {extrato}')

print(f'\n{falhas} falha(s)')
sys.exit(1 if falhas else 0)
