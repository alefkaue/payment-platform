-- =============================================================================
-- 04_triggers_auditoria.sql  —  executar como svc_astro_migrator
-- =============================================================================
-- Três tipos de trigger, todos nas tabelas REAIS (astro_dados):
--
--  A. AUDITORIA (AFTER): toda inserção/alteração/exclusão em tabela financeira
--     ou de cadastro vira uma linha em astro_auditoria.trilha com quem, quando,
--     o quê, valor antigo e novo. Dado pessoal cifrado e segredos NÃO são
--     copiados para a trilha: ela só diz QUAIS deles mudaram (LGPD:
--     minimização). Cada linha guarda o hash da anterior (encadeamento): apagar
--     ou editar uma linha no meio quebra a corrente e verificar_cadeia() acusa.
--
--  B. INTEGRIDADE (BEFORE): trilhas append-only não aceitam UPDATE/DELETE
--     (nem do migrador), todo histórico de saldo precisa de transação,
--     transação concluída só muda status/bloqueio, carteira não troca de dono.
--
--  C. POLÍTICAS DE ESCRITA (BEFORE): a parte do RLS que é diferente da leitura
--     (cadastro, mexer em saldo, chave Pix). Ver 02_contexto_rls.sql.
--
-- SIGNAL SQLSTATE '45000' = "erro definido pelo usuário": aborta o comando.
-- =============================================================================

-- -----------------------------------------------------------------------------
-- A1. Tabelas da trilha
-- -----------------------------------------------------------------------------
USE astro_auditoria;

CREATE TABLE trilha (
  id             BIGINT       NOT NULL AUTO_INCREMENT,
  seq            BIGINT       NOT NULL,           -- posição na corrente
  ocorrido_em    DATETIME(6)  NOT NULL,           -- UTC
  usuario_bd     VARCHAR(288) NOT NULL,           -- conta que fez LOGIN (USER())
  conexao        BIGINT UNSIGNED NOT NULL,
  modo_app       VARCHAR(10)  NULL,               -- publico | usuario | sistema (do contexto assinado)
  usuario_app    INT          NULL,               -- pessoa do contexto assinado
  tabela         VARCHAR(64)  NOT NULL,
  operacao       ENUM('INSERT','UPDATE','DELETE') NOT NULL,
  registro_id    VARCHAR(64)  NOT NULL,
  antes          JSON         NULL,
  depois         JSON         NULL,
  hash_anterior  CHAR(64)     CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  hash           CHAR(64)     CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uq_trilha_seq (seq),
  KEY ix_trilha_tabela_registro (tabela, registro_id),
  KEY ix_trilha_ocorrido (ocorrido_em)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Ponta da corrente (uma linha). O FOR UPDATE nela enfileira os registros:
-- nunca dois eventos pegam o mesmo "hash anterior".
CREATE TABLE cadeia (
  id           TINYINT  NOT NULL,
  ultimo_hash  CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  total        BIGINT   NOT NULL,
  PRIMARY KEY (id),
  CONSTRAINT ck_cadeia_id CHECK (id = 1)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
INSERT INTO cadeia (id, ultimo_hash, total) VALUES (1, REPEAT('0', 64), 0);

DELIMITER $$

CREATE TRIGGER trg_trilha_imutavel_upd BEFORE UPDATE ON trilha FOR EACH ROW
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Trilha de auditoria imutavel'$$
CREATE TRIGGER trg_trilha_imutavel_del BEFORE DELETE ON trilha FOR EACH ROW
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Trilha de auditoria imutavel'$$
CREATE TRIGGER trg_cadeia_sem_delete BEFORE DELETE ON cadeia FOR EACH ROW
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Cadeia de auditoria imutavel'$$

-- O texto que entra no hash. Mesma função na gravação e na verificação.
CREATE FUNCTION texto_do_evento(p_anterior CHAR(64), p_seq BIGINT, p_quando DATETIME(6),
                                p_usuario_bd VARCHAR(288), p_modo VARCHAR(10), p_usuario_app INT,
                                p_tabela VARCHAR(64), p_operacao VARCHAR(6), p_registro VARCHAR(64),
                                p_antes JSON, p_depois JSON)
RETURNS LONGTEXT CHARSET utf8mb4
DETERMINISTIC NO SQL
RETURN CONCAT_WS('|', p_anterior, p_seq, DATE_FORMAT(p_quando, '%Y-%m-%d %H:%i:%s.%f'), p_usuario_bd,
                 COALESCE(p_modo, '-'), COALESCE(p_usuario_app, '-'), p_tabela, p_operacao, p_registro,
                 COALESCE(CAST(p_antes AS CHAR), '-'), COALESCE(CAST(p_depois AS CHAR), '-'))$$

-- Chamada pelos triggers de auditoria. Roda na MESMA transação da alteração:
-- se a alteração sofrer ROLLBACK, a linha da trilha some junto (não há registro
-- de algo que não aconteceu); se a trilha falhar, a alteração também falha.
CREATE PROCEDURE registrar(IN p_tabela VARCHAR(64), IN p_operacao VARCHAR(6), IN p_registro VARCHAR(64),
                           IN p_antes JSON, IN p_depois JSON)
MODIFIES SQL DATA SQL SECURITY DEFINER
BEGIN
  DECLARE c JSON DEFAULT astro_privado.ctx();
  DECLARE v_anterior CHAR(64);
  DECLARE v_seq BIGINT;
  DECLARE v_quando DATETIME(6) DEFAULT UTC_TIMESTAMP(6);
  DECLARE v_modo VARCHAR(10) DEFAULT astro_privado.ctx_modo(c);
  DECLARE v_uapp INT DEFAULT JSON_VALUE(c, '$.usuario_id' RETURNING SIGNED);
  DECLARE v_hash CHAR(64);

  SELECT ultimo_hash, total + 1 INTO v_anterior, v_seq FROM astro_auditoria.cadeia WHERE id = 1 FOR UPDATE;
  SET v_hash = SHA2(astro_auditoria.texto_do_evento(v_anterior, v_seq, v_quando, USER(), v_modo, v_uapp,
                                                    p_tabela, p_operacao, p_registro, p_antes, p_depois), 256);
  INSERT INTO astro_auditoria.trilha (seq, ocorrido_em, usuario_bd, conexao, modo_app, usuario_app,
                                      tabela, operacao, registro_id, antes, depois, hash_anterior, hash)
  VALUES (v_seq, v_quando, USER(), CONNECTION_ID(), v_modo, v_uapp,
          p_tabela, p_operacao, p_registro, p_antes, p_depois, v_anterior, v_hash);
  UPDATE astro_auditoria.cadeia SET ultimo_hash = v_hash, total = v_seq WHERE id = 1;
END$$

-- Recalcula a corrente inteira. Resultado esperado: integra = 1.
-- Se alguém (mesmo um admin) editar/apagar/inserir linha fora de ordem, aponta
-- a primeira posição quebrada.
CREATE PROCEDURE verificar_cadeia()
READS SQL DATA SQL SECURITY DEFINER
BEGIN
  DECLARE v_fim BOOLEAN DEFAULT FALSE;
  DECLARE v_esperado CHAR(64) DEFAULT REPEAT('0', 64);
  DECLARE v_seq_esperada BIGINT DEFAULT 1;
  DECLARE v_quebra BIGINT DEFAULT NULL;
  DECLARE v_total BIGINT DEFAULT 0;
  DECLARE r_seq BIGINT; DECLARE r_quando DATETIME(6); DECLARE r_usuario VARCHAR(288);
  DECLARE r_modo VARCHAR(10); DECLARE r_uapp INT; DECLARE r_tabela VARCHAR(64);
  DECLARE r_operacao VARCHAR(6); DECLARE r_registro VARCHAR(64); DECLARE r_antes JSON;
  DECLARE r_depois JSON; DECLARE r_anterior CHAR(64); DECLARE r_hash CHAR(64);
  DECLARE cur CURSOR FOR
    SELECT seq, ocorrido_em, usuario_bd, modo_app, usuario_app, tabela, operacao, registro_id,
           antes, depois, hash_anterior, hash
      FROM astro_auditoria.trilha ORDER BY seq;
  DECLARE CONTINUE HANDLER FOR NOT FOUND SET v_fim = TRUE;

  SET TRANSACTION ISOLATION LEVEL REPEATABLE READ;
  START TRANSACTION WITH CONSISTENT SNAPSHOT, READ ONLY;
  OPEN cur;
  laco: LOOP
    FETCH cur INTO r_seq, r_quando, r_usuario, r_modo, r_uapp, r_tabela, r_operacao, r_registro,
                   r_antes, r_depois, r_anterior, r_hash;
    IF v_fim THEN LEAVE laco; END IF;
    SET v_total = v_total + 1;
    IF r_seq <> v_seq_esperada OR r_anterior <> v_esperado
       OR r_hash <> SHA2(astro_auditoria.texto_do_evento(r_anterior, r_seq, r_quando, r_usuario, r_modo, r_uapp,
                                                         r_tabela, r_operacao, r_registro, r_antes, r_depois), 256) THEN
      SET v_quebra = r_seq;
      LEAVE laco;
    END IF;
    SET v_esperado = r_hash;
    SET v_seq_esperada = v_seq_esperada + 1;
  END LOOP;
  CLOSE cur;
  SELECT v_total AS eventos_conferidos,
         v_quebra AS primeira_quebra_seq,
         (v_quebra IS NULL AND v_esperado = (SELECT ultimo_hash FROM astro_auditoria.cadeia WHERE id = 1)) AS integra;
  COMMIT;
END$$

DELIMITER ;

-- -----------------------------------------------------------------------------
-- B + C. Integridade e políticas de escrita (BEFORE) nas tabelas reais
-- -----------------------------------------------------------------------------
USE astro_dados;
DELIMITER $$

-- Trilhas append-only: nenhum UPDATE/DELETE, nem do migrador. (No PostgreSQL só
-- historico_saldo e logs_auditoria tinham trigger; as outras 6 dependiam só de
-- GRANT. Aqui as 8 têm as duas barreiras.)
CREATE TRIGGER trg_historico_saldo_imutavel_upd BEFORE UPDATE ON historico_saldo FOR EACH ROW
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Trilha de auditoria imutavel'$$
CREATE TRIGGER trg_historico_saldo_imutavel_del BEFORE DELETE ON historico_saldo FOR EACH ROW
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Trilha de auditoria imutavel'$$
CREATE TRIGGER trg_logs_auditoria_imutavel_upd BEFORE UPDATE ON logs_auditoria FOR EACH ROW
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Trilha de auditoria imutavel'$$
CREATE TRIGGER trg_logs_auditoria_imutavel_del BEFORE DELETE ON logs_auditoria FOR EACH ROW
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Trilha de auditoria imutavel'$$
CREATE TRIGGER trg_pontos_movimentos_imutavel_upd BEFORE UPDATE ON pontos_movimentos FOR EACH ROW
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Registro append-only'$$
CREATE TRIGGER trg_pontos_movimentos_imutavel_del BEFORE DELETE ON pontos_movimentos FOR EACH ROW
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Registro append-only'$$
CREATE TRIGGER trg_creditos_tributarios_imutavel_upd BEFORE UPDATE ON creditos_tributarios FOR EACH ROW
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Registro append-only'$$
CREATE TRIGGER trg_creditos_tributarios_imutavel_del BEFORE DELETE ON creditos_tributarios FOR EACH ROW
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Registro append-only'$$
CREATE TRIGGER trg_rendimentos_imutavel_upd BEFORE UPDATE ON rendimentos FOR EACH ROW
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Registro append-only'$$
CREATE TRIGGER trg_rendimentos_imutavel_del BEFORE DELETE ON rendimentos FOR EACH ROW
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Registro append-only'$$
CREATE TRIGGER trg_sessoes_mfa_imutavel_upd BEFORE UPDATE ON sessoes_mfa FOR EACH ROW
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Registro append-only'$$
CREATE TRIGGER trg_sessoes_mfa_imutavel_del BEFORE DELETE ON sessoes_mfa FOR EACH ROW
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Registro append-only'$$
CREATE TRIGGER trg_documentos_identidade_imutavel_upd BEFORE UPDATE ON documentos_identidade FOR EACH ROW
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Registro append-only'$$
CREATE TRIGGER trg_documentos_identidade_imutavel_del BEFORE DELETE ON documentos_identidade FOR EACH ROW
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Registro append-only'$$
CREATE TRIGGER trg_documentos_empresa_imutavel_upd BEFORE UPDATE ON documentos_empresa FOR EACH ROW
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Registro append-only'$$
CREATE TRIGGER trg_documentos_empresa_imutavel_del BEFORE DELETE ON documentos_empresa FOR EACH ROW
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Registro append-only'$$

-- Ledger: todo histórico novo aponta para uma transação (igual ao original)
-- e só entra para carteira no escopo assinado da operação.
CREATE TRIGGER trg_historico_saldo_ins BEFORE INSERT ON historico_saldo FOR EACH ROW
BEGIN
  DECLARE c JSON;
  IF NEW.transacao_id IS NULL THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Novo historico requer transacao';
  END IF;
  IF NOT astro_privado.sessao_migrador() THEN
    SET c = astro_privado.ctx();
    IF NOT (astro_privado.ctx_comum(c) OR astro_privado.ctx_no_escopo(c, NEW.carteira_id)) THEN
      SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Politica: historico fora do escopo da operacao';
    END IF;
  END IF;
END$$

-- Tabelas append-only gravadas pela API sem dono específico: exigem contexto.
CREATE TRIGGER trg_creditos_tributarios_ins BEFORE INSERT ON creditos_tributarios FOR EACH ROW
BEGIN
  IF NOT astro_privado.sessao_migrador() AND astro_privado.ctx() IS NULL THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Politica: contexto obrigatorio';
  END IF;
END$$
CREATE TRIGGER trg_logs_auditoria_ins BEFORE INSERT ON logs_auditoria FOR EACH ROW
BEGIN
  IF NOT astro_privado.sessao_migrador() AND astro_privado.ctx() IS NULL THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Politica: contexto obrigatorio';
  END IF;
END$$
CREATE TRIGGER trg_rendimentos_ins BEFORE INSERT ON rendimentos FOR EACH ROW
BEGIN
  IF NOT astro_privado.sessao_migrador() AND astro_privado.ctx() IS NULL THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Politica: contexto obrigatorio';
  END IF;
END$$

-- usuarios: cadastro público só cria USUARIO comum (nunca ADMIN); alterar só a
-- própria linha (ou modo sistema/admin).
CREATE TRIGGER trg_usuarios_ins BEFORE INSERT ON usuarios FOR EACH ROW
BEGIN
  DECLARE c JSON;
  IF NOT astro_privado.sessao_migrador() THEN
    SET c = astro_privado.ctx();
    IF NOT (astro_privado.ctx_comum(c) OR (astro_privado.ctx_modo(c) = 'publico' AND NEW.papel = 'USUARIO')) THEN
      SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Politica: cadastro de usuario negado';
    END IF;
  END IF;
END$$
CREATE TRIGGER trg_usuarios_upd BEFORE UPDATE ON usuarios FOR EACH ROW
BEGIN
  DECLARE c JSON;
  IF NOT astro_privado.sessao_migrador() THEN
    SET c = astro_privado.ctx();
    IF NOT (astro_privado.ctx_comum(c)
            OR (astro_privado.ctx_modo(c) = 'usuario' AND OLD.id = astro_privado.ctx_uid(c) AND NEW.id = OLD.id)) THEN
      SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Politica: alteracao de usuario negada';
    END IF;
    IF NOT (NEW.papel <=> OLD.papel) AND NOT astro_privado.ctx_comum(c) THEN
      SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Politica: troca de papel negada';
    END IF;
  END IF;
END$$
CREATE TRIGGER trg_usuarios_del BEFORE DELETE ON usuarios FOR EACH ROW
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Usuario nao e apagado: desative (ativo = FALSE)'$$

-- vinculos: cria quem é ADMIN da empresa, ou o representante na abertura da
-- conta (empresa criada nesta transação); altera o ADMIN ou a pessoa convidada
-- (aceitar/recusar o próprio convite, conferido pelo CPF).
CREATE TRIGGER trg_vinculos_ins BEFORE INSERT ON vinculos FOR EACH ROW
BEGIN
  DECLARE c JSON;
  IF NOT astro_privado.sessao_migrador() THEN
    SET c = astro_privado.ctx();
    IF NOT (astro_privado.ctx_comum(c)
            OR astro_privado.ctx_vinculo_admin(c, NEW.empresa_id)
            OR (astro_privado.ctx_modo(c) = 'usuario' AND NEW.usuario_id = astro_privado.ctx_uid(c)
                AND astro_privado.ctx_criado_agora(c, 'empresas', NEW.empresa_id)
                AND EXISTS (SELECT 1 FROM astro_dados.empresas e
                             WHERE e.id = NEW.empresa_id AND e.representante_usuario_id = astro_privado.ctx_uid(c)))) THEN
      SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Politica: criacao de vinculo negada';
    END IF;
  END IF;
END$$
CREATE TRIGGER trg_vinculos_upd BEFORE UPDATE ON vinculos FOR EACH ROW
BEGIN
  DECLARE c JSON;
  DECLARE v_cpf_indice CHAR(64);
  IF NOT astro_privado.sessao_migrador() THEN
    SET c = astro_privado.ctx();
    IF NOT (astro_privado.ctx_comum(c)
            OR (astro_privado.ctx_vinculo_admin(c, OLD.empresa_id) AND NEW.empresa_id = OLD.empresa_id)) THEN
      SELECT cpf_indice INTO v_cpf_indice FROM astro_dados.usuarios WHERE id = astro_privado.ctx_uid(c);
      IF NOT (astro_privado.ctx_modo(c) = 'usuario'
              AND v_cpf_indice IS NOT NULL
              AND OLD.cpf_indice = v_cpf_indice AND NEW.cpf_indice = v_cpf_indice
              AND NEW.empresa_id = OLD.empresa_id
              AND (OLD.usuario_id IS NULL OR OLD.usuario_id = astro_privado.ctx_uid(c))
              AND (NEW.usuario_id IS NULL OR NEW.usuario_id = astro_privado.ctx_uid(c))
              AND NEW.papel = OLD.papel AND NEW.alcada <=> OLD.alcada AND NEW.alcada_diaria <=> OLD.alcada_diaria) THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Politica: alteracao de vinculo negada';
      END IF;
    END IF;
  END IF;
END$$

-- carteiras: criar só no cadastro (ou sistema/admin), e sempre com saldo zero;
-- mexer em saldo só com a carteira no escopo assinado; dono/número nunca mudam.
CREATE TRIGGER trg_carteiras_ins BEFORE INSERT ON carteiras FOR EACH ROW
BEGIN
  DECLARE c JSON;
  IF NOT astro_privado.sessao_migrador() THEN
    SET c = astro_privado.ctx();
    IF NOT (astro_privado.ctx_comum(c)
            OR astro_privado.pode_criar_carteira(c, NEW.titular_tipo, NEW.usuario_id, NEW.empresa_id)) THEN
      SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Politica: criacao de carteira negada';
    END IF;
    IF (NEW.saldo <> 0 OR NEW.saldo_bloqueado <> 0) AND NOT astro_privado.ctx_comum(c) THEN
      SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Politica: carteira nova nasce com saldo zero';
    END IF;
  END IF;
END$$
CREATE TRIGGER trg_carteiras_upd BEFORE UPDATE ON carteiras FOR EACH ROW
BEGIN
  DECLARE c JSON;
  IF NOT astro_privado.sessao_migrador() THEN
    IF NOT (NEW.id <=> OLD.id AND NEW.titular_tipo <=> OLD.titular_tipo AND NEW.usuario_id <=> OLD.usuario_id
            AND NEW.empresa_id <=> OLD.empresa_id AND NEW.sistema <=> OLD.sistema
            AND NEW.agencia <=> OLD.agencia AND NEW.numero <=> OLD.numero AND NEW.criado_em <=> OLD.criado_em) THEN
      SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Integridade: so saldo e saldo_bloqueado podem mudar';
    END IF;
    SET c = astro_privado.ctx();
    IF NOT (astro_privado.ctx_comum(c) OR astro_privado.ctx_no_escopo(c, OLD.id)) THEN
      SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Politica: carteira fora do escopo da operacao';
    END IF;
  END IF;
END$$
CREATE TRIGGER trg_carteiras_del BEFORE DELETE ON carteiras FOR EACH ROW
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Carteira nao e apagada'$$

-- transacoes: depois de gravada, só status e bloqueio_ate mudam (devolução,
-- bloqueio cautelar). Valor, contas e autor ficam congelados.
CREATE TRIGGER trg_transacoes_upd BEFORE UPDATE ON transacoes FOR EACH ROW
BEGIN
  IF NOT astro_privado.sessao_migrador() THEN
    IF NOT (NEW.id <=> OLD.id AND NEW.origem_carteira_id <=> OLD.origem_carteira_id
            AND NEW.destino_carteira_id <=> OLD.destino_carteira_id AND NEW.tipo <=> OLD.tipo
            AND NEW.valor_bruto <=> OLD.valor_bruto AND NEW.cbs <=> OLD.cbs AND NEW.ibs <=> OLD.ibs
            AND NEW.liquido <=> OLD.liquido AND NEW.tipo_destino <=> OLD.tipo_destino
            AND NEW.aplicou_split <=> OLD.aplicou_split AND NEW.auth_metodo <=> OLD.auth_metodo
            AND NEW.autor_usuario_id <=> OLD.autor_usuario_id AND NEW.dispositivo_id <=> OLD.dispositivo_id
            AND NEW.descricao <=> OLD.descricao AND NEW.verificacao_facial <=> OLD.verificacao_facial
            AND NEW.idempotency_key <=> OLD.idempotency_key
            AND NEW.transacao_original_id <=> OLD.transacao_original_id AND NEW.criado_em <=> OLD.criado_em) THEN
      SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Integridade: transacao so muda status e bloqueio_ate';
    END IF;
  END IF;
END$$
CREATE TRIGGER trg_transacoes_del BEFORE DELETE ON transacoes FOR EACH ROW
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Transacao nao e apagada: use devolucao/estorno'$$

-- chaves_pix: ler é livre (com contexto) para achar o destinatário; criar,
-- trocar ou apagar só o dono da carteira (ou a carteira criada no cadastro).
CREATE TRIGGER trg_chaves_pix_ins BEFORE INSERT ON chaves_pix FOR EACH ROW
BEGIN
  DECLARE c JSON;
  IF NOT astro_privado.sessao_migrador() THEN
    SET c = astro_privado.ctx();
    IF NOT (astro_privado.ctx_comum(c) OR astro_privado.ctx_carteira_propria(c, NEW.carteira_id)
            OR (astro_privado.ctx_modo(c) = 'publico' AND astro_privado.ctx_criado_agora(c, 'carteiras', NEW.carteira_id))) THEN
      SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Politica: chave Pix so pelo dono da carteira';
    END IF;
  END IF;
END$$
CREATE TRIGGER trg_chaves_pix_upd BEFORE UPDATE ON chaves_pix FOR EACH ROW
BEGIN
  DECLARE c JSON;
  IF NOT astro_privado.sessao_migrador() THEN
    SET c = astro_privado.ctx();
    IF NOT (astro_privado.ctx_comum(c)
            OR (astro_privado.ctx_carteira_propria(c, OLD.carteira_id) AND NEW.carteira_id = OLD.carteira_id)) THEN
      SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Politica: chave Pix so pelo dono da carteira';
    END IF;
  END IF;
END$$
CREATE TRIGGER trg_chaves_pix_del BEFORE DELETE ON chaves_pix FOR EACH ROW
BEGIN
  DECLARE c JSON;
  IF NOT astro_privado.sessao_migrador() THEN
    SET c = astro_privado.ctx();
    IF NOT (astro_privado.ctx_comum(c) OR astro_privado.ctx_carteira_propria(c, OLD.carteira_id)) THEN
      SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Politica: chave Pix so pelo dono da carteira';
    END IF;
  END IF;
END$$

DELIMITER ;

-- -----------------------------------------------------------------------------
-- A2. Triggers de auditoria (AFTER) — gerados por ferramentas/gerar_auditoria.py
-- Para cada tabela: _ins grava "depois", _upd grava "antes" e "depois" (só se
-- algo relevante mudou), _del grava "antes". Colunas cifradas/segredos entram
-- apenas como nome em "sensiveis_alterados".
-- Em usuarios, empresas e carteiras o AFTER INSERT também anota o registro em
-- astro_privado.cadastro_sessao (usado pelas políticas de cadastro).
-- -----------------------------------------------------------------------------
USE astro_dados;
DELIMITER $$

CREATE TRIGGER trg_aud_usuarios_ins AFTER INSERT ON usuarios FOR EACH ROW
BEGIN
  DECLARE c JSON;
  SET c = astro_privado.ctx();
  IF c IS NOT NULL THEN
    DELETE FROM astro_privado.cadastro_sessao
     WHERE conexao = CONNECTION_ID() AND criado_em < UTC_TIMESTAMP(6) - INTERVAL 2 MINUTE;
    INSERT INTO astro_privado.cadastro_sessao (conexao, tx, tabela, registro_id, criado_em)
    VALUES (CONNECTION_ID(), JSON_VALUE(c, '$.tx'), 'usuarios', NEW.id, UTC_TIMESTAMP(6));
  END IF;
  CALL astro_auditoria.registrar('usuarios', 'INSERT', NEW.id, NULL, JSON_OBJECT('id', NEW.`id`, 'papel', NEW.`papel`, 'kyc_status', NEW.`kyc_status`, 'ativo', NEW.`ativo`, 'pontos', NEW.`pontos`, 'totp_passo_usado', NEW.`totp_passo_usado`, 'criado_em', NEW.`criado_em`));
END$$

CREATE TRIGGER trg_aud_usuarios_upd AFTER UPDATE ON usuarios FOR EACH ROW
BEGIN
  IF NOT (OLD.`id` <=> NEW.`id` AND OLD.`papel` <=> NEW.`papel` AND OLD.`kyc_status` <=> NEW.`kyc_status` AND OLD.`ativo` <=> NEW.`ativo` AND OLD.`pontos` <=> NEW.`pontos` AND OLD.`totp_passo_usado` <=> NEW.`totp_passo_usado` AND OLD.`criado_em` <=> NEW.`criado_em` AND OLD.`nome` <=> NEW.`nome` AND OLD.`cpf` <=> NEW.`cpf` AND OLD.`email` <=> NEW.`email` AND OLD.`celular` <=> NEW.`celular` AND OLD.`data_nascimento` <=> NEW.`data_nascimento` AND OLD.`senha_hash` <=> NEW.`senha_hash` AND OLD.`embedding_facial_cifrado` <=> NEW.`embedding_facial_cifrado` AND OLD.`totp_segredo` <=> NEW.`totp_segredo`) THEN
    CALL astro_auditoria.registrar('usuarios', 'UPDATE', NEW.id, JSON_OBJECT('id', OLD.`id`, 'papel', OLD.`papel`, 'kyc_status', OLD.`kyc_status`, 'ativo', OLD.`ativo`, 'pontos', OLD.`pontos`, 'totp_passo_usado', OLD.`totp_passo_usado`, 'criado_em', OLD.`criado_em`), JSON_SET(JSON_OBJECT('id', NEW.`id`, 'papel', NEW.`papel`, 'kyc_status', NEW.`kyc_status`, 'ativo', NEW.`ativo`, 'pontos', NEW.`pontos`, 'totp_passo_usado', NEW.`totp_passo_usado`, 'criado_em', NEW.`criado_em`), '$.sensiveis_alterados', CONCAT_WS(',', IF(OLD.`nome` <=> NEW.`nome`, NULL, 'nome'), IF(OLD.`cpf` <=> NEW.`cpf`, NULL, 'cpf'), IF(OLD.`email` <=> NEW.`email`, NULL, 'email'), IF(OLD.`celular` <=> NEW.`celular`, NULL, 'celular'), IF(OLD.`data_nascimento` <=> NEW.`data_nascimento`, NULL, 'data_nascimento'), IF(OLD.`senha_hash` <=> NEW.`senha_hash`, NULL, 'senha_hash'), IF(OLD.`embedding_facial_cifrado` <=> NEW.`embedding_facial_cifrado`, NULL, 'embedding_facial_cifrado'), IF(OLD.`totp_segredo` <=> NEW.`totp_segredo`, NULL, 'totp_segredo'))));
  END IF;
END$$

CREATE TRIGGER trg_aud_usuarios_del AFTER DELETE ON usuarios FOR EACH ROW
  CALL astro_auditoria.registrar('usuarios', 'DELETE', OLD.id, JSON_OBJECT('id', OLD.`id`, 'papel', OLD.`papel`, 'kyc_status', OLD.`kyc_status`, 'ativo', OLD.`ativo`, 'pontos', OLD.`pontos`, 'totp_passo_usado', OLD.`totp_passo_usado`, 'criado_em', OLD.`criado_em`), NULL)$$

CREATE TRIGGER trg_aud_empresas_ins AFTER INSERT ON empresas FOR EACH ROW
BEGIN
  DECLARE c JSON;
  SET c = astro_privado.ctx();
  IF c IS NOT NULL THEN
    DELETE FROM astro_privado.cadastro_sessao
     WHERE conexao = CONNECTION_ID() AND criado_em < UTC_TIMESTAMP(6) - INTERVAL 2 MINUTE;
    INSERT INTO astro_privado.cadastro_sessao (conexao, tx, tabela, registro_id, criado_em)
    VALUES (CONNECTION_ID(), JSON_VALUE(c, '$.tx'), 'empresas', NEW.id, UTC_TIMESTAMP(6));
  END IF;
  CALL astro_auditoria.registrar('empresas', 'INSERT', NEW.id, NULL, JSON_OBJECT('id', NEW.`id`, 'porte', NEW.`porte`, 'regime_apuracao', NEW.`regime_apuracao`, 'cnae', NEW.`cnae`, 'setor', NEW.`setor`, 'situacao_cadastral', NEW.`situacao_cadastral`, 'verificada_em', NEW.`verificada_em`, 'verificada_por', NEW.`verificada_por`, 'representante_usuario_id', NEW.`representante_usuario_id`, 'kyb_status', NEW.`kyb_status`, 'criado_em', NEW.`criado_em`));
END$$

CREATE TRIGGER trg_aud_empresas_upd AFTER UPDATE ON empresas FOR EACH ROW
BEGIN
  IF NOT (OLD.`id` <=> NEW.`id` AND OLD.`porte` <=> NEW.`porte` AND OLD.`regime_apuracao` <=> NEW.`regime_apuracao` AND OLD.`cnae` <=> NEW.`cnae` AND OLD.`setor` <=> NEW.`setor` AND OLD.`situacao_cadastral` <=> NEW.`situacao_cadastral` AND OLD.`verificada_em` <=> NEW.`verificada_em` AND OLD.`verificada_por` <=> NEW.`verificada_por` AND OLD.`representante_usuario_id` <=> NEW.`representante_usuario_id` AND OLD.`kyb_status` <=> NEW.`kyb_status` AND OLD.`criado_em` <=> NEW.`criado_em` AND OLD.`cnpj` <=> NEW.`cnpj` AND OLD.`razao_social` <=> NEW.`razao_social` AND OLD.`nome_fantasia` <=> NEW.`nome_fantasia`) THEN
    CALL astro_auditoria.registrar('empresas', 'UPDATE', NEW.id, JSON_OBJECT('id', OLD.`id`, 'porte', OLD.`porte`, 'regime_apuracao', OLD.`regime_apuracao`, 'cnae', OLD.`cnae`, 'setor', OLD.`setor`, 'situacao_cadastral', OLD.`situacao_cadastral`, 'verificada_em', OLD.`verificada_em`, 'verificada_por', OLD.`verificada_por`, 'representante_usuario_id', OLD.`representante_usuario_id`, 'kyb_status', OLD.`kyb_status`, 'criado_em', OLD.`criado_em`), JSON_SET(JSON_OBJECT('id', NEW.`id`, 'porte', NEW.`porte`, 'regime_apuracao', NEW.`regime_apuracao`, 'cnae', NEW.`cnae`, 'setor', NEW.`setor`, 'situacao_cadastral', NEW.`situacao_cadastral`, 'verificada_em', NEW.`verificada_em`, 'verificada_por', NEW.`verificada_por`, 'representante_usuario_id', NEW.`representante_usuario_id`, 'kyb_status', NEW.`kyb_status`, 'criado_em', NEW.`criado_em`), '$.sensiveis_alterados', CONCAT_WS(',', IF(OLD.`cnpj` <=> NEW.`cnpj`, NULL, 'cnpj'), IF(OLD.`razao_social` <=> NEW.`razao_social`, NULL, 'razao_social'), IF(OLD.`nome_fantasia` <=> NEW.`nome_fantasia`, NULL, 'nome_fantasia'))));
  END IF;
END$$

CREATE TRIGGER trg_aud_empresas_del AFTER DELETE ON empresas FOR EACH ROW
  CALL astro_auditoria.registrar('empresas', 'DELETE', OLD.id, JSON_OBJECT('id', OLD.`id`, 'porte', OLD.`porte`, 'regime_apuracao', OLD.`regime_apuracao`, 'cnae', OLD.`cnae`, 'setor', OLD.`setor`, 'situacao_cadastral', OLD.`situacao_cadastral`, 'verificada_em', OLD.`verificada_em`, 'verificada_por', OLD.`verificada_por`, 'representante_usuario_id', OLD.`representante_usuario_id`, 'kyb_status', OLD.`kyb_status`, 'criado_em', OLD.`criado_em`), NULL)$$

CREATE TRIGGER trg_aud_vinculos_ins AFTER INSERT ON vinculos FOR EACH ROW
BEGIN
  CALL astro_auditoria.registrar('vinculos', 'INSERT', NEW.id, NULL, JSON_OBJECT('id', NEW.`id`, 'usuario_id', NEW.`usuario_id`, 'empresa_id', NEW.`empresa_id`, 'cargo', NEW.`cargo`, 'papel', NEW.`papel`, 'alcada', NEW.`alcada`, 'alcada_diaria', NEW.`alcada_diaria`, 'status', NEW.`status`, 'ativo', NEW.`ativo`, 'criado_por_usuario_id', NEW.`criado_por_usuario_id`, 'aceito_em', NEW.`aceito_em`, 'status_em', NEW.`status_em`, 'criado_em', NEW.`criado_em`));
END$$

CREATE TRIGGER trg_aud_vinculos_upd AFTER UPDATE ON vinculos FOR EACH ROW
BEGIN
  IF NOT (OLD.`id` <=> NEW.`id` AND OLD.`usuario_id` <=> NEW.`usuario_id` AND OLD.`empresa_id` <=> NEW.`empresa_id` AND OLD.`cargo` <=> NEW.`cargo` AND OLD.`papel` <=> NEW.`papel` AND OLD.`alcada` <=> NEW.`alcada` AND OLD.`alcada_diaria` <=> NEW.`alcada_diaria` AND OLD.`status` <=> NEW.`status` AND OLD.`ativo` <=> NEW.`ativo` AND OLD.`criado_por_usuario_id` <=> NEW.`criado_por_usuario_id` AND OLD.`aceito_em` <=> NEW.`aceito_em` AND OLD.`status_em` <=> NEW.`status_em` AND OLD.`criado_em` <=> NEW.`criado_em` AND OLD.`cpf` <=> NEW.`cpf` AND OLD.`nome` <=> NEW.`nome` AND OLD.`email` <=> NEW.`email` AND OLD.`celular` <=> NEW.`celular`) THEN
    CALL astro_auditoria.registrar('vinculos', 'UPDATE', NEW.id, JSON_OBJECT('id', OLD.`id`, 'usuario_id', OLD.`usuario_id`, 'empresa_id', OLD.`empresa_id`, 'cargo', OLD.`cargo`, 'papel', OLD.`papel`, 'alcada', OLD.`alcada`, 'alcada_diaria', OLD.`alcada_diaria`, 'status', OLD.`status`, 'ativo', OLD.`ativo`, 'criado_por_usuario_id', OLD.`criado_por_usuario_id`, 'aceito_em', OLD.`aceito_em`, 'status_em', OLD.`status_em`, 'criado_em', OLD.`criado_em`), JSON_SET(JSON_OBJECT('id', NEW.`id`, 'usuario_id', NEW.`usuario_id`, 'empresa_id', NEW.`empresa_id`, 'cargo', NEW.`cargo`, 'papel', NEW.`papel`, 'alcada', NEW.`alcada`, 'alcada_diaria', NEW.`alcada_diaria`, 'status', NEW.`status`, 'ativo', NEW.`ativo`, 'criado_por_usuario_id', NEW.`criado_por_usuario_id`, 'aceito_em', NEW.`aceito_em`, 'status_em', NEW.`status_em`, 'criado_em', NEW.`criado_em`), '$.sensiveis_alterados', CONCAT_WS(',', IF(OLD.`cpf` <=> NEW.`cpf`, NULL, 'cpf'), IF(OLD.`nome` <=> NEW.`nome`, NULL, 'nome'), IF(OLD.`email` <=> NEW.`email`, NULL, 'email'), IF(OLD.`celular` <=> NEW.`celular`, NULL, 'celular'))));
  END IF;
END$$

CREATE TRIGGER trg_aud_vinculos_del AFTER DELETE ON vinculos FOR EACH ROW
  CALL astro_auditoria.registrar('vinculos', 'DELETE', OLD.id, JSON_OBJECT('id', OLD.`id`, 'usuario_id', OLD.`usuario_id`, 'empresa_id', OLD.`empresa_id`, 'cargo', OLD.`cargo`, 'papel', OLD.`papel`, 'alcada', OLD.`alcada`, 'alcada_diaria', OLD.`alcada_diaria`, 'status', OLD.`status`, 'ativo', OLD.`ativo`, 'criado_por_usuario_id', OLD.`criado_por_usuario_id`, 'aceito_em', OLD.`aceito_em`, 'status_em', OLD.`status_em`, 'criado_em', OLD.`criado_em`), NULL)$$

CREATE TRIGGER trg_aud_carteiras_ins AFTER INSERT ON carteiras FOR EACH ROW
BEGIN
  DECLARE c JSON;
  SET c = astro_privado.ctx();
  IF c IS NOT NULL THEN
    DELETE FROM astro_privado.cadastro_sessao
     WHERE conexao = CONNECTION_ID() AND criado_em < UTC_TIMESTAMP(6) - INTERVAL 2 MINUTE;
    INSERT INTO astro_privado.cadastro_sessao (conexao, tx, tabela, registro_id, criado_em)
    VALUES (CONNECTION_ID(), JSON_VALUE(c, '$.tx'), 'carteiras', NEW.id, UTC_TIMESTAMP(6));
  END IF;
  CALL astro_auditoria.registrar('carteiras', 'INSERT', NEW.id, NULL, JSON_OBJECT('id', NEW.`id`, 'titular_tipo', NEW.`titular_tipo`, 'usuario_id', NEW.`usuario_id`, 'empresa_id', NEW.`empresa_id`, 'sistema', NEW.`sistema`, 'agencia', NEW.`agencia`, 'numero', NEW.`numero`, 'saldo', NEW.`saldo`, 'saldo_bloqueado', NEW.`saldo_bloqueado`, 'criado_em', NEW.`criado_em`));
END$$

CREATE TRIGGER trg_aud_carteiras_upd AFTER UPDATE ON carteiras FOR EACH ROW
BEGIN
  IF NOT (OLD.`id` <=> NEW.`id` AND OLD.`titular_tipo` <=> NEW.`titular_tipo` AND OLD.`usuario_id` <=> NEW.`usuario_id` AND OLD.`empresa_id` <=> NEW.`empresa_id` AND OLD.`sistema` <=> NEW.`sistema` AND OLD.`agencia` <=> NEW.`agencia` AND OLD.`numero` <=> NEW.`numero` AND OLD.`saldo` <=> NEW.`saldo` AND OLD.`saldo_bloqueado` <=> NEW.`saldo_bloqueado` AND OLD.`criado_em` <=> NEW.`criado_em`) THEN
    CALL astro_auditoria.registrar('carteiras', 'UPDATE', NEW.id, JSON_OBJECT('id', OLD.`id`, 'titular_tipo', OLD.`titular_tipo`, 'usuario_id', OLD.`usuario_id`, 'empresa_id', OLD.`empresa_id`, 'sistema', OLD.`sistema`, 'agencia', OLD.`agencia`, 'numero', OLD.`numero`, 'saldo', OLD.`saldo`, 'saldo_bloqueado', OLD.`saldo_bloqueado`, 'criado_em', OLD.`criado_em`), JSON_OBJECT('id', NEW.`id`, 'titular_tipo', NEW.`titular_tipo`, 'usuario_id', NEW.`usuario_id`, 'empresa_id', NEW.`empresa_id`, 'sistema', NEW.`sistema`, 'agencia', NEW.`agencia`, 'numero', NEW.`numero`, 'saldo', NEW.`saldo`, 'saldo_bloqueado', NEW.`saldo_bloqueado`, 'criado_em', NEW.`criado_em`));
  END IF;
END$$

CREATE TRIGGER trg_aud_carteiras_del AFTER DELETE ON carteiras FOR EACH ROW
  CALL astro_auditoria.registrar('carteiras', 'DELETE', OLD.id, JSON_OBJECT('id', OLD.`id`, 'titular_tipo', OLD.`titular_tipo`, 'usuario_id', OLD.`usuario_id`, 'empresa_id', OLD.`empresa_id`, 'sistema', OLD.`sistema`, 'agencia', OLD.`agencia`, 'numero', OLD.`numero`, 'saldo', OLD.`saldo`, 'saldo_bloqueado', OLD.`saldo_bloqueado`, 'criado_em', OLD.`criado_em`), NULL)$$

CREATE TRIGGER trg_aud_transacoes_ins AFTER INSERT ON transacoes FOR EACH ROW
BEGIN
  CALL astro_auditoria.registrar('transacoes', 'INSERT', NEW.id, NULL, JSON_OBJECT('id', NEW.`id`, 'origem_carteira_id', NEW.`origem_carteira_id`, 'destino_carteira_id', NEW.`destino_carteira_id`, 'tipo', NEW.`tipo`, 'valor_bruto', NEW.`valor_bruto`, 'cbs', NEW.`cbs`, 'ibs', NEW.`ibs`, 'liquido', NEW.`liquido`, 'tipo_destino', NEW.`tipo_destino`, 'aplicou_split', NEW.`aplicou_split`, 'auth_metodo', NEW.`auth_metodo`, 'status', NEW.`status`, 'bloqueio_ate', NEW.`bloqueio_ate`, 'autor_usuario_id', NEW.`autor_usuario_id`, 'dispositivo_id', NEW.`dispositivo_id`, 'idempotency_key', NEW.`idempotency_key`, 'transacao_original_id', NEW.`transacao_original_id`, 'criado_em', NEW.`criado_em`));
END$$

CREATE TRIGGER trg_aud_transacoes_upd AFTER UPDATE ON transacoes FOR EACH ROW
BEGIN
  IF NOT (OLD.`id` <=> NEW.`id` AND OLD.`origem_carteira_id` <=> NEW.`origem_carteira_id` AND OLD.`destino_carteira_id` <=> NEW.`destino_carteira_id` AND OLD.`tipo` <=> NEW.`tipo` AND OLD.`valor_bruto` <=> NEW.`valor_bruto` AND OLD.`cbs` <=> NEW.`cbs` AND OLD.`ibs` <=> NEW.`ibs` AND OLD.`liquido` <=> NEW.`liquido` AND OLD.`tipo_destino` <=> NEW.`tipo_destino` AND OLD.`aplicou_split` <=> NEW.`aplicou_split` AND OLD.`auth_metodo` <=> NEW.`auth_metodo` AND OLD.`status` <=> NEW.`status` AND OLD.`bloqueio_ate` <=> NEW.`bloqueio_ate` AND OLD.`autor_usuario_id` <=> NEW.`autor_usuario_id` AND OLD.`dispositivo_id` <=> NEW.`dispositivo_id` AND OLD.`idempotency_key` <=> NEW.`idempotency_key` AND OLD.`transacao_original_id` <=> NEW.`transacao_original_id` AND OLD.`criado_em` <=> NEW.`criado_em` AND OLD.`descricao` <=> NEW.`descricao` AND OLD.`verificacao_facial` <=> NEW.`verificacao_facial`) THEN
    CALL astro_auditoria.registrar('transacoes', 'UPDATE', NEW.id, JSON_OBJECT('id', OLD.`id`, 'origem_carteira_id', OLD.`origem_carteira_id`, 'destino_carteira_id', OLD.`destino_carteira_id`, 'tipo', OLD.`tipo`, 'valor_bruto', OLD.`valor_bruto`, 'cbs', OLD.`cbs`, 'ibs', OLD.`ibs`, 'liquido', OLD.`liquido`, 'tipo_destino', OLD.`tipo_destino`, 'aplicou_split', OLD.`aplicou_split`, 'auth_metodo', OLD.`auth_metodo`, 'status', OLD.`status`, 'bloqueio_ate', OLD.`bloqueio_ate`, 'autor_usuario_id', OLD.`autor_usuario_id`, 'dispositivo_id', OLD.`dispositivo_id`, 'idempotency_key', OLD.`idempotency_key`, 'transacao_original_id', OLD.`transacao_original_id`, 'criado_em', OLD.`criado_em`), JSON_SET(JSON_OBJECT('id', NEW.`id`, 'origem_carteira_id', NEW.`origem_carteira_id`, 'destino_carteira_id', NEW.`destino_carteira_id`, 'tipo', NEW.`tipo`, 'valor_bruto', NEW.`valor_bruto`, 'cbs', NEW.`cbs`, 'ibs', NEW.`ibs`, 'liquido', NEW.`liquido`, 'tipo_destino', NEW.`tipo_destino`, 'aplicou_split', NEW.`aplicou_split`, 'auth_metodo', NEW.`auth_metodo`, 'status', NEW.`status`, 'bloqueio_ate', NEW.`bloqueio_ate`, 'autor_usuario_id', NEW.`autor_usuario_id`, 'dispositivo_id', NEW.`dispositivo_id`, 'idempotency_key', NEW.`idempotency_key`, 'transacao_original_id', NEW.`transacao_original_id`, 'criado_em', NEW.`criado_em`), '$.sensiveis_alterados', CONCAT_WS(',', IF(OLD.`descricao` <=> NEW.`descricao`, NULL, 'descricao'), IF(OLD.`verificacao_facial` <=> NEW.`verificacao_facial`, NULL, 'verificacao_facial'))));
  END IF;
END$$

CREATE TRIGGER trg_aud_transacoes_del AFTER DELETE ON transacoes FOR EACH ROW
  CALL astro_auditoria.registrar('transacoes', 'DELETE', OLD.id, JSON_OBJECT('id', OLD.`id`, 'origem_carteira_id', OLD.`origem_carteira_id`, 'destino_carteira_id', OLD.`destino_carteira_id`, 'tipo', OLD.`tipo`, 'valor_bruto', OLD.`valor_bruto`, 'cbs', OLD.`cbs`, 'ibs', OLD.`ibs`, 'liquido', OLD.`liquido`, 'tipo_destino', OLD.`tipo_destino`, 'aplicou_split', OLD.`aplicou_split`, 'auth_metodo', OLD.`auth_metodo`, 'status', OLD.`status`, 'bloqueio_ate', OLD.`bloqueio_ate`, 'autor_usuario_id', OLD.`autor_usuario_id`, 'dispositivo_id', OLD.`dispositivo_id`, 'idempotency_key', OLD.`idempotency_key`, 'transacao_original_id', OLD.`transacao_original_id`, 'criado_em', OLD.`criado_em`), NULL)$$

CREATE TRIGGER trg_aud_split_liquidacoes_ins AFTER INSERT ON split_liquidacoes FOR EACH ROW
BEGIN
  CALL astro_auditoria.registrar('split_liquidacoes', 'INSERT', NEW.id, NULL, JSON_OBJECT('id', NEW.`id`, 'transacao_id', NEW.`transacao_id`, 'natureza', NEW.`natureza`, 'carteira_destino_id', NEW.`carteira_destino_id`, 'valor', NEW.`valor`, 'repasse_id', NEW.`repasse_id`, 'estornada', NEW.`estornada`, 'criado_em', NEW.`criado_em`));
END$$

CREATE TRIGGER trg_aud_split_liquidacoes_upd AFTER UPDATE ON split_liquidacoes FOR EACH ROW
BEGIN
  IF NOT (OLD.`id` <=> NEW.`id` AND OLD.`transacao_id` <=> NEW.`transacao_id` AND OLD.`natureza` <=> NEW.`natureza` AND OLD.`carteira_destino_id` <=> NEW.`carteira_destino_id` AND OLD.`valor` <=> NEW.`valor` AND OLD.`repasse_id` <=> NEW.`repasse_id` AND OLD.`estornada` <=> NEW.`estornada` AND OLD.`criado_em` <=> NEW.`criado_em`) THEN
    CALL astro_auditoria.registrar('split_liquidacoes', 'UPDATE', NEW.id, JSON_OBJECT('id', OLD.`id`, 'transacao_id', OLD.`transacao_id`, 'natureza', OLD.`natureza`, 'carteira_destino_id', OLD.`carteira_destino_id`, 'valor', OLD.`valor`, 'repasse_id', OLD.`repasse_id`, 'estornada', OLD.`estornada`, 'criado_em', OLD.`criado_em`), JSON_OBJECT('id', NEW.`id`, 'transacao_id', NEW.`transacao_id`, 'natureza', NEW.`natureza`, 'carteira_destino_id', NEW.`carteira_destino_id`, 'valor', NEW.`valor`, 'repasse_id', NEW.`repasse_id`, 'estornada', NEW.`estornada`, 'criado_em', NEW.`criado_em`));
  END IF;
END$$

CREATE TRIGGER trg_aud_split_liquidacoes_del AFTER DELETE ON split_liquidacoes FOR EACH ROW
  CALL astro_auditoria.registrar('split_liquidacoes', 'DELETE', OLD.id, JSON_OBJECT('id', OLD.`id`, 'transacao_id', OLD.`transacao_id`, 'natureza', OLD.`natureza`, 'carteira_destino_id', OLD.`carteira_destino_id`, 'valor', OLD.`valor`, 'repasse_id', OLD.`repasse_id`, 'estornada', OLD.`estornada`, 'criado_em', OLD.`criado_em`), NULL)$$

CREATE TRIGGER trg_aud_repasses_tributo_ins AFTER INSERT ON repasses_tributo FOR EACH ROW
BEGIN
  CALL astro_auditoria.registrar('repasses_tributo', 'INSERT', NEW.id, NULL, JSON_OBJECT('id', NEW.`id`, 'cbs_total', NEW.`cbs_total`, 'ibs_total', NEW.`ibs_total`, 'corte', NEW.`corte`, 'criado_em', NEW.`criado_em`));
END$$

CREATE TRIGGER trg_aud_repasses_tributo_upd AFTER UPDATE ON repasses_tributo FOR EACH ROW
BEGIN
  IF NOT (OLD.`id` <=> NEW.`id` AND OLD.`cbs_total` <=> NEW.`cbs_total` AND OLD.`ibs_total` <=> NEW.`ibs_total` AND OLD.`corte` <=> NEW.`corte` AND OLD.`criado_em` <=> NEW.`criado_em`) THEN
    CALL astro_auditoria.registrar('repasses_tributo', 'UPDATE', NEW.id, JSON_OBJECT('id', OLD.`id`, 'cbs_total', OLD.`cbs_total`, 'ibs_total', OLD.`ibs_total`, 'corte', OLD.`corte`, 'criado_em', OLD.`criado_em`), JSON_OBJECT('id', NEW.`id`, 'cbs_total', NEW.`cbs_total`, 'ibs_total', NEW.`ibs_total`, 'corte', NEW.`corte`, 'criado_em', NEW.`criado_em`));
  END IF;
END$$

CREATE TRIGGER trg_aud_repasses_tributo_del AFTER DELETE ON repasses_tributo FOR EACH ROW
  CALL astro_auditoria.registrar('repasses_tributo', 'DELETE', OLD.id, JSON_OBJECT('id', OLD.`id`, 'cbs_total', OLD.`cbs_total`, 'ibs_total', OLD.`ibs_total`, 'corte', OLD.`corte`, 'criado_em', OLD.`criado_em`), NULL)$$

CREATE TRIGGER trg_aud_creditos_tributarios_ins AFTER INSERT ON creditos_tributarios FOR EACH ROW
BEGIN
  CALL astro_auditoria.registrar('creditos_tributarios', 'INSERT', NEW.id, NULL, JSON_OBJECT('id', NEW.`id`, 'empresa_id', NEW.`empresa_id`, 'tributo', NEW.`tributo`, 'valor', NEW.`valor`, 'fonte', NEW.`fonte`, 'referencia', NEW.`referencia`, 'consultado_em', NEW.`consultado_em`));
END$$

CREATE TRIGGER trg_aud_creditos_tributarios_upd AFTER UPDATE ON creditos_tributarios FOR EACH ROW
BEGIN
  IF NOT (OLD.`id` <=> NEW.`id` AND OLD.`empresa_id` <=> NEW.`empresa_id` AND OLD.`tributo` <=> NEW.`tributo` AND OLD.`valor` <=> NEW.`valor` AND OLD.`fonte` <=> NEW.`fonte` AND OLD.`referencia` <=> NEW.`referencia` AND OLD.`consultado_em` <=> NEW.`consultado_em`) THEN
    CALL astro_auditoria.registrar('creditos_tributarios', 'UPDATE', NEW.id, JSON_OBJECT('id', OLD.`id`, 'empresa_id', OLD.`empresa_id`, 'tributo', OLD.`tributo`, 'valor', OLD.`valor`, 'fonte', OLD.`fonte`, 'referencia', OLD.`referencia`, 'consultado_em', OLD.`consultado_em`), JSON_OBJECT('id', NEW.`id`, 'empresa_id', NEW.`empresa_id`, 'tributo', NEW.`tributo`, 'valor', NEW.`valor`, 'fonte', NEW.`fonte`, 'referencia', NEW.`referencia`, 'consultado_em', NEW.`consultado_em`));
  END IF;
END$$

CREATE TRIGGER trg_aud_creditos_tributarios_del AFTER DELETE ON creditos_tributarios FOR EACH ROW
  CALL astro_auditoria.registrar('creditos_tributarios', 'DELETE', OLD.id, JSON_OBJECT('id', OLD.`id`, 'empresa_id', OLD.`empresa_id`, 'tributo', OLD.`tributo`, 'valor', OLD.`valor`, 'fonte', OLD.`fonte`, 'referencia', OLD.`referencia`, 'consultado_em', OLD.`consultado_em`), NULL)$$

CREATE TRIGGER trg_aud_cobrancas_ins AFTER INSERT ON cobrancas FOR EACH ROW
BEGIN
  CALL astro_auditoria.registrar('cobrancas', 'INSERT', NEW.id, NULL, JSON_OBJECT('id', NEW.`id`, 'txid', NEW.`txid`, 'recebedor_carteira_id', NEW.`recebedor_carteira_id`, 'valor', NEW.`valor`, 'vencimento', NEW.`vencimento`, 'nfe_chave', NEW.`nfe_chave`, 'cbs', NEW.`cbs`, 'ibs', NEW.`ibs`, 'linha_digitavel', NEW.`linha_digitavel`, 'status', NEW.`status`, 'grupo_parcelamento', NEW.`grupo_parcelamento`, 'parcela_numero', NEW.`parcela_numero`, 'parcelas_total', NEW.`parcelas_total`, 'autorizacao_id', NEW.`autorizacao_id`, 'transacao_id', NEW.`transacao_id`, 'paga_em', NEW.`paga_em`, 'criado_por_usuario_id', NEW.`criado_por_usuario_id`, 'criado_em', NEW.`criado_em`));
END$$

CREATE TRIGGER trg_aud_cobrancas_upd AFTER UPDATE ON cobrancas FOR EACH ROW
BEGIN
  IF NOT (OLD.`id` <=> NEW.`id` AND OLD.`txid` <=> NEW.`txid` AND OLD.`recebedor_carteira_id` <=> NEW.`recebedor_carteira_id` AND OLD.`valor` <=> NEW.`valor` AND OLD.`vencimento` <=> NEW.`vencimento` AND OLD.`nfe_chave` <=> NEW.`nfe_chave` AND OLD.`cbs` <=> NEW.`cbs` AND OLD.`ibs` <=> NEW.`ibs` AND OLD.`linha_digitavel` <=> NEW.`linha_digitavel` AND OLD.`status` <=> NEW.`status` AND OLD.`grupo_parcelamento` <=> NEW.`grupo_parcelamento` AND OLD.`parcela_numero` <=> NEW.`parcela_numero` AND OLD.`parcelas_total` <=> NEW.`parcelas_total` AND OLD.`autorizacao_id` <=> NEW.`autorizacao_id` AND OLD.`transacao_id` <=> NEW.`transacao_id` AND OLD.`paga_em` <=> NEW.`paga_em` AND OLD.`criado_por_usuario_id` <=> NEW.`criado_por_usuario_id` AND OLD.`criado_em` <=> NEW.`criado_em` AND OLD.`descricao` <=> NEW.`descricao` AND OLD.`pagador_documento` <=> NEW.`pagador_documento`) THEN
    CALL astro_auditoria.registrar('cobrancas', 'UPDATE', NEW.id, JSON_OBJECT('id', OLD.`id`, 'txid', OLD.`txid`, 'recebedor_carteira_id', OLD.`recebedor_carteira_id`, 'valor', OLD.`valor`, 'vencimento', OLD.`vencimento`, 'nfe_chave', OLD.`nfe_chave`, 'cbs', OLD.`cbs`, 'ibs', OLD.`ibs`, 'linha_digitavel', OLD.`linha_digitavel`, 'status', OLD.`status`, 'grupo_parcelamento', OLD.`grupo_parcelamento`, 'parcela_numero', OLD.`parcela_numero`, 'parcelas_total', OLD.`parcelas_total`, 'autorizacao_id', OLD.`autorizacao_id`, 'transacao_id', OLD.`transacao_id`, 'paga_em', OLD.`paga_em`, 'criado_por_usuario_id', OLD.`criado_por_usuario_id`, 'criado_em', OLD.`criado_em`), JSON_SET(JSON_OBJECT('id', NEW.`id`, 'txid', NEW.`txid`, 'recebedor_carteira_id', NEW.`recebedor_carteira_id`, 'valor', NEW.`valor`, 'vencimento', NEW.`vencimento`, 'nfe_chave', NEW.`nfe_chave`, 'cbs', NEW.`cbs`, 'ibs', NEW.`ibs`, 'linha_digitavel', NEW.`linha_digitavel`, 'status', NEW.`status`, 'grupo_parcelamento', NEW.`grupo_parcelamento`, 'parcela_numero', NEW.`parcela_numero`, 'parcelas_total', NEW.`parcelas_total`, 'autorizacao_id', NEW.`autorizacao_id`, 'transacao_id', NEW.`transacao_id`, 'paga_em', NEW.`paga_em`, 'criado_por_usuario_id', NEW.`criado_por_usuario_id`, 'criado_em', NEW.`criado_em`), '$.sensiveis_alterados', CONCAT_WS(',', IF(OLD.`descricao` <=> NEW.`descricao`, NULL, 'descricao'), IF(OLD.`pagador_documento` <=> NEW.`pagador_documento`, NULL, 'pagador_documento'))));
  END IF;
END$$

CREATE TRIGGER trg_aud_cobrancas_del AFTER DELETE ON cobrancas FOR EACH ROW
  CALL astro_auditoria.registrar('cobrancas', 'DELETE', OLD.id, JSON_OBJECT('id', OLD.`id`, 'txid', OLD.`txid`, 'recebedor_carteira_id', OLD.`recebedor_carteira_id`, 'valor', OLD.`valor`, 'vencimento', OLD.`vencimento`, 'nfe_chave', OLD.`nfe_chave`, 'cbs', OLD.`cbs`, 'ibs', OLD.`ibs`, 'linha_digitavel', OLD.`linha_digitavel`, 'status', OLD.`status`, 'grupo_parcelamento', OLD.`grupo_parcelamento`, 'parcela_numero', OLD.`parcela_numero`, 'parcelas_total', OLD.`parcelas_total`, 'autorizacao_id', OLD.`autorizacao_id`, 'transacao_id', OLD.`transacao_id`, 'paga_em', OLD.`paga_em`, 'criado_por_usuario_id', OLD.`criado_por_usuario_id`, 'criado_em', OLD.`criado_em`), NULL)$$

CREATE TRIGGER trg_aud_autorizacoes_recorrentes_ins AFTER INSERT ON autorizacoes_recorrentes FOR EACH ROW
BEGIN
  CALL astro_auditoria.registrar('autorizacoes_recorrentes', 'INSERT', NEW.id, NULL, JSON_OBJECT('id', NEW.`id`, 'recebedor_carteira_id', NEW.`recebedor_carteira_id`, 'pagador_carteira_id', NEW.`pagador_carteira_id`, 'valor_maximo', NEW.`valor_maximo`, 'periodicidade', NEW.`periodicidade`, 'status', NEW.`status`, 'aceita_em', NEW.`aceita_em`, 'cancelada_em', NEW.`cancelada_em`, 'criado_em', NEW.`criado_em`));
END$$

CREATE TRIGGER trg_aud_autorizacoes_recorrentes_upd AFTER UPDATE ON autorizacoes_recorrentes FOR EACH ROW
BEGIN
  IF NOT (OLD.`id` <=> NEW.`id` AND OLD.`recebedor_carteira_id` <=> NEW.`recebedor_carteira_id` AND OLD.`pagador_carteira_id` <=> NEW.`pagador_carteira_id` AND OLD.`valor_maximo` <=> NEW.`valor_maximo` AND OLD.`periodicidade` <=> NEW.`periodicidade` AND OLD.`status` <=> NEW.`status` AND OLD.`aceita_em` <=> NEW.`aceita_em` AND OLD.`cancelada_em` <=> NEW.`cancelada_em` AND OLD.`criado_em` <=> NEW.`criado_em` AND OLD.`descricao` <=> NEW.`descricao`) THEN
    CALL astro_auditoria.registrar('autorizacoes_recorrentes', 'UPDATE', NEW.id, JSON_OBJECT('id', OLD.`id`, 'recebedor_carteira_id', OLD.`recebedor_carteira_id`, 'pagador_carteira_id', OLD.`pagador_carteira_id`, 'valor_maximo', OLD.`valor_maximo`, 'periodicidade', OLD.`periodicidade`, 'status', OLD.`status`, 'aceita_em', OLD.`aceita_em`, 'cancelada_em', OLD.`cancelada_em`, 'criado_em', OLD.`criado_em`), JSON_SET(JSON_OBJECT('id', NEW.`id`, 'recebedor_carteira_id', NEW.`recebedor_carteira_id`, 'pagador_carteira_id', NEW.`pagador_carteira_id`, 'valor_maximo', NEW.`valor_maximo`, 'periodicidade', NEW.`periodicidade`, 'status', NEW.`status`, 'aceita_em', NEW.`aceita_em`, 'cancelada_em', NEW.`cancelada_em`, 'criado_em', NEW.`criado_em`), '$.sensiveis_alterados', CONCAT_WS(',', IF(OLD.`descricao` <=> NEW.`descricao`, NULL, 'descricao'))));
  END IF;
END$$

CREATE TRIGGER trg_aud_autorizacoes_recorrentes_del AFTER DELETE ON autorizacoes_recorrentes FOR EACH ROW
  CALL astro_auditoria.registrar('autorizacoes_recorrentes', 'DELETE', OLD.id, JSON_OBJECT('id', OLD.`id`, 'recebedor_carteira_id', OLD.`recebedor_carteira_id`, 'pagador_carteira_id', OLD.`pagador_carteira_id`, 'valor_maximo', OLD.`valor_maximo`, 'periodicidade', OLD.`periodicidade`, 'status', OLD.`status`, 'aceita_em', OLD.`aceita_em`, 'cancelada_em', OLD.`cancelada_em`, 'criado_em', OLD.`criado_em`), NULL)$$

CREATE TRIGGER trg_aud_chaves_pix_ins AFTER INSERT ON chaves_pix FOR EACH ROW
BEGIN
  CALL astro_auditoria.registrar('chaves_pix', 'INSERT', NEW.id, NULL, JSON_OBJECT('id', NEW.`id`, 'carteira_id', NEW.`carteira_id`, 'tipo', NEW.`tipo`, 'valor_indice', NEW.`valor_indice`, 'criado_em', NEW.`criado_em`));
END$$

CREATE TRIGGER trg_aud_chaves_pix_upd AFTER UPDATE ON chaves_pix FOR EACH ROW
BEGIN
  IF NOT (OLD.`id` <=> NEW.`id` AND OLD.`carteira_id` <=> NEW.`carteira_id` AND OLD.`tipo` <=> NEW.`tipo` AND OLD.`valor_indice` <=> NEW.`valor_indice` AND OLD.`criado_em` <=> NEW.`criado_em` AND OLD.`valor` <=> NEW.`valor`) THEN
    CALL astro_auditoria.registrar('chaves_pix', 'UPDATE', NEW.id, JSON_OBJECT('id', OLD.`id`, 'carteira_id', OLD.`carteira_id`, 'tipo', OLD.`tipo`, 'valor_indice', OLD.`valor_indice`, 'criado_em', OLD.`criado_em`), JSON_SET(JSON_OBJECT('id', NEW.`id`, 'carteira_id', NEW.`carteira_id`, 'tipo', NEW.`tipo`, 'valor_indice', NEW.`valor_indice`, 'criado_em', NEW.`criado_em`), '$.sensiveis_alterados', CONCAT_WS(',', IF(OLD.`valor` <=> NEW.`valor`, NULL, 'valor'))));
  END IF;
END$$

CREATE TRIGGER trg_aud_chaves_pix_del AFTER DELETE ON chaves_pix FOR EACH ROW
  CALL astro_auditoria.registrar('chaves_pix', 'DELETE', OLD.id, JSON_OBJECT('id', OLD.`id`, 'carteira_id', OLD.`carteira_id`, 'tipo', OLD.`tipo`, 'valor_indice', OLD.`valor_indice`, 'criado_em', OLD.`criado_em`), NULL)$$

CREATE TRIGGER trg_aud_operacoes_pendentes_ins AFTER INSERT ON operacoes_pendentes FOR EACH ROW
BEGIN
  CALL astro_auditoria.registrar('operacoes_pendentes', 'INSERT', NEW.id, NULL, JSON_OBJECT('id', NEW.`id`, 'empresa_id', NEW.`empresa_id`, 'tipo', NEW.`tipo`, 'valor', NEW.`valor`, 'aprovacoes_necessarias', NEW.`aprovacoes_necessarias`, 'criado_por_usuario_id', NEW.`criado_por_usuario_id`, 'status', NEW.`status`, 'decidido_por_usuario_id', NEW.`decidido_por_usuario_id`, 'decidido_em', NEW.`decidido_em`, 'criado_em', NEW.`criado_em`, 'idempotency_key', NEW.`idempotency_key`));
END$$

CREATE TRIGGER trg_aud_operacoes_pendentes_upd AFTER UPDATE ON operacoes_pendentes FOR EACH ROW
BEGIN
  IF NOT (OLD.`id` <=> NEW.`id` AND OLD.`empresa_id` <=> NEW.`empresa_id` AND OLD.`tipo` <=> NEW.`tipo` AND OLD.`valor` <=> NEW.`valor` AND OLD.`aprovacoes_necessarias` <=> NEW.`aprovacoes_necessarias` AND OLD.`criado_por_usuario_id` <=> NEW.`criado_por_usuario_id` AND OLD.`status` <=> NEW.`status` AND OLD.`decidido_por_usuario_id` <=> NEW.`decidido_por_usuario_id` AND OLD.`decidido_em` <=> NEW.`decidido_em` AND OLD.`criado_em` <=> NEW.`criado_em` AND OLD.`idempotency_key` <=> NEW.`idempotency_key` AND OLD.`payload` <=> NEW.`payload` AND OLD.`descricao` <=> NEW.`descricao` AND OLD.`aprovacoes` <=> NEW.`aprovacoes` AND OLD.`resultado` <=> NEW.`resultado`) THEN
    CALL astro_auditoria.registrar('operacoes_pendentes', 'UPDATE', NEW.id, JSON_OBJECT('id', OLD.`id`, 'empresa_id', OLD.`empresa_id`, 'tipo', OLD.`tipo`, 'valor', OLD.`valor`, 'aprovacoes_necessarias', OLD.`aprovacoes_necessarias`, 'criado_por_usuario_id', OLD.`criado_por_usuario_id`, 'status', OLD.`status`, 'decidido_por_usuario_id', OLD.`decidido_por_usuario_id`, 'decidido_em', OLD.`decidido_em`, 'criado_em', OLD.`criado_em`, 'idempotency_key', OLD.`idempotency_key`), JSON_SET(JSON_OBJECT('id', NEW.`id`, 'empresa_id', NEW.`empresa_id`, 'tipo', NEW.`tipo`, 'valor', NEW.`valor`, 'aprovacoes_necessarias', NEW.`aprovacoes_necessarias`, 'criado_por_usuario_id', NEW.`criado_por_usuario_id`, 'status', NEW.`status`, 'decidido_por_usuario_id', NEW.`decidido_por_usuario_id`, 'decidido_em', NEW.`decidido_em`, 'criado_em', NEW.`criado_em`, 'idempotency_key', NEW.`idempotency_key`), '$.sensiveis_alterados', CONCAT_WS(',', IF(OLD.`payload` <=> NEW.`payload`, NULL, 'payload'), IF(OLD.`descricao` <=> NEW.`descricao`, NULL, 'descricao'), IF(OLD.`aprovacoes` <=> NEW.`aprovacoes`, NULL, 'aprovacoes'), IF(OLD.`resultado` <=> NEW.`resultado`, NULL, 'resultado'))));
  END IF;
END$$

CREATE TRIGGER trg_aud_operacoes_pendentes_del AFTER DELETE ON operacoes_pendentes FOR EACH ROW
  CALL astro_auditoria.registrar('operacoes_pendentes', 'DELETE', OLD.id, JSON_OBJECT('id', OLD.`id`, 'empresa_id', OLD.`empresa_id`, 'tipo', OLD.`tipo`, 'valor', OLD.`valor`, 'aprovacoes_necessarias', OLD.`aprovacoes_necessarias`, 'criado_por_usuario_id', OLD.`criado_por_usuario_id`, 'status', OLD.`status`, 'decidido_por_usuario_id', OLD.`decidido_por_usuario_id`, 'decidido_em', OLD.`decidido_em`, 'criado_em', OLD.`criado_em`, 'idempotency_key', OLD.`idempotency_key`), NULL)$$

CREATE TRIGGER trg_aud_contestacoes_ins AFTER INSERT ON contestacoes FOR EACH ROW
BEGIN
  CALL astro_auditoria.registrar('contestacoes', 'INSERT', NEW.id, NULL, JSON_OBJECT('id', NEW.`id`, 'transacao_id', NEW.`transacao_id`, 'aberta_por_usuario_id', NEW.`aberta_por_usuario_id`, 'status', NEW.`status`, 'valor_devolvido', NEW.`valor_devolvido`, 'decidida_em', NEW.`decidida_em`, 'criado_em', NEW.`criado_em`));
END$$

CREATE TRIGGER trg_aud_contestacoes_upd AFTER UPDATE ON contestacoes FOR EACH ROW
BEGIN
  IF NOT (OLD.`id` <=> NEW.`id` AND OLD.`transacao_id` <=> NEW.`transacao_id` AND OLD.`aberta_por_usuario_id` <=> NEW.`aberta_por_usuario_id` AND OLD.`status` <=> NEW.`status` AND OLD.`valor_devolvido` <=> NEW.`valor_devolvido` AND OLD.`decidida_em` <=> NEW.`decidida_em` AND OLD.`criado_em` <=> NEW.`criado_em` AND OLD.`motivo` <=> NEW.`motivo`) THEN
    CALL astro_auditoria.registrar('contestacoes', 'UPDATE', NEW.id, JSON_OBJECT('id', OLD.`id`, 'transacao_id', OLD.`transacao_id`, 'aberta_por_usuario_id', OLD.`aberta_por_usuario_id`, 'status', OLD.`status`, 'valor_devolvido', OLD.`valor_devolvido`, 'decidida_em', OLD.`decidida_em`, 'criado_em', OLD.`criado_em`), JSON_SET(JSON_OBJECT('id', NEW.`id`, 'transacao_id', NEW.`transacao_id`, 'aberta_por_usuario_id', NEW.`aberta_por_usuario_id`, 'status', NEW.`status`, 'valor_devolvido', NEW.`valor_devolvido`, 'decidida_em', NEW.`decidida_em`, 'criado_em', NEW.`criado_em`), '$.sensiveis_alterados', CONCAT_WS(',', IF(OLD.`motivo` <=> NEW.`motivo`, NULL, 'motivo'))));
  END IF;
END$$

CREATE TRIGGER trg_aud_contestacoes_del AFTER DELETE ON contestacoes FOR EACH ROW
  CALL astro_auditoria.registrar('contestacoes', 'DELETE', OLD.id, JSON_OBJECT('id', OLD.`id`, 'transacao_id', OLD.`transacao_id`, 'aberta_por_usuario_id', OLD.`aberta_por_usuario_id`, 'status', OLD.`status`, 'valor_devolvido', OLD.`valor_devolvido`, 'decidida_em', OLD.`decidida_em`, 'criado_em', OLD.`criado_em`), NULL)$$

CREATE TRIGGER trg_aud_limites_ins AFTER INSERT ON limites FOR EACH ROW
BEGIN
  CALL astro_auditoria.registrar('limites', 'INSERT', NEW.id, NULL, JSON_OBJECT('id', NEW.`id`, 'carteira_id', NEW.`carteira_id`, 'por_transacao', NEW.`por_transacao`, 'diurno', NEW.`diurno`, 'noturno', NEW.`noturno`, 'pendente_por_transacao', NEW.`pendente_por_transacao`, 'pendente_diurno', NEW.`pendente_diurno`, 'pendente_noturno', NEW.`pendente_noturno`, 'pendente_vigente_em', NEW.`pendente_vigente_em`));
END$$

CREATE TRIGGER trg_aud_limites_upd AFTER UPDATE ON limites FOR EACH ROW
BEGIN
  IF NOT (OLD.`id` <=> NEW.`id` AND OLD.`carteira_id` <=> NEW.`carteira_id` AND OLD.`por_transacao` <=> NEW.`por_transacao` AND OLD.`diurno` <=> NEW.`diurno` AND OLD.`noturno` <=> NEW.`noturno` AND OLD.`pendente_por_transacao` <=> NEW.`pendente_por_transacao` AND OLD.`pendente_diurno` <=> NEW.`pendente_diurno` AND OLD.`pendente_noturno` <=> NEW.`pendente_noturno` AND OLD.`pendente_vigente_em` <=> NEW.`pendente_vigente_em`) THEN
    CALL astro_auditoria.registrar('limites', 'UPDATE', NEW.id, JSON_OBJECT('id', OLD.`id`, 'carteira_id', OLD.`carteira_id`, 'por_transacao', OLD.`por_transacao`, 'diurno', OLD.`diurno`, 'noturno', OLD.`noturno`, 'pendente_por_transacao', OLD.`pendente_por_transacao`, 'pendente_diurno', OLD.`pendente_diurno`, 'pendente_noturno', OLD.`pendente_noturno`, 'pendente_vigente_em', OLD.`pendente_vigente_em`), JSON_OBJECT('id', NEW.`id`, 'carteira_id', NEW.`carteira_id`, 'por_transacao', NEW.`por_transacao`, 'diurno', NEW.`diurno`, 'noturno', NEW.`noturno`, 'pendente_por_transacao', NEW.`pendente_por_transacao`, 'pendente_diurno', NEW.`pendente_diurno`, 'pendente_noturno', NEW.`pendente_noturno`, 'pendente_vigente_em', NEW.`pendente_vigente_em`));
  END IF;
END$$

CREATE TRIGGER trg_aud_limites_del AFTER DELETE ON limites FOR EACH ROW
  CALL astro_auditoria.registrar('limites', 'DELETE', OLD.id, JSON_OBJECT('id', OLD.`id`, 'carteira_id', OLD.`carteira_id`, 'por_transacao', OLD.`por_transacao`, 'diurno', OLD.`diurno`, 'noturno', OLD.`noturno`, 'pendente_por_transacao', OLD.`pendente_por_transacao`, 'pendente_diurno', OLD.`pendente_diurno`, 'pendente_noturno', OLD.`pendente_noturno`, 'pendente_vigente_em', OLD.`pendente_vigente_em`), NULL)$$

CREATE TRIGGER trg_aud_funcionarios_ins AFTER INSERT ON funcionarios FOR EACH ROW
BEGIN
  CALL astro_auditoria.registrar('funcionarios', 'INSERT', NEW.id, NULL, JSON_OBJECT('id', NEW.`id`, 'empresa_id', NEW.`empresa_id`, 'cargo', NEW.`cargo`, 'salario', NEW.`salario`, 'ativo', NEW.`ativo`, 'criado_por_usuario_id', NEW.`criado_por_usuario_id`, 'criado_em', NEW.`criado_em`, 'desligado_em', NEW.`desligado_em`));
END$$

CREATE TRIGGER trg_aud_funcionarios_upd AFTER UPDATE ON funcionarios FOR EACH ROW
BEGIN
  IF NOT (OLD.`id` <=> NEW.`id` AND OLD.`empresa_id` <=> NEW.`empresa_id` AND OLD.`cargo` <=> NEW.`cargo` AND OLD.`salario` <=> NEW.`salario` AND OLD.`ativo` <=> NEW.`ativo` AND OLD.`criado_por_usuario_id` <=> NEW.`criado_por_usuario_id` AND OLD.`criado_em` <=> NEW.`criado_em` AND OLD.`desligado_em` <=> NEW.`desligado_em` AND OLD.`nome` <=> NEW.`nome` AND OLD.`cpf` <=> NEW.`cpf`) THEN
    CALL astro_auditoria.registrar('funcionarios', 'UPDATE', NEW.id, JSON_OBJECT('id', OLD.`id`, 'empresa_id', OLD.`empresa_id`, 'cargo', OLD.`cargo`, 'salario', OLD.`salario`, 'ativo', OLD.`ativo`, 'criado_por_usuario_id', OLD.`criado_por_usuario_id`, 'criado_em', OLD.`criado_em`, 'desligado_em', OLD.`desligado_em`), JSON_SET(JSON_OBJECT('id', NEW.`id`, 'empresa_id', NEW.`empresa_id`, 'cargo', NEW.`cargo`, 'salario', NEW.`salario`, 'ativo', NEW.`ativo`, 'criado_por_usuario_id', NEW.`criado_por_usuario_id`, 'criado_em', NEW.`criado_em`, 'desligado_em', NEW.`desligado_em`), '$.sensiveis_alterados', CONCAT_WS(',', IF(OLD.`nome` <=> NEW.`nome`, NULL, 'nome'), IF(OLD.`cpf` <=> NEW.`cpf`, NULL, 'cpf'))));
  END IF;
END$$

CREATE TRIGGER trg_aud_funcionarios_del AFTER DELETE ON funcionarios FOR EACH ROW
  CALL astro_auditoria.registrar('funcionarios', 'DELETE', OLD.id, JSON_OBJECT('id', OLD.`id`, 'empresa_id', OLD.`empresa_id`, 'cargo', OLD.`cargo`, 'salario', OLD.`salario`, 'ativo', OLD.`ativo`, 'criado_por_usuario_id', OLD.`criado_por_usuario_id`, 'criado_em', OLD.`criado_em`, 'desligado_em', OLD.`desligado_em`), NULL)$$

CREATE TRIGGER trg_aud_webhooks_ins AFTER INSERT ON webhooks FOR EACH ROW
BEGIN
  CALL astro_auditoria.registrar('webhooks', 'INSERT', NEW.id, NULL, JSON_OBJECT('id', NEW.`id`, 'empresa_id', NEW.`empresa_id`, 'url', NEW.`url`, 'eventos', NEW.`eventos`, 'ativo', NEW.`ativo`, 'criado_em', NEW.`criado_em`));
END$$

CREATE TRIGGER trg_aud_webhooks_upd AFTER UPDATE ON webhooks FOR EACH ROW
BEGIN
  IF NOT (OLD.`id` <=> NEW.`id` AND OLD.`empresa_id` <=> NEW.`empresa_id` AND OLD.`url` <=> NEW.`url` AND OLD.`eventos` <=> NEW.`eventos` AND OLD.`ativo` <=> NEW.`ativo` AND OLD.`criado_em` <=> NEW.`criado_em` AND OLD.`segredo` <=> NEW.`segredo`) THEN
    CALL astro_auditoria.registrar('webhooks', 'UPDATE', NEW.id, JSON_OBJECT('id', OLD.`id`, 'empresa_id', OLD.`empresa_id`, 'url', OLD.`url`, 'eventos', OLD.`eventos`, 'ativo', OLD.`ativo`, 'criado_em', OLD.`criado_em`), JSON_SET(JSON_OBJECT('id', NEW.`id`, 'empresa_id', NEW.`empresa_id`, 'url', NEW.`url`, 'eventos', NEW.`eventos`, 'ativo', NEW.`ativo`, 'criado_em', NEW.`criado_em`), '$.sensiveis_alterados', CONCAT_WS(',', IF(OLD.`segredo` <=> NEW.`segredo`, NULL, 'segredo'))));
  END IF;
END$$

CREATE TRIGGER trg_aud_webhooks_del AFTER DELETE ON webhooks FOR EACH ROW
  CALL astro_auditoria.registrar('webhooks', 'DELETE', OLD.id, JSON_OBJECT('id', OLD.`id`, 'empresa_id', OLD.`empresa_id`, 'url', OLD.`url`, 'eventos', OLD.`eventos`, 'ativo', OLD.`ativo`, 'criado_em', OLD.`criado_em`), NULL)$$

CREATE TRIGGER trg_aud_cartoes_ins AFTER INSERT ON cartoes FOR EACH ROW
BEGIN
  CALL astro_auditoria.registrar('cartoes', 'INSERT', NEW.id, NULL, JSON_OBJECT('id', NEW.`id`, 'carteira_id', NEW.`carteira_id`, 'apelido', NEW.`apelido`, 'numero_masc', NEW.`numero_masc`, 'bandeira', NEW.`bandeira`, 'validade', NEW.`validade`, 'virtual', NEW.`virtual`, 'estado', NEW.`estado`, 'compras_online', NEW.`compras_online`, 'compras_internacionais', NEW.`compras_internacionais`, 'limite', NEW.`limite`, 'criado_em', NEW.`criado_em`));
END$$

CREATE TRIGGER trg_aud_cartoes_upd AFTER UPDATE ON cartoes FOR EACH ROW
BEGIN
  IF NOT (OLD.`id` <=> NEW.`id` AND OLD.`carteira_id` <=> NEW.`carteira_id` AND OLD.`apelido` <=> NEW.`apelido` AND OLD.`numero_masc` <=> NEW.`numero_masc` AND OLD.`bandeira` <=> NEW.`bandeira` AND OLD.`validade` <=> NEW.`validade` AND OLD.`virtual` <=> NEW.`virtual` AND OLD.`estado` <=> NEW.`estado` AND OLD.`compras_online` <=> NEW.`compras_online` AND OLD.`compras_internacionais` <=> NEW.`compras_internacionais` AND OLD.`limite` <=> NEW.`limite` AND OLD.`criado_em` <=> NEW.`criado_em`) THEN
    CALL astro_auditoria.registrar('cartoes', 'UPDATE', NEW.id, JSON_OBJECT('id', OLD.`id`, 'carteira_id', OLD.`carteira_id`, 'apelido', OLD.`apelido`, 'numero_masc', OLD.`numero_masc`, 'bandeira', OLD.`bandeira`, 'validade', OLD.`validade`, 'virtual', OLD.`virtual`, 'estado', OLD.`estado`, 'compras_online', OLD.`compras_online`, 'compras_internacionais', OLD.`compras_internacionais`, 'limite', OLD.`limite`, 'criado_em', OLD.`criado_em`), JSON_OBJECT('id', NEW.`id`, 'carteira_id', NEW.`carteira_id`, 'apelido', NEW.`apelido`, 'numero_masc', NEW.`numero_masc`, 'bandeira', NEW.`bandeira`, 'validade', NEW.`validade`, 'virtual', NEW.`virtual`, 'estado', NEW.`estado`, 'compras_online', NEW.`compras_online`, 'compras_internacionais', NEW.`compras_internacionais`, 'limite', NEW.`limite`, 'criado_em', NEW.`criado_em`));
  END IF;
END$$

CREATE TRIGGER trg_aud_cartoes_del AFTER DELETE ON cartoes FOR EACH ROW
  CALL astro_auditoria.registrar('cartoes', 'DELETE', OLD.id, JSON_OBJECT('id', OLD.`id`, 'carteira_id', OLD.`carteira_id`, 'apelido', OLD.`apelido`, 'numero_masc', OLD.`numero_masc`, 'bandeira', OLD.`bandeira`, 'validade', OLD.`validade`, 'virtual', OLD.`virtual`, 'estado', OLD.`estado`, 'compras_online', OLD.`compras_online`, 'compras_internacionais', OLD.`compras_internacionais`, 'limite', OLD.`limite`, 'criado_em', OLD.`criado_em`), NULL)$$

CREATE TRIGGER trg_aud_dispositivos_ins AFTER INSERT ON dispositivos FOR EACH ROW
BEGIN
  CALL astro_auditoria.registrar('dispositivos', 'INSERT', NEW.id, NULL, JSON_OBJECT('id', NEW.`id`, 'usuario_id', NEW.`usuario_id`, 'id_hash', NEW.`id_hash`, 'nome', NEW.`nome`, 'confiavel', NEW.`confiavel`, 'confiavel_em', NEW.`confiavel_em`, 'bloqueado', NEW.`bloqueado`, 'bloqueado_em', NEW.`bloqueado_em`, 'removido', NEW.`removido`, 'atestacao', NEW.`atestacao`, 'criado_em', NEW.`criado_em`));
END$$

CREATE TRIGGER trg_aud_dispositivos_upd AFTER UPDATE ON dispositivos FOR EACH ROW
BEGIN
  IF NOT (OLD.`id` <=> NEW.`id` AND OLD.`usuario_id` <=> NEW.`usuario_id` AND OLD.`id_hash` <=> NEW.`id_hash` AND OLD.`nome` <=> NEW.`nome` AND OLD.`confiavel` <=> NEW.`confiavel` AND OLD.`confiavel_em` <=> NEW.`confiavel_em` AND OLD.`bloqueado` <=> NEW.`bloqueado` AND OLD.`bloqueado_em` <=> NEW.`bloqueado_em` AND OLD.`removido` <=> NEW.`removido` AND OLD.`atestacao` <=> NEW.`atestacao` AND OLD.`criado_em` <=> NEW.`criado_em`) THEN
    CALL astro_auditoria.registrar('dispositivos', 'UPDATE', NEW.id, JSON_OBJECT('id', OLD.`id`, 'usuario_id', OLD.`usuario_id`, 'id_hash', OLD.`id_hash`, 'nome', OLD.`nome`, 'confiavel', OLD.`confiavel`, 'confiavel_em', OLD.`confiavel_em`, 'bloqueado', OLD.`bloqueado`, 'bloqueado_em', OLD.`bloqueado_em`, 'removido', OLD.`removido`, 'atestacao', OLD.`atestacao`, 'criado_em', OLD.`criado_em`), JSON_OBJECT('id', NEW.`id`, 'usuario_id', NEW.`usuario_id`, 'id_hash', NEW.`id_hash`, 'nome', NEW.`nome`, 'confiavel', NEW.`confiavel`, 'confiavel_em', NEW.`confiavel_em`, 'bloqueado', NEW.`bloqueado`, 'bloqueado_em', NEW.`bloqueado_em`, 'removido', NEW.`removido`, 'atestacao', NEW.`atestacao`, 'criado_em', NEW.`criado_em`));
  END IF;
END$$

CREATE TRIGGER trg_aud_dispositivos_del AFTER DELETE ON dispositivos FOR EACH ROW
  CALL astro_auditoria.registrar('dispositivos', 'DELETE', OLD.id, JSON_OBJECT('id', OLD.`id`, 'usuario_id', OLD.`usuario_id`, 'id_hash', OLD.`id_hash`, 'nome', OLD.`nome`, 'confiavel', OLD.`confiavel`, 'confiavel_em', OLD.`confiavel_em`, 'bloqueado', OLD.`bloqueado`, 'bloqueado_em', OLD.`bloqueado_em`, 'removido', OLD.`removido`, 'atestacao', OLD.`atestacao`, 'criado_em', OLD.`criado_em`), NULL)$$

DELIMITER ;
