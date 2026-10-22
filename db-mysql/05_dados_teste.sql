-- =============================================================================
-- 05_dados_teste.sql  —  SÓ LABORATÓRIO — executar como svc_astro_migrator
-- =============================================================================
-- NUNCA rode este arquivo na Azure de produção. Ele cria:
--   * uma chave de contexto ALEATÓRIA (ninguém a conhece; serve só ao lab);
--   * astro_privado.lab_entrar_como(): assina um contexto para a SUA conexão,
--     para você testar no Workbench sem ter a aplicação rodando;
--   * dados fictícios. Os "envelopes" de dado pessoal têm o formato certo mas
--     NÃO são decifráveis (são bytes aleatórios): dado real só a API cifra.
-- O 99_fechar_janela_migracao.sql apaga as rotinas de laboratório.
-- =============================================================================

USE astro_privado;

-- Chave de contexto do laboratório (32 bytes aleatórios gerados pelo servidor).
INSERT INTO contexto_chave (id, chave) VALUES (1, RANDOM_BYTES(32))
  ON DUPLICATE KEY UPDATE chave = VALUES(chave), trocada_em = CURRENT_TIMESTAMP(6);

DELIMITER $$

-- Envelope falso no formato "pii:v1:<indice>:<token>". O índice aqui é SHA-256
-- (no sistema real é HMAC com PII_INDEX_KEY, calculado pela API).
CREATE FUNCTION lab_envelope(p_dominio VARCHAR(30), p_valor VARCHAR(200)) RETURNS TEXT CHARSET ascii
NOT DETERMINISTIC NO SQL
RETURN CONCAT('pii:v1:', SHA2(CONCAT(p_dominio, ':', p_valor), 256), ':', LOWER(HEX(RANDOM_BYTES(100))))$$

-- Assina um contexto válido por 30 s para ESTA conexão (faz o papel da API).
-- Uso:  CALL astro_privado.lab_entrar_como('usuario', 2, JSON_ARRAY(3, 4));
CREATE PROCEDURE lab_entrar_como(IN p_modo VARCHAR(10), IN p_usuario INT, IN p_carteiras JSON)
READS SQL DATA SQL SECURITY DEFINER
BEGIN
  DECLARE v_chave VARBINARY(32);
  DECLARE v_corpo TEXT CHARSET utf8mb4;
  SELECT chave INTO v_chave FROM astro_privado.contexto_chave WHERE id = 1;
  SET v_corpo = CAST(JSON_OBJECT('cid', CONNECTION_ID(), 'exp', UNIX_TIMESTAMP() + 30, 'modo', p_modo,
                                 'tx', LOWER(HEX(RANDOM_BYTES(16))), 'usuario_id', p_usuario,
                                 'carteiras_operacao', COALESCE(p_carteiras, JSON_ARRAY())) AS CHAR);
  SET @astro_contexto = v_corpo;
  SET @astro_prova = astro_privado.hmac_sha256(CAST(v_corpo AS BINARY), v_chave);
END$$

DELIMITER ;

-- -----------------------------------------------------------------------------
-- Dados fictícios
--   1 Admin Astro (papel ADMIN)      carteira 1 CAIXA, 2 TRIBUTOS (sistema)
--   2 Ana   (PF)                     carteira 3
--   3 Bruno (PF)                     carteira 4
--   4 Carla (ADMIN da empresa 1)     carteira 5  (PJ "Mercado Exemplo")
--   5 Diego (OPERADOR da empresa 1, alçada R$ 500)
-- -----------------------------------------------------------------------------
USE astro_dados;
SET @hash_lab = '$argon2id$v=19$m=19456,t=2,p=1$bGFib3JhdG9yaW8$bGFiLW5hby1lLXNlbmhhLXJlYWw';

INSERT INTO usuarios (id, nome, cpf, email, senha_hash, papel, kyc_status, ativo) VALUES
 (1, astro_privado.lab_envelope('nome','Admin Astro'), NULL, astro_privado.lab_envelope('email','admin@astro.test'), @hash_lab, 'ADMIN',   'aprovado', TRUE),
 (2, astro_privado.lab_envelope('nome','Ana'),   astro_privado.lab_envelope('cpf','52998224725'), astro_privado.lab_envelope('email','ana@astro.test'),   @hash_lab, 'USUARIO', 'aprovado', TRUE),
 (3, astro_privado.lab_envelope('nome','Bruno'), astro_privado.lab_envelope('cpf','11144477735'), astro_privado.lab_envelope('email','bruno@astro.test'), @hash_lab, 'USUARIO', 'aprovado', TRUE),
 (4, astro_privado.lab_envelope('nome','Carla'), astro_privado.lab_envelope('cpf','39053344705'), astro_privado.lab_envelope('email','carla@astro.test'), @hash_lab, 'USUARIO', 'aprovado', TRUE),
 (5, astro_privado.lab_envelope('nome','Diego'), astro_privado.lab_envelope('cpf','15350946056'), astro_privado.lab_envelope('email','diego@astro.test'), @hash_lab, 'USUARIO', 'aprovado', TRUE);

INSERT INTO empresas (id, cnpj, razao_social, porte, regime_apuracao, representante_usuario_id, kyb_status) VALUES
 (1, astro_privado.lab_envelope('cnpj','11222333000181'), astro_privado.lab_envelope('razao','Mercado Exemplo LTDA'), 'PME', 'REGULAR', 4, 'aprovado');

INSERT INTO vinculos (usuario_id, empresa_id, cpf, papel, alcada, status, ativo, aceito_em) VALUES
 (4, 1, astro_privado.lab_envelope('cpf','39053344705'), 'ADMIN',    NULL,   'ativo', TRUE, UTC_TIMESTAMP(6)),
 (5, 1, astro_privado.lab_envelope('cpf','15350946056'), 'OPERADOR', 500.00, 'ativo', TRUE, UTC_TIMESTAMP(6));

INSERT INTO carteiras (id, titular_tipo, usuario_id, empresa_id, sistema, numero) VALUES
 (1, 'SISTEMA', NULL, NULL, 'CAIXA',    '00000001-7'),
 (2, 'SISTEMA', NULL, NULL, 'TRIBUTOS', '00000002-5'),
 (3, 'PF',      2,    NULL, NULL,       '48213907-1'),
 (4, 'PF',      3,    NULL, NULL,       '70315562-8'),
 (5, 'PJ',      NULL, 1,    NULL,       '26649031-4');

INSERT INTO limites (carteira_id, por_transacao, diurno, noturno) VALUES
 (3, 2000.00, 5000.00, 1000.00), (4, 2000.00, 5000.00, 1000.00), (5, 20000.00, 50000.00, 10000.00);

-- Depósitos iniciais saindo da CAIXA (que pode ficar negativa), com o ledger.
INSERT INTO transacoes (id, origem_carteira_id, destino_carteira_id, tipo, valor_bruto, liquido, tipo_destino, auth_metodo, idempotency_key) VALUES
 (1, 1, 3, 'deposito', 1000.00, 1000.00, 'PF', 'SISTEMA', 'lab-deposito-ana-0001'),
 (2, 1, 4, 'deposito',  500.00,  500.00, 'PF', 'SISTEMA', 'lab-deposito-bruno-0001'),
 (3, 1, 5, 'deposito', 5000.00, 5000.00, 'PJ', 'SISTEMA', 'lab-deposito-empresa-0001');
INSERT INTO historico_saldo (carteira_id, saldo_anterior, saldo_novo, motivo, transacao_id) VALUES
 (1,     0.00, -1000.00, 'deposito', 1), (3, 0.00, 1000.00, 'deposito', 1),
 (1, -1000.00, -1500.00, 'deposito', 2), (4, 0.00,  500.00, 'deposito', 2),
 (1, -1500.00, -6500.00, 'deposito', 3), (5, 0.00, 5000.00, 'deposito', 3);
UPDATE carteiras SET saldo = CASE id WHEN 1 THEN -6500 WHEN 3 THEN 1000 WHEN 4 THEN 500 WHEN 5 THEN 5000 ELSE saldo END;

INSERT INTO chaves_pix (carteira_id, tipo, valor) VALUES
 (3, 'cpf',   astro_privado.lab_envelope('pix','52998224725')),
 (4, 'email', astro_privado.lab_envelope('pix','bruno@astro.test'));

INSERT INTO dispositivos (usuario_id, id_hash, nome, confiavel) VALUES
 (2, SHA2('aparelho-ana', 256),   'Celular da Ana',   TRUE),
 (3, SHA2('aparelho-bruno', 256), 'Celular do Bruno', TRUE);

INSERT INTO cartoes (carteira_id, numero_masc, validade) VALUES (3, '**** **** **** 4821', '10/30');

INSERT INTO funcionarios (empresa_id, nome, cpf, cargo, salario) VALUES
 (1, astro_privado.lab_envelope('nome','Eva'), astro_privado.lab_envelope('cpf','71428793860'), 'Caixa', 2500.00);

INSERT INTO produtos (nome, descricao, preco, categoria, emoji, lojista_carteira_id) VALUES
 ('Fone Bluetooth', 'Fone sem fio com cancelamento de ruído', 199.90, 'Eletrônicos', '🎧', 5);

-- Conferência rápida (como migrador, sem filtro): 5 usuários, 5 carteiras.
SELECT (SELECT COUNT(*) FROM usuarios) AS usuarios, (SELECT COUNT(*) FROM carteiras) AS carteiras,
       (SELECT SUM(saldo) FROM carteiras) AS soma_saldos_deve_ser_zero;
