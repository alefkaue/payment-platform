-- =============================================================================
-- 03_views_procedures.sql  —  executar como svc_astro_migrator
-- =============================================================================
-- POR QUE VIEWS COM O MESMO NOME DAS TABELAS?
--   A API (SQLAlchemy) faz SELECT/INSERT/UPDATE em "usuarios", "carteiras"...
--   Se ela se conectar ao banco `astro`, esses nomes são VIEWS, não tabelas.
--   Uma view simples (uma tabela, sem GROUP BY) é ATUALIZÁVEL: INSERT e UPDATE
--   nela vão para a tabela real. Assim a aplicação continua funcionando, mas
--   toda linha passa pelo filtro do WHERE.
--
--   SQL SECURITY DEFINER  a view lê a tabela real com o privilégio do DONO da
--                         view (o migrador), não da API, que não tem nenhum.
--   ALGORITHM = MERGE     o WHERE da view é fundido na consulta da API; um
--                         SELECT por id continua usando a chave primária.
--   WITH CHECK OPTION     INSERT/UPDATE pela view só é aceito se a linha
--                         resultante continuar visível (= o WITH CHECK do RLS).
--                         Onde a regra de escrita é diferente da de leitura
--                         (carteiras, cadastro...), quem decide é um trigger (04).
-- =============================================================================

USE astro;

-- ---------------------------------------------------------------- pessoas
CREATE ALGORITHM=MERGE SQL SECURITY DEFINER VIEW usuarios AS
  SELECT * FROM astro_dados.usuarios WHERE astro_privado.pode_ler()
  WITH CHECK OPTION;

CREATE ALGORITHM=MERGE SQL SECURITY DEFINER VIEW empresas AS
  SELECT * FROM astro_dados.empresas WHERE astro_privado.pode_ler()
  WITH CHECK OPTION;

CREATE ALGORITHM=MERGE SQL SECURITY DEFINER VIEW vinculos AS
  SELECT * FROM astro_dados.vinculos WHERE astro_privado.pode_ler()
  WITH CHECK OPTION;

-- ---------------------------------------------------------------- dinheiro
-- Escrita em carteiras é conferida por trigger (cadastro x movimento de saldo).
CREATE ALGORITHM=MERGE SQL SECURITY DEFINER VIEW carteiras AS
  SELECT * FROM astro_dados.carteiras
   WHERE astro_privado.pode_ler_carteira(id, titular_tipo, usuario_id, empresa_id);

CREATE ALGORITHM=MERGE SQL SECURITY DEFINER VIEW transacoes AS
  SELECT * FROM astro_dados.transacoes
   WHERE astro_privado.pode_ler_transacao(origem_carteira_id, destino_carteira_id)
  WITH CHECK OPTION;

CREATE ALGORITHM=MERGE SQL SECURITY DEFINER VIEW historico_saldo AS
  SELECT * FROM astro_dados.historico_saldo
   WHERE astro_privado.pode_ler_historico(carteira_id)
  WITH CHECK OPTION;

CREATE ALGORITHM=MERGE SQL SECURITY DEFINER VIEW split_liquidacoes AS
  SELECT * FROM astro_dados.split_liquidacoes WHERE astro_privado.pode_ler()
  WITH CHECK OPTION;

CREATE ALGORITHM=MERGE SQL SECURITY DEFINER VIEW repasses_tributo AS
  SELECT * FROM astro_dados.repasses_tributo WHERE astro_privado.pode_ler()
  WITH CHECK OPTION;

-- NOVO: crédito tributário é informação fiscal da empresa; só ela (e o banco) vê.
CREATE ALGORITHM=MERGE SQL SECURITY DEFINER VIEW creditos_tributarios AS
  SELECT * FROM astro_dados.creditos_tributarios
   WHERE astro_privado.pode_ler_por_empresa(empresa_id);

CREATE ALGORITHM=MERGE SQL SECURITY DEFINER VIEW cobrancas AS
  SELECT * FROM astro_dados.cobrancas WHERE astro_privado.pode_ler()
  WITH CHECK OPTION;

CREATE ALGORITHM=MERGE SQL SECURITY DEFINER VIEW autorizacoes_recorrentes AS
  SELECT * FROM astro_dados.autorizacoes_recorrentes WHERE astro_privado.pode_ler()
  WITH CHECK OPTION;

-- Leitura livre (com contexto) para achar o destinatário de um Pix; criar ou
-- apagar chave só o dono (trigger no script 04).
CREATE ALGORITHM=MERGE SQL SECURITY DEFINER VIEW chaves_pix AS
  SELECT * FROM astro_dados.chaves_pix WHERE astro_privado.pode_ler()
  WITH CHECK OPTION;

-- NOVO: aprovação dupla só é vista por quem tem vínculo com a empresa.
CREATE ALGORITHM=MERGE SQL SECURITY DEFINER VIEW operacoes_pendentes AS
  SELECT * FROM astro_dados.operacoes_pendentes
   WHERE astro_privado.pode_ler_por_empresa(empresa_id)
  WITH CHECK OPTION;

-- NOVO: contestação só é vista por quem abriu ou pelos participantes.
CREATE ALGORITHM=MERGE SQL SECURITY DEFINER VIEW contestacoes AS
  SELECT * FROM astro_dados.contestacoes
   WHERE astro_privado.pode_ler_contestacao(transacao_id, aberta_por_usuario_id)
  WITH CHECK OPTION;

-- ---------------------------------------------------------------- segurança
CREATE ALGORITHM=MERGE SQL SECURITY DEFINER VIEW limites AS
  SELECT * FROM astro_dados.limites WHERE astro_privado.pode_ler_limite(carteira_id)
  WITH CHECK OPTION;

CREATE ALGORITHM=MERGE SQL SECURITY DEFINER VIEW dispositivos AS
  SELECT * FROM astro_dados.dispositivos WHERE astro_privado.pode_ler_por_usuario(usuario_id)
  WITH CHECK OPTION;

CREATE ALGORITHM=MERGE SQL SECURITY DEFINER VIEW dpop_jtis AS
  SELECT * FROM astro_dados.dpop_jtis WHERE astro_privado.pode_ler()
  WITH CHECK OPTION;

CREATE ALGORITHM=MERGE SQL SECURITY DEFINER VIEW desafios_biometria AS
  SELECT * FROM astro_dados.desafios_biometria WHERE astro_privado.pode_ler_desafio(usuario_id)
  WITH CHECK OPTION;

CREATE ALGORITHM=MERGE SQL SECURITY DEFINER VIEW refresh_tokens AS
  SELECT * FROM astro_dados.refresh_tokens WHERE astro_privado.pode_ler_por_usuario(usuario_id)
  WITH CHECK OPTION;

CREATE ALGORITHM=MERGE SQL SECURITY DEFINER VIEW sessoes_mfa AS
  SELECT * FROM astro_dados.sessoes_mfa WHERE astro_privado.pode_ler()
  WITH CHECK OPTION;

-- NOVO: a trilha de negócio só é lida pela própria pessoa, pela empresa dela ou
-- pelo banco. Gravar é livre (com contexto): o login que falhou de alguém
-- precisa virar log mesmo sem a pessoa estar logada.
CREATE ALGORITHM=MERGE SQL SECURITY DEFINER VIEW logs_auditoria AS
  SELECT * FROM astro_dados.logs_auditoria
   WHERE astro_privado.pode_ler_por_usuario(usuario_id)
      OR astro_privado.pode_ler_por_empresa(empresa_id);

-- ---------------------------------------------------------------- identidade
CREATE ALGORITHM=MERGE SQL SECURITY DEFINER VIEW kyc_casos AS
  SELECT * FROM astro_dados.kyc_casos WHERE astro_privado.pode_ler()
  WITH CHECK OPTION;

CREATE ALGORITHM=MERGE SQL SECURITY DEFINER VIEW documentos_identidade AS
  SELECT * FROM astro_dados.documentos_identidade WHERE astro_privado.pode_ler_documento(caso_id)
  WITH CHECK OPTION;

CREATE ALGORITHM=MERGE SQL SECURITY DEFINER VIEW documentos_empresa AS
  SELECT * FROM astro_dados.documentos_empresa WHERE astro_privado.pode_ler_por_empresa(empresa_id)
  WITH CHECK OPTION;

CREATE ALGORITHM=MERGE SQL SECURITY DEFINER VIEW funcionarios AS
  SELECT * FROM astro_dados.funcionarios WHERE astro_privado.pode_ler_por_empresa(empresa_id)
  WITH CHECK OPTION;

-- ---------------------------------------------------------------- produtos
CREATE ALGORITHM=MERGE SQL SECURITY DEFINER VIEW webhooks AS
  SELECT * FROM astro_dados.webhooks WHERE astro_privado.pode_ler()
  WITH CHECK OPTION;

CREATE ALGORITHM=MERGE SQL SECURITY DEFINER VIEW webhook_entregas AS
  SELECT * FROM astro_dados.webhook_entregas WHERE astro_privado.pode_ler()
  WITH CHECK OPTION;

-- NOVO: rendimento é extrato; só o dono lê. Quem grava é o job (modo sistema).
CREATE ALGORITHM=MERGE SQL SECURITY DEFINER VIEW rendimentos AS
  SELECT * FROM astro_dados.rendimentos WHERE astro_privado.pode_ler_por_carteira(carteira_id);

CREATE ALGORITHM=MERGE SQL SECURITY DEFINER VIEW produtos AS
  SELECT * FROM astro_dados.produtos WHERE astro_privado.pode_ler()
  WITH CHECK OPTION;

CREATE ALGORITHM=MERGE SQL SECURITY DEFINER VIEW voos AS
  SELECT * FROM astro_dados.voos WHERE astro_privado.pode_ler()
  WITH CHECK OPTION;

-- NOVO: extrato de pontos só da própria pessoa.
CREATE ALGORITHM=MERGE SQL SECURITY DEFINER VIEW pontos_movimentos AS
  SELECT * FROM astro_dados.pontos_movimentos WHERE astro_privado.pode_ler_por_usuario(usuario_id)
  WITH CHECK OPTION;

CREATE ALGORITHM=MERGE SQL SECURITY DEFINER VIEW cartoes AS
  SELECT * FROM astro_dados.cartoes WHERE astro_privado.pode_ler_por_carteira(carteira_id)
  WITH CHECK OPTION;


DELIMITER $$

-- =============================================================================
-- Rotinas que existiam no PostgreSQL (SECURITY DEFINER), agora em MySQL
-- =============================================================================

-- astro_documento_usado: responde SÓ "sim/não" se o documento já foi usado por
-- outra pessoa. Não devolve de quem é (o original fazia igual).
CREATE FUNCTION astro_documento_usado(p_resumo VARCHAR(140)) RETURNS BOOLEAN
NOT DETERMINISTIC READS SQL DATA SQL SECURITY DEFINER
BEGIN
  IF astro_privado.ctx() IS NULL OR p_resumo IS NULL
     OR p_resumo NOT REGEXP '^[0-9a-f]{64}(:[0-9a-f]{64})?$' THEN
    RETURN FALSE;
  END IF;
  RETURN EXISTS (SELECT 1 FROM astro_dados.documentos_identidade d
                   JOIN astro_dados.kyc_casos k ON k.id = d.caso_id
                  WHERE d.sha256 = p_resumo AND k.usuario_id IS NOT NULL);
END$$

-- astro_destinatario: acha UMA carteira de destino por exatamente um critério
-- (id, agência+número, conta de sistema ou PF de um usuário) e devolve só a
-- identificação — NUNCA o saldo. É assim que alguém paga outra pessoa sem
-- poder ler a carteira dela. No PG era função que retornava tabela; no MySQL
-- vira procedure que devolve um result set: CALL astro.astro_destinatario(...).
CREATE PROCEDURE astro_destinatario(IN p_id INT, IN p_numero VARCHAR(12), IN p_agencia VARCHAR(4),
                                    IN p_sistema VARCHAR(20), IN p_usuario INT)
READS SQL DATA SQL SECURITY DEFINER
BEGIN
  DECLARE c JSON DEFAULT astro_privado.ctx();
  IF c IS NULL OR astro_privado.ctx_modo(c) NOT IN ('usuario','sistema')
     OR ((p_id IS NOT NULL) + (p_numero IS NOT NULL) + (p_sistema IS NOT NULL) + (p_usuario IS NOT NULL)) <> 1 THEN
    -- Mesmo formato de resposta, zero linhas: não revela o motivo.
    SELECT id, titular_tipo, usuario_id, empresa_id, sistema, agencia, numero
      FROM astro_dados.carteiras WHERE FALSE;
  ELSE
    SELECT id, titular_tipo, usuario_id, empresa_id, sistema, agencia, numero
      FROM astro_dados.carteiras
     WHERE (p_id IS NOT NULL AND id = p_id)
        OR (p_numero IS NOT NULL AND numero = p_numero AND agencia = p_agencia)
        OR (p_sistema IS NOT NULL AND sistema = p_sistema)
        OR (p_usuario IS NOT NULL AND usuario_id = p_usuario AND titular_tipo = 'PF')
     LIMIT 1;
  END IF;
END$$

-- =============================================================================
-- transferir: transferência entre carteiras feita INTEIRA dentro do banco.
-- É o caminho mais seguro (a API só manda "de, para, quanto"), e mostra como
-- movimentar saldo sem condição de corrida.
--
-- ISOLAMENTO: READ COMMITTED + SELECT ... FOR UPDATE.
--   - O problema clássico é o "gasto duplo": duas transferências leem saldo 100
--     ao mesmo tempo e as duas debitam 100. Quem evita isso é o LOCK DE LINHA
--     (FOR UPDATE): a segunda espera a primeira terminar e então lê o saldo já
--     debitado. Leitura com FOR UPDATE sempre vê o valor mais novo, em qualquer
--     nível de isolamento.
--   - READ COMMITTED (o mesmo nível padrão do PostgreSQL usado no original) não
--     cria "gap locks", então há menos deadlock que no REPEATABLE READ padrão
--     do MySQL. SERIALIZABLE transformaria todo SELECT em lock: mais lento e
--     mais deadlock, sem proteger nada a mais aqui.
--   - As duas carteiras são travadas SEMPRE em ordem crescente de id: duas
--     transferências opostas (A->B e B->A) não se travam mutuamente.
--   - Última barreira: o CHECK ck_carteira_saldo recusa saldo negativo.
--
-- Chame FORA de uma transação aberta (START TRANSACTION aqui dentro faria
-- COMMIT implícito do que estivesse aberto).
-- =============================================================================
CREATE PROCEDURE transferir(IN p_origem INT, IN p_destino INT, IN p_valor DECIMAL(14,2),
                            IN p_descricao TEXT, IN p_idempotency VARCHAR(200),
                            OUT p_transacao_id INT)
MODIFIES SQL DATA SQL SECURITY DEFINER
proc: BEGIN
  DECLARE c JSON DEFAULT astro_privado.ctx();
  DECLARE v_uid INT;
  DECLARE v_lock INT;
  DECLARE v_saldo_origem DECIMAL(14,2);
  DECLARE v_saldo_destino DECIMAL(14,2);
  DECLARE v_usuario_origem INT;
  DECLARE v_empresa_origem INT;
  DECLARE v_tipo_destino VARCHAR(10);
  DECLARE v_limite DECIMAL(14,2);
  DECLARE EXIT HANDLER FOR SQLEXCEPTION
  BEGIN
    ROLLBACK;
    RESIGNAL;
  END;

  -- 1) Quem está pedindo? Só pessoa autenticada, com escopo assinado.
  IF c IS NULL OR astro_privado.ctx_modo(c) <> 'usuario' THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Contexto ausente ou invalido';
  END IF;
  SET v_uid = astro_privado.ctx_uid(c);
  IF NOT astro_privado.ctx_no_escopo(c, p_origem) OR NOT astro_privado.ctx_no_escopo(c, p_destino) THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Carteiras fora do escopo assinado';
  END IF;

  -- 2) Validação de entrada (o CHECK também barra, mas aqui a mensagem é clara).
  IF p_valor IS NULL OR p_valor <= 0 OR p_valor >= 1000000000000 THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Valor invalido';
  END IF;
  IF p_origem IS NULL OR p_destino IS NULL OR p_origem = p_destino THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Carteiras invalidas';
  END IF;
  IF p_idempotency IS NULL OR CHAR_LENGTH(p_idempotency) < 16 THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Chave de idempotencia obrigatoria (16+ caracteres)';
  END IF;

  -- 3) Repetição do mesmo pedido devolve a transação já feita (sem débito duplo).
  SELECT id INTO p_transacao_id FROM astro_dados.transacoes WHERE idempotency_key = p_idempotency;
  IF p_transacao_id IS NOT NULL THEN
    LEAVE proc;
  END IF;

  SET TRANSACTION ISOLATION LEVEL READ COMMITTED;
  START TRANSACTION;

  -- 4) Trava as duas carteiras em ordem fixa de id.
  SELECT id INTO v_lock FROM astro_dados.carteiras WHERE id = LEAST(p_origem, p_destino) FOR UPDATE;
  SELECT id INTO v_lock FROM astro_dados.carteiras WHERE id = GREATEST(p_origem, p_destino) FOR UPDATE;

  SELECT saldo, usuario_id, empresa_id INTO v_saldo_origem, v_usuario_origem, v_empresa_origem
    FROM astro_dados.carteiras WHERE id = p_origem;
  SELECT saldo, titular_tipo INTO v_saldo_destino, v_tipo_destino
    FROM astro_dados.carteiras WHERE id = p_destino;
  IF v_saldo_origem IS NULL OR v_saldo_destino IS NULL THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Carteira inexistente';
  END IF;

  -- 5) Quem pede pode debitar a origem? PF: a dona. PJ: vínculo ativo que não
  --    seja só CONSULTA e com alçada suficiente (sem alçada = sem limite).
  IF NOT (COALESCE(v_usuario_origem = v_uid, FALSE) OR EXISTS (
          SELECT 1 FROM astro_dados.vinculos v
           WHERE v.empresa_id = v_empresa_origem AND v.usuario_id = v_uid
             AND v.ativo AND v.status = 'ativo' AND v.papel IN ('ADMIN','APROVADOR','OPERADOR')
             AND (v.alcada IS NULL OR v.alcada >= p_valor))) THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Sem permissao para debitar esta carteira';
  END IF;

  -- 6) Limite por transação da carteira de origem.
  SELECT por_transacao INTO v_limite FROM astro_dados.limites WHERE carteira_id = p_origem;
  IF v_limite IS NOT NULL AND p_valor > v_limite THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Acima do limite por transacao';
  END IF;

  IF v_saldo_origem < p_valor THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Saldo insuficiente';
  END IF;

  -- 7) Grava a transação, move o saldo e registra o ledger — tudo ou nada.
  INSERT INTO astro_dados.transacoes
         (origem_carteira_id, destino_carteira_id, tipo, valor_bruto, cbs, ibs, liquido,
          tipo_destino, aplicou_split, auth_metodo, status, autor_usuario_id, descricao, idempotency_key)
  VALUES (p_origem, p_destino, 'transferencia', p_valor, 0, 0, p_valor,
          v_tipo_destino, FALSE, 'SENHA', 'CONCLUIDA', v_uid, p_descricao, p_idempotency);
  SET p_transacao_id = LAST_INSERT_ID();

  UPDATE astro_dados.carteiras SET saldo = saldo - p_valor WHERE id = p_origem;
  UPDATE astro_dados.carteiras SET saldo = saldo + p_valor WHERE id = p_destino;

  INSERT INTO astro_dados.historico_saldo (carteira_id, saldo_anterior, saldo_novo, motivo, transacao_id)
  VALUES (p_origem,  v_saldo_origem,  v_saldo_origem  - p_valor, 'transferencia', p_transacao_id),
         (p_destino, v_saldo_destino, v_saldo_destino + p_valor, 'transferencia', p_transacao_id);
  COMMIT;
END$$

DELIMITER ;

-- =============================================================================
-- Relatórios SEM dado pessoal (papel astro_readonly) e conciliação
-- =============================================================================
USE astro_relatorios;

CREATE SQL SECURITY DEFINER VIEW resumo_transacoes_dia AS
  SELECT DATE(criado_em) AS dia, tipo, status,
         COUNT(*) AS quantidade, SUM(valor_bruto) AS valor_total,
         SUM(cbs) AS cbs_total, SUM(ibs) AS ibs_total
    FROM astro_dados.transacoes
   GROUP BY DATE(criado_em), tipo, status;

CREATE SQL SECURITY DEFINER VIEW resumo_carteiras AS
  SELECT titular_tipo, COUNT(*) AS quantidade,
         SUM(saldo) AS saldo_total, SUM(saldo_bloqueado) AS bloqueado_total
    FROM astro_dados.carteiras
   GROUP BY titular_tipo;

DELIMITER $$

-- Conciliação (equivale a backend/scripts/verificar_banco.py): só contagens,
-- nenhum CPF/e-mail. Tudo numa FOTO consistente do banco (REPEATABLE READ +
-- CONSISTENT SNAPSHOT, somente leitura): os números batem entre si mesmo com
-- transferências acontecendo durante a conferência.
CREATE PROCEDURE verificar_banco()
READS SQL DATA SQL SECURITY DEFINER
BEGIN
  SET TRANSACTION ISOLATION LEVEL REPEATABLE READ;
  START TRANSACTION WITH CONSISTENT SNAPSHOT, READ ONLY;
  SELECT
    (SELECT COUNT(*) FROM astro_dados.historico_saldo WHERE transacao_id IS NULL) AS historicos_sem_transacao,
    (SELECT COUNT(*) FROM astro_dados.carteiras
      WHERE saldo_bloqueado < 0 OR (saldo < 0 AND COALESCE(sistema, '') <> 'CAIXA')) AS carteiras_negativas,
    (SELECT COUNT(*) FROM (
        SELECT transacao_id FROM astro_dados.historico_saldo WHERE transacao_id IS NOT NULL
         GROUP BY transacao_id
        HAVING ROUND(SUM(saldo_novo - saldo_anterior + bloqueado_novo - bloqueado_anterior), 2) <> 0) m
    ) AS transacoes_desbalanceadas,
    (SELECT COUNT(*) FROM astro_dados.carteiras c
       LEFT JOIN (SELECT carteira_id, saldo_novo, bloqueado_novo,
                         ROW_NUMBER() OVER (PARTITION BY carteira_id ORDER BY id DESC) AS ordem
                    FROM astro_dados.historico_saldo) h
         ON h.carteira_id = c.id AND h.ordem = 1
      WHERE (h.carteira_id IS NULL AND (c.saldo <> 0 OR c.saldo_bloqueado <> 0))
         OR (h.carteira_id IS NOT NULL AND (c.saldo <> h.saldo_novo OR c.saldo_bloqueado <> h.bloqueado_novo))
    ) AS carteiras_divergentes_do_historico,
    (SELECT COALESCE(SUM(saldo + saldo_bloqueado), 0) FROM astro_dados.carteiras) AS total_financeiro;
  COMMIT;
END$$

DELIMITER ;
