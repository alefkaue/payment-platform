"""Ações sensíveis não confirmam sem a trilha na mesma transação."""
import pytest
from sqlalchemy import event, select, func
from decimal import Decimal
from app.db.models import LogAuditoria
from app.repositories import get_repository
from tests.helpers import Pessoa


def preparar(cliente, operacao):
    pessoa = Pessoa(cliente, 'auditoria.atomica@ex.com')
    repo = get_repository()
    u = repo.obter_usuario_por_login(pessoa.email)
    if operacao in {'sessao', 'outras_sessoes', 'sessoes_dispositivo'}:
        sessoes = repo.listar_sessoes(u['id'])
        assert sessoes
        if operacao == 'sessao':
            alterar = lambda: repo.revogar_sessao(u['id'], sessoes[0]['sessao_id'])
        elif operacao == 'outras_sessoes':
            alterar = lambda: repo.revogar_outras_sessoes(u['id'], None)
        else:
            alterar = lambda: repo.revogar_sessoes_do_dispositivo(u['id'], sessoes[0]['dispositivo']['id'])
        return repo, alterar, lambda: repo.listar_sessoes(u['id'])
    if operacao in {'kyb', 'funcionario'}:
        empresa = pessoa.abrir_empresa()
        eid = repo.obter_conta_por_numero(empresa['numero'])['empresa_id']
        if operacao == 'kyb':
            return repo, lambda: repo.atualizar_kyb_status(eid, 'reprovado'), lambda: repo.obter_empresa(eid)['kyb_status']
        from tests.helpers import gerar_cpf
        f = repo.criar_funcionario(empresa_id=eid, nome='Teste', cpf=gerar_cpf(), cargo=None, salario=None, criado_por=u['id'])
        return repo, lambda: repo.desligar_funcionario(eid, f['id']), lambda: repo.obter_funcionario(f['id'])['ativo']
    if operacao == 'limite':
        conta = repo.obter_conta_por_numero(pessoa.numero)
        cid = conta['carteira_id']
        return repo, lambda: repo.salvar_limite(cid, imediatos={'por_transacao': Decimal('1')}, pendentes={}, vigente_em=None), lambda: repo.obter_limite(cid)['por_transacao']
    if operacao in {'vinculo', 'desativar_vinculo'}:
        empresa = pessoa.abrir_empresa()
        c = repo.obter_conta_por_numero(empresa['numero'])
        v = repo.obter_vinculo(u['id'], c['empresa_id'])
        alterar = (lambda: repo.desativar_vinculo(v['id'], c['empresa_id'])) if operacao == 'desativar_vinculo' else (lambda: repo.atualizar_vinculo(v['id'], status='suspenso'))
        return repo, alterar, lambda: repo.obter_vinculo_por_id(v['id'])['status']
    if operacao == 'senha':
        return repo, lambda: repo.atualizar_senha_hash(u['id'], 'hash-novo-teste'), lambda: repo.obter_usuario_por_login(pessoa.email)['senha_hash']
    if operacao == 'kyc':
        caso = repo.criar_caso_kyc(tipo='pf', status='em_analise', nivel_risco='medio', motivos=[], usuario_id=u['id'])
        return repo, lambda: repo.decidir_caso_kyc(caso['id'], 'aprovado'), lambda: repo.ultimo_caso_kyc(usuario_id=u['id'])['status']
    d = repo.registrar_dispositivo(usuario_id=u['id'], id_hash='hash-dispositivo-teste', nome='teste')
    if operacao == 'desbloquear':
        repo.bloquear_dispositivo(u['id'], d['id'])
        return repo, lambda: repo.desbloquear_dispositivo(u['id'], d['id']), lambda: repo.obter_dispositivo(u['id'], 'hash-dispositivo-teste')['bloqueado']
    if operacao == 'confiar':
        return repo, lambda: repo.marcar_dispositivo_confiavel(u['id'], d['id']), lambda: repo.obter_dispositivo(u['id'], 'hash-dispositivo-teste')['confiavel']
    return repo, lambda: repo.bloquear_dispositivo(u['id'], d['id']), lambda: repo.obter_dispositivo(u['id'], 'hash-dispositivo-teste')['bloqueado']


@pytest.mark.parametrize('operacao', ['senha', 'kyc', 'confiar', 'bloquear', 'desbloquear', 'vinculo', 'limite', 'sessao', 'outras_sessoes', 'sessoes_dispositivo', 'kyb', 'funcionario', 'desativar_vinculo'])
def test_trilha_indisponivel_reverte_acao(cliente, operacao):
    repo, alterar, estado = preparar(cliente, operacao)
    antes = estado()
    def falhar(session, *_):
        if any(isinstance(obj, LogAuditoria) and obj.acao.endswith('_atomico') for obj in session.new):
            raise RuntimeError('Auditoria indisponível no teste.')
    event.listen(repo._sf, 'before_flush', falhar)
    try:
        with pytest.raises(RuntimeError, match='Auditoria indisponível'):
            alterar()
    finally:
        event.remove(repo._sf, 'before_flush', falhar)
    assert estado() == antes


@pytest.mark.parametrize('operacao', ['senha', 'kyc', 'confiar', 'bloquear', 'desbloquear', 'vinculo', 'limite', 'sessao', 'outras_sessoes', 'sessoes_dispositivo', 'kyb', 'funcionario', 'desativar_vinculo'])
def test_trilha_confirma_junto_sem_dados_brutos(cliente, operacao):
    repo, alterar, estado = preparar(cliente, operacao)
    antes = estado()
    with repo._sf() as s:
        quantidade = s.scalar(select(func.count(LogAuditoria.id)).where(LogAuditoria.acao.like('%_atomico')))
    alterar()
    assert estado() != antes
    with repo._sf() as s:
        registros = [r for r in s.scalars(select(LogAuditoria)) if r.acao.endswith('_atomico')]
    assert len(registros) == quantidade + 1
    assert 'hash-novo-teste' not in str([r.detalhe for r in registros])
    assert 'auditoria.atomica@ex.com' not in str([r.detalhe for r in registros])
