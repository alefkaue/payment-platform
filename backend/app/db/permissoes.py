"""Permissões explícitas da API. Tabela nova exige revisão deste contrato."""
TABELAS_RUNTIME = frozenset({
    'autorizacoes_recorrentes', 'carteiras', 'cartoes', 'chaves_pix', 'cobrancas',
    'contestacoes', 'creditos_tributarios', 'desafios_biometria', 'dispositivos',
    'documentos_empresa', 'documentos_identidade', 'dpop_jtis', 'empresas',
    'funcionarios', 'historico_saldo', 'kyc_casos', 'limites', 'logs_auditoria',
    'operacoes_pendentes', 'pontos_movimentos', 'produtos', 'refresh_tokens',
    'rendimentos', 'repasses_tributo', 'sessoes_mfa', 'split_liquidacoes',
    'transacoes', 'usuarios', 'vinculos', 'voos', 'webhook_entregas', 'webhooks',
})
# Exclusão física só é usada para remover chave Pix e limpar provas DPoP expiradas.
TABELAS_DELETE = frozenset({'chaves_pix', 'dpop_jtis'})
TABELAS_APPEND_ONLY = frozenset({
    'historico_saldo', 'logs_auditoria', 'pontos_movimentos', 'creditos_tributarios',
    'rendimentos', 'sessoes_mfa', 'documentos_identidade', 'documentos_empresa',
})
COLUNAS_UPDATE = {
    'transacoes': frozenset({'status', 'bloqueio_ate'}),
    'usuarios': frozenset({'senha_hash', 'embedding_facial_cifrado', 'kyc_status', 'ativo', 'pontos'}),
    'carteiras': frozenset({'saldo', 'saldo_bloqueado'}),
}
COLUNAS_TRANSACAO_UPDATE = COLUNAS_UPDATE['transacoes']


def privilegios_tabela(nome: str) -> tuple[str, ...]:
    permitidos = ['SELECT', 'INSERT']
    if nome not in TABELAS_APPEND_ONLY and nome not in COLUNAS_UPDATE:
        permitidos.append('UPDATE')
    if nome in TABELAS_DELETE:
        permitidos.append('DELETE')
    return tuple(permitidos)
