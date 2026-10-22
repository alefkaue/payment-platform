-- =============================================================================
-- 06_privilegios.sql  —  executar como ADMINISTRADOR (depois dos scripts 01–05)
-- =============================================================================
-- PRIVILÉGIO MÍNIMO (DCL): cada papel recebe só o que precisa, objeto por
-- objeto. Nada de GRANT ALL, nada em *.* (global), nada com GRANT OPTION.
--
-- astro_app (a API) — mesma lista do original (backend/app/db/permissoes.py),
-- só que nas VIEWS de `astro`. Nas tabelas reais (astro_dados) ela não tem nada:
--   SELECT + INSERT        nas 32
--   UPDATE                 nas que não são append-only
--   UPDATE (colunas)       em usuarios, carteiras e transacoes: só as colunas
--                          que a API altera (ex.: saldo, nunca o dono da carteira)
--   DELETE                 só chaves_pix e dpop_jtis
--   EXECUTE                só as 3 rotinas públicas
--   nenhum DDL (CREATE, DROP, ALTER, TRIGGER...) em lugar nenhum
-- =============================================================================

-- Append-only (8): ler e inserir.
GRANT SELECT, INSERT ON astro.historico_saldo       TO astro_app;
GRANT SELECT, INSERT ON astro.logs_auditoria        TO astro_app;
GRANT SELECT, INSERT ON astro.pontos_movimentos     TO astro_app;
GRANT SELECT, INSERT ON astro.creditos_tributarios  TO astro_app;
GRANT SELECT, INSERT ON astro.rendimentos           TO astro_app;
GRANT SELECT, INSERT ON astro.sessoes_mfa           TO astro_app;
GRANT SELECT, INSERT ON astro.documentos_identidade TO astro_app;
GRANT SELECT, INSERT ON astro.documentos_empresa    TO astro_app;

-- UPDATE só em colunas específicas (3).
GRANT SELECT, INSERT ON astro.usuarios TO astro_app;
GRANT UPDATE (senha_hash, embedding_facial_cifrado, kyc_status, ativo, pontos, totp_segredo, totp_passo_usado)
   ON astro.usuarios TO astro_app;
GRANT SELECT, INSERT ON astro.carteiras TO astro_app;
GRANT UPDATE (saldo, saldo_bloqueado) ON astro.carteiras TO astro_app;
GRANT SELECT, INSERT ON astro.transacoes TO astro_app;
GRANT UPDATE (status, bloqueio_ate) ON astro.transacoes TO astro_app;

-- Com exclusão física (2).
GRANT SELECT, INSERT, UPDATE, DELETE ON astro.chaves_pix TO astro_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON astro.dpop_jtis  TO astro_app;

-- Demais (19): ler, inserir, alterar.
GRANT SELECT, INSERT, UPDATE ON astro.empresas                 TO astro_app;
GRANT SELECT, INSERT, UPDATE ON astro.vinculos                 TO astro_app;
GRANT SELECT, INSERT, UPDATE ON astro.split_liquidacoes        TO astro_app;
GRANT SELECT, INSERT, UPDATE ON astro.repasses_tributo         TO astro_app;
GRANT SELECT, INSERT, UPDATE ON astro.cobrancas                TO astro_app;
GRANT SELECT, INSERT, UPDATE ON astro.autorizacoes_recorrentes TO astro_app;
GRANT SELECT, INSERT, UPDATE ON astro.operacoes_pendentes      TO astro_app;
GRANT SELECT, INSERT, UPDATE ON astro.contestacoes             TO astro_app;
GRANT SELECT, INSERT, UPDATE ON astro.limites                  TO astro_app;
GRANT SELECT, INSERT, UPDATE ON astro.dispositivos             TO astro_app;
GRANT SELECT, INSERT, UPDATE ON astro.desafios_biometria       TO astro_app;
GRANT SELECT, INSERT, UPDATE ON astro.refresh_tokens           TO astro_app;
GRANT SELECT, INSERT, UPDATE ON astro.kyc_casos                TO astro_app;
GRANT SELECT, INSERT, UPDATE ON astro.funcionarios             TO astro_app;
GRANT SELECT, INSERT, UPDATE ON astro.webhooks                 TO astro_app;
GRANT SELECT, INSERT, UPDATE ON astro.webhook_entregas         TO astro_app;
GRANT SELECT, INSERT, UPDATE ON astro.produtos                 TO astro_app;
GRANT SELECT, INSERT, UPDATE ON astro.voos                     TO astro_app;
GRANT SELECT, INSERT, UPDATE ON astro.cartoes                  TO astro_app;

-- Rotinas públicas.
GRANT EXECUTE ON FUNCTION  astro.astro_documento_usado TO astro_app;
GRANT EXECUTE ON PROCEDURE astro.astro_destinatario    TO astro_app;
GRANT EXECUTE ON PROCEDURE astro.transferir            TO astro_app;

-- -----------------------------------------------------------------------------
-- astro_auditor: lê a trilha e confere a corrente. Não lê dado de cliente e
-- não altera nada (nem a própria trilha).
-- -----------------------------------------------------------------------------
GRANT SELECT ON astro_auditoria.trilha TO astro_auditor;
GRANT EXECUTE ON PROCEDURE astro_auditoria.verificar_cadeia TO astro_auditor;
GRANT SELECT ON astro_relatorios.* TO astro_auditor;
GRANT EXECUTE ON PROCEDURE astro_relatorios.verificar_banco TO astro_auditor;

-- -----------------------------------------------------------------------------
-- astro_readonly: só relatórios agregados (sem CPF, nome, e-mail...). É o que
-- um colega de análise/BI pode usar sem ver dado pessoal de ninguém (LGPD).
-- -----------------------------------------------------------------------------
GRANT SELECT ON astro_relatorios.resumo_transacoes_dia TO astro_readonly;
GRANT SELECT ON astro_relatorios.resumo_carteiras      TO astro_readonly;
GRANT EXECUTE ON PROCEDURE astro_relatorios.verificar_banco TO astro_readonly;

-- -----------------------------------------------------------------------------
-- SÓ LABORATÓRIO: permite à conta da API assinar contexto pelo Workbench.
-- Em produção NÃO rode a linha abaixo (e o 99 apaga a rotina de qualquer jeito).
-- -----------------------------------------------------------------------------
GRANT EXECUTE ON PROCEDURE astro_privado.lab_entrar_como TO astro_app;

-- -----------------------------------------------------------------------------
-- Conferência: o que cada papel pode fazer.
-- -----------------------------------------------------------------------------
SHOW GRANTS FOR astro_app;
SHOW GRANTS FOR astro_auditor;
SHOW GRANTS FOR astro_readonly;
SHOW GRANTS FOR astro_migrator;
