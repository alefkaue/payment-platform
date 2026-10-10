"""Contrato de integridade v1. Imutável: novas regras exigem nova versão/migração."""

CHECKS = {
    "usuarios": [("ck_usuario_pontos", "pontos >= 0"),
                 ("ck_usuario_kyc", "kyc_status IN ('pendente','em_analise','aprovado','reprovado')")],
    "empresas": [("ck_empresa_porte", "porte IN ('MEI','PME','GRANDE')"),
                 ("ck_empresa_kyb", "kyb_status IN ('pendente','em_analise','aprovado','reprovado')")],
    "vinculos": [("ck_vinculo_alcada", "alcada IS NULL OR alcada >= 0"),
                 ("ck_vinculo_alcada_diaria", "alcada_diaria IS NULL OR alcada_diaria >= 0"),
                 ("ck_vinculo_status", "status IN ('pendente','aguardando','ativo','suspenso','revogado','recusado')"),
                 ("ck_vinculo_ativo", "ativo = (status = 'ativo')"),
                 ("ck_vinculo_titular", "status <> 'ativo' OR usuario_id IS NOT NULL")],
    "carteiras": [("ck_carteira_titular", "(titular_tipo = 'PF' AND usuario_id IS NOT NULL AND empresa_id IS NULL AND sistema IS NULL) OR (titular_tipo = 'PJ' AND empresa_id IS NOT NULL AND usuario_id IS NULL AND sistema IS NULL) OR (titular_tipo = 'SISTEMA' AND usuario_id IS NULL AND empresa_id IS NULL AND sistema IS NOT NULL AND sistema IN ('CAIXA','TRIBUTOS','FISCO'))"),
                  ("ck_carteira_saldo", "saldo >= 0 OR (titular_tipo = 'SISTEMA' AND sistema = 'CAIXA')"),
                  ("ck_carteira_bloqueado", "saldo_bloqueado >= 0")],
    "transacoes": [("ck_transacao_valores", "valor_bruto > 0 AND liquido >= 0 AND cbs >= 0 AND ibs >= 0"),
                   ("ck_transacao_contas", "origem_carteira_id <> destino_carteira_id"),
                   ("ck_transacao_tipo", "tipo IN ('transferencia','cobranca','deposito','rendimento','repasse_tributo','devolucao','estorno','resgate_pontos')"),
                   ("ck_transacao_conservacao", "(tipo = 'repasse_tributo' AND NOT aplicou_split AND valor_bruto = liquido AND round(valor_bruto, 2) = round(cbs + ibs, 2)) OR (tipo <> 'repasse_tributo' AND round(valor_bruto, 2) = round(liquido + cbs + ibs, 2) AND (aplicou_split OR (cbs = 0 AND ibs = 0)))"),
                   ("ck_transacao_split", "NOT aplicou_split OR tipo IN ('cobranca','resgate_pontos')")],
    "historico_saldo": [("ck_historico_bloqueado", "bloqueado_anterior >= 0 AND bloqueado_novo >= 0")],
    "split_liquidacoes": [("ck_split_valor", "valor >= 0"),
                          ("ck_split_natureza", "natureza IN ('CBS','IBS','LIQUIDO')"),
                          ("ck_split_repasse", "NOT estornada OR repasse_id IS NULL")],
    "repasses_tributo": [("ck_repasse_totais", "cbs_total >= 0 AND ibs_total >= 0 AND cbs_total + ibs_total > 0")],
    "creditos_tributarios": [("ck_credito_valor", "valor >= 0"), ("ck_credito_tributo", "tributo IN ('CBS','IBS')")],
    "cobrancas": [("ck_cobranca_valores", "valor > 0 AND cbs >= 0 AND ibs >= 0 AND cbs + ibs <= valor"),
                  ("ck_cobranca_nota", "nfe_chave IS NOT NULL OR (cbs = 0 AND ibs = 0)"),
                  ("ck_cobranca_parcelas", "parcela_numero >= 1 AND parcelas_total >= parcela_numero"),
                  ("ck_cobranca_status", "status IN ('aberta','paga','cancelada','estornada')"),
                  ("ck_cobranca_pagamento", "status NOT IN ('paga','estornada') OR (transacao_id IS NOT NULL AND paga_em IS NOT NULL)")],
    "autorizacoes_recorrentes": [("ck_autorizacao_valor", "valor_maximo > 0"),
                                ("ck_autorizacao_contas", "pagador_carteira_id <> recebedor_carteira_id"),
                                ("ck_autorizacao_periodo", "periodicidade IN ('semanal','mensal','anual')"),
                                ("ck_autorizacao_status", "status IN ('pendente','ativa','cancelada','recusada')")],
    "operacoes_pendentes": [("ck_pendente_valor", "valor >= 0"),
                           ("ck_pendente_aprovacoes", "aprovacoes_necessarias IN (1,2)"),
                           ("ck_pendente_status", "status IN ('pendente','aprovada','rejeitada','falhou','expirada','cancelada','executando')")],
    "contestacoes": [("ck_contestacao_valor", "valor_devolvido >= 0"),
                     ("ck_contestacao_status", "status IN ('aberta','procedente','improcedente')")],
    "limites": [("ck_limite_valores", "por_transacao >= 0 AND diurno >= 0 AND noturno >= 0"),
                ("ck_limite_pendentes", "(pendente_por_transacao IS NULL OR pendente_por_transacao >= 0) AND (pendente_diurno IS NULL OR pendente_diurno >= 0) AND (pendente_noturno IS NULL OR pendente_noturno >= 0)")],
    "chaves_pix": [("ck_chave_tipo", "tipo IN ('cpf','cnpj','email','celular','aleatoria')")],
    "kyc_casos": [("ck_kyc_tipo", "tipo IN ('pf','pj')"),
                  ("ck_kyc_status", "status IN ('aprovado','em_analise','reprovado')")],
    "documentos_empresa": [("ck_documento_tamanho", "tamanho > 0")],
    "funcionarios": [("ck_funcionario_salario", "salario IS NULL OR salario > 0")],
    "webhook_entregas": [("ck_entrega_tentativas", "tentativas >= 0"),
                        ("ck_entrega_status", "status IN ('pendente','entregue','falhou')")],
    "rendimentos": [("ck_rendimento_valores", "saldo_base > 0 AND valor > 0 AND taxa_diaria > 0")],
    "produtos": [("ck_produto_preco", "preco > 0")],
    "voos": [("ck_voo_preco", "preco > 0 AND milhas > 0")],
    "cartoes": [("ck_cartao_limite", "limite >= 0")],
}

UNIQUES = {
    "carteiras": [("uq_carteira_usuario", ["usuario_id"]), ("uq_carteira_empresa", ["empresa_id"])],
    "split_liquidacoes": [("uq_split_transacao_natureza", ["transacao_id", "natureza"])],
    "cobrancas": [("uq_cobranca_transacao", ["transacao_id"])],
}

INDEXES = {
    "transacoes": [("ix_transacoes_origem_criado", ["origem_carteira_id", "criado_em"]),
                   ("ix_transacoes_destino_criado", ["destino_carteira_id", "criado_em"]),
                   ("ix_transacoes_status_bloqueio", ["status", "bloqueio_ate"])],
    "historico_saldo": [("ix_historico_transacao", ["transacao_id"])],
    "refresh_tokens": [("ix_refresh_sessao_ativa", ["sessao_id", "revogado", "expira_em"])],
    "sessoes_mfa": [("ix_mfa_referencia_tipo_criado", ["referencia", "tipo", "criado_em"]),
                    ("ix_mfa_ip_tipo_criado", ["ip", "tipo", "criado_em"])],
    "split_liquidacoes": [("ix_split_repasse_pendente", ["natureza", "estornada", "repasse_id", "criado_em"])],
    "webhook_entregas": [("ix_entregas_status_tentativas", ["status", "tentativas"])],
}

# Limite superior também recusa NaN/Infinity no NUMERIC do Postgres.
NUMERICOS = {'vinculos': ['alcada', 'alcada_diaria'], 'carteiras': ['saldo', 'saldo_bloqueado'], 'transacoes': ['valor_bruto', 'cbs', 'ibs', 'liquido'], 'historico_saldo': ['saldo_anterior', 'saldo_novo', 'bloqueado_anterior', 'bloqueado_novo'], 'split_liquidacoes': ['valor'], 'repasses_tributo': ['cbs_total', 'ibs_total'], 'creditos_tributarios': ['valor'], 'cobrancas': ['valor', 'cbs', 'ibs'], 'autorizacoes_recorrentes': ['valor_maximo'], 'operacoes_pendentes': ['valor'], 'contestacoes': ['valor_devolvido'], 'limites': ['por_transacao', 'diurno', 'noturno', 'pendente_por_transacao', 'pendente_diurno', 'pendente_noturno'], 'funcionarios': ['salario'], 'rendimentos': ['saldo_base', 'valor', 'taxa_diaria'], 'produtos': ['preco'], 'voos': ['preco'], 'cartoes': ['limite']}
for _tabela, _colunas in NUMERICOS.items():
    for _coluna in _colunas:
        CHECKS.setdefault(_tabela, []).append((f"ck_{_tabela}_{_coluna}_finito", f"{_coluna} IS NULL OR ({_coluna} > -1000000000000 AND {_coluna} < 1000000000000)"))
