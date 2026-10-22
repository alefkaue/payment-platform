-- =============================================================================
-- 07_testes_seguranca.sql  —  executar CONECTADO COMO svc_astro_api (a API)
-- =============================================================================
-- Testes NEGATIVOS: cada bloco marcado "ESPERADO: ERRO" ou "ESPERADO: 0" tenta
-- algo que um invasor (ou um bug) faria. Se algum deles der certo, há falha.
-- Há também testes POSITIVOS ("ESPERADO: OK") para provar que o filtro não
-- está simplesmente bloqueando tudo.
--
-- No Workbench: Query > "Continue on SQL Script Error" (ícone do raio com X)
-- precisa estar LIGADO, senão o script para no primeiro erro esperado.
-- Os contextos assinados valem 30 s: rode o arquivo inteiro de uma vez.
--
-- Códigos de erro que você vai ver:
--   1142  comando negado (sem privilégio na tabela)
--   1143  comando negado na COLUNA
--   1044  acesso negado ao banco
--   1369  CHECK OPTION da view falhou (linha ficaria invisível)
--   1644  SIGNAL de um trigger/procedure (política ou integridade)
--   3819  CHECK constraint violada
-- =============================================================================

SELECT 'T00 identidade da sessao (ESPERADO: svc_astro_api, papel astro_app, TLS ativo)' AS teste;
SELECT CURRENT_USER() AS conta, CURRENT_ROLE() AS papel_ativo;
SHOW SESSION STATUS WHERE Variable_name IN ('Ssl_version', 'Ssl_cipher');

-- ---------------------------------------------------------------- DDL
SELECT 'T01 DROP/CREATE pela API (ESPERADO: ERRO 1142/1044)' AS teste;
DROP VIEW astro.carteiras;
DROP TABLE astro_dados.carteiras;
CREATE TABLE astro.invasao (id INT);
CREATE DATABASE invasao;
ALTER TABLE astro_dados.carteiras DROP CHECK ck_carteira_saldo;
CREATE TRIGGER astro_dados.trg_invasao BEFORE INSERT ON astro_dados.carteiras FOR EACH ROW SET NEW.saldo = 0;

-- ---------------------------------------------------------------- tabelas reais
SELECT 'T02 ler/alterar tabela REAL, chave e auditoria (ESPERADO: ERRO 1142)' AS teste;
SELECT * FROM astro_dados.carteiras;
SELECT * FROM astro_dados.usuarios;
UPDATE astro_dados.carteiras SET saldo = 1000000 WHERE id = 3;
SELECT * FROM astro_privado.contexto_chave;
SELECT * FROM astro_auditoria.trilha;
DELETE FROM astro_auditoria.trilha;

-- ---------------------------------------------------------------- sem contexto
SELECT 'T03 sem contexto assinado: senha do banco sozinha nao le nada (ESPERADO: 0)' AS teste;
SET @astro_contexto = NULL, @astro_prova = NULL;
SELECT (SELECT COUNT(*) FROM astro.carteiras) AS carteiras, (SELECT COUNT(*) FROM astro.usuarios) AS usuarios,
       (SELECT COUNT(*) FROM astro.transacoes) AS transacoes, (SELECT COUNT(*) FROM astro.chaves_pix) AS chaves_pix;

SELECT 'T04 contexto FORJADO dizendo modo sistema, prova inventada (ESPERADO: 0)' AS teste;
SET @astro_contexto = CONCAT('{"cid":', CONNECTION_ID(), ',"exp":', UNIX_TIMESTAMP() + 20,
                             ',"modo":"sistema","tx":"0123456789abcdef0123456789abcdef","usuario_id":null}');
SET @astro_prova = SHA2(@astro_contexto, 256);   -- "assinatura" sem a chave secreta
SELECT (SELECT COUNT(*) FROM astro.carteiras) AS carteiras, (SELECT COUNT(*) FROM astro.usuarios) AS usuarios;

SELECT 'T05 contexto valido de Ana, depois ADULTERADO para usuario_id=3 (ESPERADO: 0)' AS teste;
CALL astro_privado.lab_entrar_como('usuario', 2, NULL);
SET @astro_contexto = REPLACE(@astro_contexto, '"usuario_id": 2', '"usuario_id": 3');
SELECT COUNT(*) AS carteiras_visiveis FROM astro.carteiras;

-- ---------------------------------------------------------------- isolamento
SELECT 'T06 Ana logada ve SO a propria carteira e as proprias transacoes (ESPERADO: OK, so carteira 3)' AS teste;
CALL astro_privado.lab_entrar_como('usuario', 2, NULL);
SELECT id, titular_tipo, usuario_id, saldo FROM astro.carteiras;
SELECT id, origem_carteira_id, destino_carteira_id, valor_bruto FROM astro.transacoes;

SELECT 'T07 Ana tenta LER dados do Bruno e da empresa (IDOR) (ESPERADO: 0)' AS teste;
SELECT (SELECT COUNT(*) FROM astro.carteiras WHERE id = 4) AS carteira_do_bruno,
       (SELECT COUNT(*) FROM astro.dispositivos WHERE usuario_id = 3) AS aparelhos_do_bruno,
       (SELECT COUNT(*) FROM astro.historico_saldo WHERE carteira_id IN (4, 5)) AS extrato_alheio,
       (SELECT COUNT(*) FROM astro.funcionarios) AS folha_da_empresa,
       (SELECT COUNT(*) FROM astro.limites WHERE carteira_id = 4) AS limites_do_bruno;

SELECT 'T08 Ana tenta ALTERAR dados do Bruno (ESPERADO: 0 linhas afetadas ou ERRO 1369/1644)' AS teste;
UPDATE astro.carteiras SET saldo = 0 WHERE id = 4;
SELECT ROW_COUNT() AS linhas_afetadas_saldo_bruno;
UPDATE astro.dispositivos SET bloqueado = TRUE WHERE usuario_id = 3;
SELECT ROW_COUNT() AS linhas_afetadas_aparelho_bruno;
UPDATE astro.limites SET por_transacao = 999999 WHERE carteira_id = 4;
SELECT ROW_COUNT() AS linhas_afetadas_limite_bruno;
INSERT INTO astro.cartoes (carteira_id, numero_masc, validade) VALUES (4, '**** **** **** 0001', '01/31');
INSERT INTO astro.chaves_pix (carteira_id, tipo, valor)
VALUES (4, 'aleatoria', CONCAT('pii:v1:', SHA2('x', 256), ':', REPEAT('a', 120)));
DELETE FROM astro.chaves_pix WHERE carteira_id = 4;

SELECT 'T09 Ana muda o PROPRIO saldo sem escopo de operacao (ESPERADO: ERRO 1644)' AS teste;
UPDATE astro.carteiras SET saldo = 999999 WHERE id = 3;

SELECT 'T10 Ana tenta virar ADMIN ou mudar o dono da carteira (ESPERADO: ERRO 1143)' AS teste;
UPDATE astro.usuarios SET papel = 'ADMIN' WHERE id = 2;
UPDATE astro.carteiras SET usuario_id = 2 WHERE id = 4;
UPDATE astro.transacoes SET valor_bruto = 1.00, liquido = 1.00 WHERE id = 1;

-- ---------------------------------------------------------------- dinheiro
SELECT 'T11 Ana tenta DEBITAR a carteira do Bruno pela procedure (ESPERADO: ERRO 1644)' AS teste;
CALL astro_privado.lab_entrar_como('usuario', 2, JSON_ARRAY(3, 4));
CALL astro.transferir(4, 3, 100.00, NULL, 'teste-roubo-00000000001', @t);

SELECT 'T12 transferencia LEGITIMA Ana -> Bruno R$ 100 (ESPERADO: OK)' AS teste;
CALL astro.transferir(3, 4, 100.00, NULL, 'teste-legitimo-0000000001', @t1);
SELECT @t1 AS transacao_criada, (SELECT saldo FROM astro.carteiras WHERE id = 3) AS saldo_ana_depois;

SELECT 'T13 mesmo pedido REPETIDO (replay) nao debita de novo (ESPERADO: mesma transacao, saldo igual)' AS teste;
CALL astro.transferir(3, 4, 100.00, NULL, 'teste-legitimo-0000000001', @t2);
SELECT @t1 = @t2 AS mesma_transacao, (SELECT saldo FROM astro.carteiras WHERE id = 3) AS saldo_ana;

SELECT 'T14 gastar mais que o saldo / valor negativo / acima do limite (ESPERADO: ERRO 1644)' AS teste;
CALL astro.transferir(3, 4, 1950.00, NULL, 'teste-sem-saldo-00000001', @t);
CALL astro.transferir(3, 4, -50.00, NULL, 'teste-negativo-000000001', @t);
CALL astro.transferir(3, 4, 2500.00, NULL, 'teste-limite-00000000001', @t);

SELECT 'T15 Diego (operador, alcada R$ 500) tenta R$ 600 da empresa (ESPERADO: ERRO 1644)' AS teste;
CALL astro_privado.lab_entrar_como('usuario', 5, JSON_ARRAY(5, 3));
CALL astro.transferir(5, 3, 600.00, NULL, 'teste-alcada-00000000001', @t);
SELECT 'T15b ...e ve a carteira da empresa, mas nao a da Ana (ESPERADO: OK, so carteira 5)' AS teste;
-- Sem escopo de operacao: o escopo assinado (carteiras_operacao) libera ler a
-- carteira de destino DURANTE a operacao, como no original.
CALL astro_privado.lab_entrar_como('usuario', 5, NULL);
SELECT id, titular_tipo, empresa_id FROM astro.carteiras;

-- ---------------------------------------------------------------- cadastro
SELECT 'T16 cadastro publico tentando criar ADMIN (ESPERADO: ERRO 1644)' AS teste;
CALL astro_privado.lab_entrar_como('publico', NULL, NULL);
INSERT INTO astro.usuarios (nome, email, senha_hash, papel)
VALUES (CONCAT('pii:v1:', SHA2('n', 256), ':', REPEAT('a', 120)), CONCAT('pii:v1:', SHA2('e1', 256), ':', REPEAT('a', 120)),
        '$argon2id$v=19$m=19456,t=2,p=1$x$y', 'ADMIN');

SELECT 'T17 cadastro publico criando carteira PARA OUTRA pessoa ou JA COM SALDO (ESPERADO: ERRO 1644)' AS teste;
INSERT INTO astro.carteiras (titular_tipo, usuario_id, numero) VALUES ('PF', 5, '99999999-1');
INSERT INTO astro.usuarios (nome, email, senha_hash)
VALUES (CONCAT('pii:v1:', SHA2('n', 256), ':', REPEAT('a', 120)), CONCAT('pii:v1:', SHA2('e2', 256), ':', REPEAT('a', 120)),
        '$argon2id$v=19$m=19456,t=2,p=1$x$y');
INSERT INTO astro.carteiras (titular_tipo, usuario_id, numero, saldo) VALUES ('PF', LAST_INSERT_ID(), '99999998-3', 1000000.00);

-- ---------------------------------------------------------------- integridade
SELECT 'T18 apagar ou alterar trilhas append-only (ESPERADO: ERRO 1142)' AS teste;
CALL astro_privado.lab_entrar_como('sistema', NULL, NULL);
DELETE FROM astro.historico_saldo;
UPDATE astro.historico_saldo SET saldo_novo = 0;
DELETE FROM astro.logs_auditoria;
TRUNCATE TABLE astro.logs_auditoria;
DELETE FROM astro.transacoes WHERE id = 1;

SELECT 'T19 CHECK constraints: saldo negativo, conservacao do dinheiro, CPF em claro (ESPERADO: ERRO 3819)' AS teste;
CALL astro_privado.lab_entrar_como('sistema', NULL, JSON_ARRAY(3));
UPDATE astro.carteiras SET saldo = -1 WHERE id = 3;
INSERT INTO astro.transacoes (origem_carteira_id, destino_carteira_id, tipo, valor_bruto, liquido, tipo_destino)
VALUES (3, 4, 'transferencia', 100.00, 150.00, 'PF');
INSERT INTO astro.usuarios (nome, cpf, email, senha_hash) VALUES ('Fulano', '52998224725', 'f@x.com', '$argon2id$x');

-- ---------------------------------------------------------------- SQL injection
SELECT 'T20 SQL injection: consulta MONTADA com texto (vulneravel) x PARAMETRIZADA (segura)' AS teste;
CALL astro_privado.lab_entrar_como('usuario', 2, NULL);
SET @entrada_do_atacante = "x' OR '1'='1";
-- ERRADO: o texto do atacante vira parte do SQL -> o OR '1'='1' devolve todos.
SET @sql_vulneravel = CONCAT("SELECT COUNT(*) AS vulneravel_retorna FROM astro.usuarios WHERE email_indice = '",
                             @entrada_do_atacante, "'");
PREPARE q FROM @sql_vulneravel; EXECUTE q; DEALLOCATE PREPARE q;
-- CERTO: o "?" recebe a entrada como VALOR; ela nunca é interpretada como SQL.
PREPARE q FROM 'SELECT COUNT(*) AS parametrizada_retorna FROM astro.usuarios WHERE email_indice = ?';
EXECUTE q USING @entrada_do_atacante; DEALLOCATE PREPARE q;

-- ---------------------------------------------------------------- validade
SELECT 'T21 contexto VENCIDO (espera 31 s) (ESPERADO: 0)' AS teste;
CALL astro_privado.lab_entrar_como('sistema', NULL, NULL);
SELECT COUNT(*) AS antes_de_vencer FROM astro.carteiras;
DO SLEEP(31);
SELECT COUNT(*) AS depois_de_vencer FROM astro.carteiras;

SELECT 'FIM dos testes da conta da API' AS teste;
