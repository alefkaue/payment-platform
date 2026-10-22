"""Gera os triggers AFTER de auditoria do 04_triggers_auditoria.sql.

Uso (a partir de db-mysql/):  python ferramentas/gerar_auditoria.py
Reescreve só o trecho depois do marcador "-- A2." no arquivo 04. Rode de novo
sempre que mudar a lista abaixo; o .sql gerado é o que vai para o banco.
"""
from pathlib import Path

# tabela -> (colunas copiadas para a trilha, colunas sensíveis: só o NOME entra)
AUDITADAS = {
    'usuarios': (['id', 'papel', 'kyc_status', 'ativo', 'pontos', 'totp_passo_usado', 'criado_em'],
                 ['nome', 'cpf', 'email', 'celular', 'data_nascimento', 'senha_hash',
                  'embedding_facial_cifrado', 'totp_segredo']),
    'empresas': (['id', 'porte', 'regime_apuracao', 'cnae', 'setor', 'situacao_cadastral', 'verificada_em',
                  'verificada_por', 'representante_usuario_id', 'kyb_status', 'criado_em'],
                 ['cnpj', 'razao_social', 'nome_fantasia']),
    'vinculos': (['id', 'usuario_id', 'empresa_id', 'cargo', 'papel', 'alcada', 'alcada_diaria', 'status',
                  'ativo', 'criado_por_usuario_id', 'aceito_em', 'status_em', 'criado_em'],
                 ['cpf', 'nome', 'email', 'celular']),
    'carteiras': (['id', 'titular_tipo', 'usuario_id', 'empresa_id', 'sistema', 'agencia', 'numero', 'saldo',
                   'saldo_bloqueado', 'criado_em'], []),
    'transacoes': (['id', 'origem_carteira_id', 'destino_carteira_id', 'tipo', 'valor_bruto', 'cbs', 'ibs',
                    'liquido', 'tipo_destino', 'aplicou_split', 'auth_metodo', 'status', 'bloqueio_ate',
                    'autor_usuario_id', 'dispositivo_id', 'idempotency_key', 'transacao_original_id', 'criado_em'],
                   ['descricao', 'verificacao_facial']),
    'split_liquidacoes': (['id', 'transacao_id', 'natureza', 'carteira_destino_id', 'valor', 'repasse_id',
                           'estornada', 'criado_em'], []),
    'repasses_tributo': (['id', 'cbs_total', 'ibs_total', 'corte', 'criado_em'], []),
    'creditos_tributarios': (['id', 'empresa_id', 'tributo', 'valor', 'fonte', 'referencia', 'consultado_em'], []),
    'cobrancas': (['id', 'txid', 'recebedor_carteira_id', 'valor', 'vencimento', 'nfe_chave', 'cbs', 'ibs',
                   'linha_digitavel', 'status', 'grupo_parcelamento', 'parcela_numero', 'parcelas_total',
                   'autorizacao_id', 'transacao_id', 'paga_em', 'criado_por_usuario_id', 'criado_em'],
                  ['descricao', 'pagador_documento']),
    'autorizacoes_recorrentes': (['id', 'recebedor_carteira_id', 'pagador_carteira_id', 'valor_maximo',
                                  'periodicidade', 'status', 'aceita_em', 'cancelada_em', 'criado_em'],
                                 ['descricao']),
    'chaves_pix': (['id', 'carteira_id', 'tipo', 'valor_indice', 'criado_em'], ['valor']),
    'operacoes_pendentes': (['id', 'empresa_id', 'tipo', 'valor', 'aprovacoes_necessarias',
                             'criado_por_usuario_id', 'status', 'decidido_por_usuario_id', 'decidido_em',
                             'criado_em', 'idempotency_key'],
                            ['payload', 'descricao', 'aprovacoes', 'resultado']),
    'contestacoes': (['id', 'transacao_id', 'aberta_por_usuario_id', 'status', 'valor_devolvido', 'decidida_em',
                      'criado_em'], ['motivo']),
    'limites': (['id', 'carteira_id', 'por_transacao', 'diurno', 'noturno', 'pendente_por_transacao',
                 'pendente_diurno', 'pendente_noturno', 'pendente_vigente_em'], []),
    'funcionarios': (['id', 'empresa_id', 'cargo', 'salario', 'ativo', 'criado_por_usuario_id', 'criado_em',
                      'desligado_em'], ['nome', 'cpf']),
    'webhooks': (['id', 'empresa_id', 'url', 'eventos', 'ativo', 'criado_em'], ['segredo']),
    'cartoes': (['id', 'carteira_id', 'apelido', 'numero_masc', 'bandeira', 'validade', 'virtual', 'estado',
                 'compras_online', 'compras_internacionais', 'limite', 'criado_em'], []),
    'dispositivos': (['id', 'usuario_id', 'id_hash', 'nome', 'confiavel', 'confiavel_em', 'bloqueado',
                      'bloqueado_em', 'removido', 'atestacao', 'criado_em'], []),
}
# AFTER INSERT destas também anota o cadastro feito nesta transação.
CADASTRO = {'usuarios', 'empresas', 'carteiras'}


def col(lado, nome):
    return f'{lado}.`{nome}`'


def objeto(lado, colunas):
    pares = ', '.join(f"'{c}', {col(lado, c)}" for c in colunas)
    return f'JSON_OBJECT({pares})'


def sensiveis_alterados(colunas):
    itens = ', '.join(f"IF({col('OLD', c)} <=> {col('NEW', c)}, NULL, '{c}')" for c in colunas)
    return f'CONCAT_WS(\',\', {itens})'


def gerar():
    partes = []
    for tabela, (copiadas, sensiveis) in AUDITADAS.items():
        depois = objeto('NEW', copiadas)
        antes = objeto('OLD', copiadas)
        cadastro = ''
        if tabela in CADASTRO:
            cadastro = (
                "  SET c = astro_privado.ctx();\n"
                "  IF c IS NOT NULL THEN\n"
                "    DELETE FROM astro_privado.cadastro_sessao\n"
                "     WHERE conexao = CONNECTION_ID() AND criado_em < UTC_TIMESTAMP(6) - INTERVAL 2 MINUTE;\n"
                "    INSERT INTO astro_privado.cadastro_sessao (conexao, tx, tabela, registro_id, criado_em)\n"
                f"    VALUES (CONNECTION_ID(), JSON_VALUE(c, '$.tx'), '{tabela}', NEW.id, UTC_TIMESTAMP(6));\n"
                "  END IF;\n")
        partes.append(
            f"CREATE TRIGGER trg_aud_{tabela}_ins AFTER INSERT ON {tabela} FOR EACH ROW\nBEGIN\n"
            + ("  DECLARE c JSON;\n" + cadastro if cadastro else '')
            + f"  CALL astro_auditoria.registrar('{tabela}', 'INSERT', NEW.id, NULL, {depois});\nEND$$\n")
        mudou = ' AND '.join(f"{col('OLD', c)} <=> {col('NEW', c)}" for c in copiadas + sensiveis)
        if sensiveis:
            depois_upd = f"JSON_SET({depois}, '$.sensiveis_alterados', {sensiveis_alterados(sensiveis)})"
        else:
            depois_upd = depois
        partes.append(
            f"CREATE TRIGGER trg_aud_{tabela}_upd AFTER UPDATE ON {tabela} FOR EACH ROW\nBEGIN\n"
            f"  IF NOT ({mudou}) THEN\n"
            f"    CALL astro_auditoria.registrar('{tabela}', 'UPDATE', NEW.id, {antes}, {depois_upd});\n"
            "  END IF;\nEND$$\n")
        partes.append(
            f"CREATE TRIGGER trg_aud_{tabela}_del AFTER DELETE ON {tabela} FOR EACH ROW\n"
            f"  CALL astro_auditoria.registrar('{tabela}', 'DELETE', OLD.id, {antes}, NULL)$$\n")
    return '\n'.join(partes) + '\nDELIMITER ;\n'


if __name__ == '__main__':
    arquivo = Path(__file__).resolve().parents[1] / '04_triggers_auditoria.sql'
    texto = arquivo.read_text(encoding='utf-8')
    marcador = 'USE astro_dados;\nDELIMITER $$\n'
    cabecalho, _, _ = texto.rpartition(marcador)
    arquivo.write_text(cabecalho + marcador + '\n' + gerar(), encoding='utf-8', newline='\n')
    print(f'{len(AUDITADAS) * 3} triggers de auditoria gerados em {arquivo.name}')
