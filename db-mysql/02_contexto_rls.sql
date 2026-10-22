-- =============================================================================
-- 02_contexto_rls.sql  —  executar como svc_astro_migrator
-- =============================================================================
-- O PROBLEMA: o MySQL não tem Row-Level Security (RLS). No PostgreSQL, o banco
-- filtrava sozinho as linhas de cada titular (13 tabelas). Sem isso, um bug ou um
-- SQL injection na API devolveria dados de qualquer cliente.
--
-- A COMPENSAÇÃO (mesma ideia do original, peça por peça):
--   1. A API não tem NENHUM privilégio nas tabelas reais (astro_dados).
--   2. Ela só enxerga views em `astro` (script 03), com o mesmo nome das tabelas.
--      As views são SQL SECURITY DEFINER: rodam com o privilégio de quem as
--      criou e filtram as linhas chamando as funções de política daqui.
--   3. Quem é o usuário? A cada transação a API grava em duas variáveis de sessão
--      um CONTEXTO em JSON e a PROVA (HMAC-SHA256 do JSON). A chave do HMAC fica
--      numa tabela que a API não lê; só a função ctx(), que confere a prova.
--      Contexto forjado ou vencido => ctx() devolve NULL => nenhuma linha.
--   4. Escritas que dependem de quem escreve (saldo, cadastro) são conferidas
--      por TRIGGERS nas tabelas reais (script 04), que também chamam ctx().
--
-- Formato do contexto (gerado pela API, ver integracao-app/contexto_mysql.py):
--   {"cid":123,"exp":1760000000,"modo":"usuario","tx":"<32 hex>","usuario_id":5,
--    "carteiras_operacao":[10,11], "desafio_usuario_id":..., "kyc_caso_id":...}
--   cid  = CONNECTION_ID() da conexão  (no PG era o pid do backend)
--   tx   = número aleatório novo a cada transação (no PG era o txid)
--   exp  = validade de no máximo 35 s
-- =============================================================================

USE astro_privado;

-- Chave do HMAC. Uma linha só (id = 1), 32 bytes. Ninguém além do DEFINER das
-- funções tem SELECT aqui. A chave é gravada pelo procedimento do runbook
-- (SEGURANCA-BANCO-MYSQL.md §4.3) a partir do Key Vault — nunca por arquivo.
CREATE TABLE contexto_chave (
  id          TINYINT       NOT NULL,
  chave       VARBINARY(32) NOT NULL,
  trocada_em  DATETIME(6)   NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  CONSTRAINT ck_contexto_chave_id      CHECK (id = 1),
  CONSTRAINT ck_contexto_chave_tamanho CHECK (LENGTH(chave) = 32)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Registros criados NESTA transação (substitui o "xmin = txid_current()" do PG).
-- Serve para o cadastro: quem acabou de criar o usuário pode criar a carteira
-- e o limite dele na mesma transação, e mais nada. Como a tabela é InnoDB, um
-- ROLLBACK apaga a linha junto com o cadastro.
CREATE TABLE cadastro_sessao (
  conexao      BIGINT UNSIGNED NOT NULL,
  tx           CHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  tabela       VARCHAR(20)     NOT NULL,
  registro_id  INT             NOT NULL,
  criado_em    DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (conexao, tx, tabela, registro_id),
  KEY ix_cadastro_sessao_criado (criado_em)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

DELIMITER $$

-- -----------------------------------------------------------------------------
-- HMAC-SHA256 (RFC 2104) só com funções nativas: SHA2() e XOR de strings binárias.
--   HMAC(K, m) = SHA256( (K xor opad) || SHA256( (K xor ipad) || m ) )
-- É a mesma conta do original (astro_privado.hmac256 em PL/pgSQL).
-- -----------------------------------------------------------------------------
CREATE FUNCTION hmac_sha256(p_mensagem LONGBLOB, p_chave VARBINARY(32))
RETURNS CHAR(64) CHARSET ascii
DETERMINISTIC NO SQL
BEGIN
  DECLARE k BINARY(64);
  IF p_chave IS NULL OR LENGTH(p_chave) <> 32 THEN
    RETURN NULL;
  END IF;
  SET k = CONCAT(p_chave, UNHEX(REPEAT('00', 32)));        -- chave completada até 64 bytes
  RETURN SHA2(CONCAT(k ^ UNHEX(REPEAT('5c', 64)),
                     UNHEX(SHA2(CONCAT(k ^ UNHEX(REPEAT('36', 64)), p_mensagem), 256))), 256);
END$$

-- -----------------------------------------------------------------------------
-- ctx(): devolve o contexto JSON SE e SOMENTE SE a prova confere, a conexão é a
-- mesma e não venceu. Em qualquer outro caso (inclusive erro), NULL.
-- -----------------------------------------------------------------------------
CREATE FUNCTION ctx() RETURNS JSON
NOT DETERMINISTIC READS SQL DATA SQL SECURITY DEFINER
BEGIN
  DECLARE v_corpo  TEXT CHARSET utf8mb4 DEFAULT @astro_contexto;
  DECLARE v_prova  TEXT CHARSET utf8mb4 DEFAULT @astro_prova;
  DECLARE v_chave  VARBINARY(32);
  DECLARE v_dados  JSON;
  DECLARE v_modo   VARCHAR(10);
  DECLARE v_exp    BIGINT;
  DECLARE v_agora  BIGINT DEFAULT UNIX_TIMESTAMP();
  -- Qualquer erro (JSON inválido, tipo errado...) = sem contexto. Nunca "passa".
  DECLARE EXIT HANDLER FOR SQLEXCEPTION RETURN NULL;

  IF v_corpo IS NULL OR CHAR_LENGTH(v_corpo) > 2048
     OR v_prova IS NULL OR CHAR_LENGTH(v_prova) <> 64 THEN
    RETURN NULL;
  END IF;
  SELECT chave INTO v_chave FROM astro_privado.contexto_chave WHERE id = 1;
  IF v_chave IS NULL THEN
    RETURN NULL;
  END IF;
  -- Compara os HASHES das duas provas, e não as provas: assim o tempo da
  -- comparação não revela quantos caracteres batem (mesma técnica do original).
  IF SHA2(astro_privado.hmac_sha256(CAST(CONVERT(v_corpo USING utf8mb4) AS BINARY), v_chave), 256)
     <> SHA2(LOWER(v_prova), 256) THEN
    RETURN NULL;
  END IF;
  IF NOT JSON_VALID(v_corpo) THEN
    RETURN NULL;
  END IF;
  SET v_dados = CAST(v_corpo AS JSON);
  SET v_modo  = JSON_VALUE(v_dados, '$.modo');
  SET v_exp   = JSON_VALUE(v_dados, '$.exp' RETURNING SIGNED);
  IF v_modo IS NULL OR v_modo NOT IN ('publico','usuario','sistema')
     OR JSON_VALUE(v_dados, '$.cid' RETURNING UNSIGNED) IS NULL
     OR JSON_VALUE(v_dados, '$.cid' RETURNING UNSIGNED) <> CONNECTION_ID()
     OR v_exp IS NULL OR v_exp < v_agora OR v_exp > v_agora + 35
     OR COALESCE(JSON_VALUE(v_dados, '$.tx'), '') NOT REGEXP '^[0-9a-f]{32}$' THEN
    RETURN NULL;
  END IF;
  IF v_modo = 'usuario' AND COALESCE(JSON_VALUE(v_dados, '$.usuario_id' RETURNING SIGNED), 0) < 1 THEN
    RETURN NULL;
  END IF;
  RETURN v_dados;
END$$

-- Atalhos para ler o contexto já validado (recebem o JSON, não validam de novo).
CREATE FUNCTION ctx_modo(c JSON) RETURNS VARCHAR(10) CHARSET utf8mb4
DETERMINISTIC NO SQL
RETURN JSON_VALUE(c, '$.modo')$$

CREATE FUNCTION ctx_uid(c JSON) RETURNS INT
DETERMINISTIC NO SQL
RETURN CASE WHEN JSON_VALUE(c, '$.modo') = 'usuario'
            THEN JSON_VALUE(c, '$.usuario_id' RETURNING SIGNED) END$$

-- A conta de migração tem passe livre nas políticas (igual à policy
-- astro_migracao do PG). USER() é a conta que fez LOGIN — dentro de view,
-- procedure ou trigger, CURRENT_USER() seria o dono do objeto, não o cliente.
-- Não há usuários anônimos (script 00), então o nome do login é o da conta.
CREATE FUNCTION sessao_migrador() RETURNS BOOLEAN
NOT DETERMINISTIC NO SQL
RETURN SUBSTRING_INDEX(USER(), '@', 1) = 'svc_astro_migrator'$$

-- "comum" do original: modo sistema, ou pessoa com papel ADMIN e ativa.
CREATE FUNCTION ctx_comum(c JSON) RETURNS BOOLEAN
NOT DETERMINISTIC READS SQL DATA SQL SECURITY DEFINER
BEGIN
  IF c IS NULL THEN RETURN FALSE; END IF;
  IF astro_privado.ctx_modo(c) = 'sistema' THEN RETURN TRUE; END IF;
  RETURN astro_privado.ctx_modo(c) = 'usuario' AND EXISTS (
    SELECT 1 FROM astro_dados.usuarios u
     WHERE u.id = astro_privado.ctx_uid(c) AND u.ativo AND u.papel = 'ADMIN');
END$$

-- A pessoa do contexto tem vínculo ATIVO com a empresa?
CREATE FUNCTION ctx_vinculo(c JSON, p_empresa INT) RETURNS BOOLEAN
NOT DETERMINISTIC READS SQL DATA SQL SECURITY DEFINER
RETURN p_empresa IS NOT NULL AND astro_privado.ctx_modo(c) = 'usuario' AND EXISTS (
  SELECT 1 FROM astro_dados.vinculos v
   WHERE v.empresa_id = p_empresa AND v.usuario_id = astro_privado.ctx_uid(c)
     AND v.ativo AND v.status = 'ativo')$$

-- ... e esse vínculo é de ADMIN da empresa?
CREATE FUNCTION ctx_vinculo_admin(c JSON, p_empresa INT) RETURNS BOOLEAN
NOT DETERMINISTIC READS SQL DATA SQL SECURITY DEFINER
RETURN p_empresa IS NOT NULL AND astro_privado.ctx_modo(c) = 'usuario' AND EXISTS (
  SELECT 1 FROM astro_dados.vinculos v
   WHERE v.empresa_id = p_empresa AND v.usuario_id = astro_privado.ctx_uid(c)
     AND v.ativo AND v.status = 'ativo' AND v.papel = 'ADMIN')$$

-- A carteira é "própria": PF do usuário ou PJ de empresa com vínculo ativo.
CREATE FUNCTION ctx_carteira_propria(c JSON, p_carteira INT) RETURNS BOOLEAN
NOT DETERMINISTIC READS SQL DATA SQL SECURITY DEFINER
BEGIN
  DECLARE v_usuario INT;
  DECLARE v_empresa INT;
  IF c IS NULL OR p_carteira IS NULL OR astro_privado.ctx_modo(c) <> 'usuario' THEN
    RETURN FALSE;
  END IF;
  SELECT usuario_id, empresa_id INTO v_usuario, v_empresa
    FROM astro_dados.carteiras WHERE id = p_carteira;
  RETURN COALESCE(v_usuario = astro_privado.ctx_uid(c), FALSE)
      OR astro_privado.ctx_vinculo(c, v_empresa);
END$$

-- A carteira está no ESCOPO da operação assinado pela API? (necessário para
-- mexer em saldo, mesmo na carteira do próprio titular — igual ao original)
CREATE FUNCTION ctx_no_escopo(c JSON, p_carteira INT) RETURNS BOOLEAN
DETERMINISTIC NO SQL
RETURN p_carteira IS NOT NULL
   AND COALESCE(JSON_CONTAINS(JSON_EXTRACT(c, '$.carteiras_operacao'), CAST(p_carteira AS JSON)), FALSE)$$

-- O registro foi criado nesta transação (mesma conexão + mesmo "tx")?
CREATE FUNCTION ctx_criado_agora(c JSON, p_tabela VARCHAR(20), p_id INT) RETURNS BOOLEAN
NOT DETERMINISTIC READS SQL DATA SQL SECURITY DEFINER
RETURN c IS NOT NULL AND p_id IS NOT NULL AND EXISTS (
  SELECT 1 FROM astro_privado.cadastro_sessao s
   WHERE s.conexao = CONNECTION_ID() AND s.tx = JSON_VALUE(c, '$.tx')
     AND s.tabela = p_tabela AND s.registro_id = p_id)$$

-- =============================================================================
-- POLÍTICAS DE LEITURA (chamadas no WHERE das views do script 03)
-- Cada uma valida o contexto UMA vez e decide. Nome = pode_ler_<tabela>.
-- =============================================================================

-- Tabelas sem dono claro: basta um contexto válido. MAIS SEGURO que o original,
-- onde elas não tinham filtro nenhum: aqui, quem tem só a senha do banco (sem a
-- chave de contexto) não lê nada.
CREATE FUNCTION pode_ler() RETURNS BOOLEAN
NOT DETERMINISTIC READS SQL DATA SQL SECURITY DEFINER
RETURN astro_privado.ctx() IS NOT NULL$$

-- carteiras: comum OU própria OU no escopo da operação OU criada agora (cadastro).
CREATE FUNCTION pode_ler_carteira(p_id INT, p_titular VARCHAR(10), p_usuario INT, p_empresa INT) RETURNS BOOLEAN
NOT DETERMINISTIC READS SQL DATA SQL SECURITY DEFINER
BEGIN
  DECLARE c JSON DEFAULT astro_privado.ctx();
  IF c IS NULL THEN RETURN FALSE; END IF;
  RETURN astro_privado.ctx_comum(c)
      OR (astro_privado.ctx_modo(c) = 'usuario'
          AND (COALESCE(p_usuario = astro_privado.ctx_uid(c), FALSE) OR astro_privado.ctx_vinculo(c, p_empresa)))
      OR astro_privado.ctx_no_escopo(c, p_id)
      OR astro_privado.pode_criar_carteira(c, p_titular, p_usuario, p_empresa);
END$$

-- Carteira "nova" (do original): cadastro público de PF criando a carteira do
-- usuário criado agora, ou representante abrindo a conta da empresa criada agora.
CREATE FUNCTION pode_criar_carteira(c JSON, p_titular VARCHAR(10), p_usuario INT, p_empresa INT) RETURNS BOOLEAN
NOT DETERMINISTIC READS SQL DATA SQL SECURITY DEFINER
RETURN c IS NOT NULL AND (
     (astro_privado.ctx_modo(c) = 'publico' AND p_titular = 'PF'
        AND astro_privado.ctx_criado_agora(c, 'usuarios', p_usuario))
  OR (astro_privado.ctx_modo(c) = 'usuario' AND p_titular = 'PJ'
        AND astro_privado.ctx_criado_agora(c, 'empresas', p_empresa)
        AND EXISTS (SELECT 1 FROM astro_dados.empresas e
                     WHERE e.id = p_empresa AND e.representante_usuario_id = astro_privado.ctx_uid(c))))$$

-- transacoes: comum OU participante (origem ou destino é carteira própria).
CREATE FUNCTION pode_ler_transacao(p_origem INT, p_destino INT) RETURNS BOOLEAN
NOT DETERMINISTIC READS SQL DATA SQL SECURITY DEFINER
BEGIN
  DECLARE c JSON DEFAULT astro_privado.ctx();
  IF c IS NULL THEN RETURN FALSE; END IF;
  RETURN astro_privado.ctx_comum(c)
      OR astro_privado.ctx_carteira_propria(c, p_origem)
      OR astro_privado.ctx_carteira_propria(c, p_destino);
END$$

-- historico_saldo: comum OU carteira própria OU no escopo da operação.
CREATE FUNCTION pode_ler_historico(p_carteira INT) RETURNS BOOLEAN
NOT DETERMINISTIC READS SQL DATA SQL SECURITY DEFINER
BEGIN
  DECLARE c JSON DEFAULT astro_privado.ctx();
  IF c IS NULL THEN RETURN FALSE; END IF;
  RETURN astro_privado.ctx_comum(c)
      OR astro_privado.ctx_carteira_propria(c, p_carteira)
      OR astro_privado.ctx_no_escopo(c, p_carteira);
END$$

-- cartoes, rendimentos: comum OU carteira própria.
CREATE FUNCTION pode_ler_por_carteira(p_carteira INT) RETURNS BOOLEAN
NOT DETERMINISTIC READS SQL DATA SQL SECURITY DEFINER
BEGIN
  DECLARE c JSON DEFAULT astro_privado.ctx();
  IF c IS NULL THEN RETURN FALSE; END IF;
  RETURN astro_privado.ctx_comum(c) OR astro_privado.ctx_carteira_propria(c, p_carteira);
END$$

-- limites: idem + o cadastro público pode criar/ler o limite da carteira criada agora.
CREATE FUNCTION pode_ler_limite(p_carteira INT) RETURNS BOOLEAN
NOT DETERMINISTIC READS SQL DATA SQL SECURITY DEFINER
BEGIN
  DECLARE c JSON DEFAULT astro_privado.ctx();
  IF c IS NULL THEN RETURN FALSE; END IF;
  RETURN astro_privado.ctx_comum(c)
      OR astro_privado.ctx_carteira_propria(c, p_carteira)
      OR (astro_privado.ctx_modo(c) = 'publico' AND astro_privado.ctx_criado_agora(c, 'carteiras', p_carteira));
END$$

-- dispositivos, refresh_tokens, pontos_movimentos: comum OU a própria pessoa.
CREATE FUNCTION pode_ler_por_usuario(p_usuario INT) RETURNS BOOLEAN
NOT DETERMINISTIC READS SQL DATA SQL SECURITY DEFINER
BEGIN
  DECLARE c JSON DEFAULT astro_privado.ctx();
  IF c IS NULL THEN RETURN FALSE; END IF;
  RETURN astro_privado.ctx_comum(c) OR COALESCE(p_usuario = astro_privado.ctx_uid(c), FALSE);
END$$

-- funcionarios, documentos_empresa, operacoes_pendentes: comum OU vínculo ativo.
CREATE FUNCTION pode_ler_por_empresa(p_empresa INT) RETURNS BOOLEAN
NOT DETERMINISTIC READS SQL DATA SQL SECURITY DEFINER
BEGIN
  DECLARE c JSON DEFAULT astro_privado.ctx();
  IF c IS NULL THEN RETURN FALSE; END IF;
  RETURN astro_privado.ctx_comum(c) OR astro_privado.ctx_vinculo(c, p_empresa);
END$$

-- desafios_biometria: comum OU dono OU fluxo público do próprio desafio.
CREATE FUNCTION pode_ler_desafio(p_usuario INT) RETURNS BOOLEAN
NOT DETERMINISTIC READS SQL DATA SQL SECURITY DEFINER
BEGIN
  DECLARE c JSON DEFAULT astro_privado.ctx();
  IF c IS NULL THEN RETURN FALSE; END IF;
  RETURN astro_privado.ctx_comum(c)
      OR COALESCE(p_usuario = astro_privado.ctx_uid(c), FALSE)
      OR (astro_privado.ctx_modo(c) = 'publico'
          AND (p_usuario IS NULL OR p_usuario = JSON_VALUE(c, '$.desafio_usuario_id' RETURNING SIGNED)));
END$$

-- documentos_identidade: comum OU dono do caso OU vínculo com a empresa do caso
-- OU o caso do cadastro em andamento (caso sem dono, id assinado no contexto).
CREATE FUNCTION pode_ler_documento(p_caso INT) RETURNS BOOLEAN
NOT DETERMINISTIC READS SQL DATA SQL SECURITY DEFINER
BEGIN
  DECLARE c JSON DEFAULT astro_privado.ctx();
  DECLARE v_usuario INT;
  DECLARE v_empresa INT;
  IF c IS NULL THEN RETURN FALSE; END IF;
  IF astro_privado.ctx_comum(c) THEN RETURN TRUE; END IF;
  SELECT usuario_id, empresa_id INTO v_usuario, v_empresa FROM astro_dados.kyc_casos WHERE id = p_caso;
  RETURN COALESCE(v_usuario = astro_privado.ctx_uid(c), FALSE)
      OR astro_privado.ctx_vinculo(c, v_empresa)
      OR (astro_privado.ctx_modo(c) = 'publico' AND v_usuario IS NULL AND v_empresa IS NULL
          AND p_caso = JSON_VALUE(c, '$.kyc_caso_id' RETURNING SIGNED));
END$$

-- contestacoes (NOVO, o original não filtrava): comum OU quem abriu OU
-- participante da transação contestada.
CREATE FUNCTION pode_ler_contestacao(p_transacao INT, p_aberta_por INT) RETURNS BOOLEAN
NOT DETERMINISTIC READS SQL DATA SQL SECURITY DEFINER
BEGIN
  DECLARE c JSON DEFAULT astro_privado.ctx();
  DECLARE v_origem INT;
  DECLARE v_destino INT;
  IF c IS NULL THEN RETURN FALSE; END IF;
  IF astro_privado.ctx_comum(c) OR COALESCE(p_aberta_por = astro_privado.ctx_uid(c), FALSE) THEN
    RETURN TRUE;
  END IF;
  SELECT origem_carteira_id, destino_carteira_id INTO v_origem, v_destino
    FROM astro_dados.transacoes WHERE id = p_transacao;
  RETURN astro_privado.ctx_carteira_propria(c, v_origem) OR astro_privado.ctx_carteira_propria(c, v_destino);
END$$

DELIMITER ;
