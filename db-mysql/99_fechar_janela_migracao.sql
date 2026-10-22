-- =============================================================================
-- 99_fechar_janela_migracao.sql  —  executar como ADMINISTRADOR
-- =============================================================================
-- Fecha a "janela de migração": depois que a estrutura está pronta, a conta que
-- pode fazer DDL fica TRANCADA. Se a senha dela vazar, não serve para nada até
-- alguém (com o admin, e com registro no audit log da Azure) destrancar.
-- Views, procedures e triggers continuam funcionando: o dono deles ser uma
-- conta trancada não impede a execução (trancar só bloqueia o LOGIN).
--
-- Para a próxima migração:  ALTER USER 'svc_astro_migrator'@'<host>' ACCOUNT UNLOCK;
-- =============================================================================

SET @host_admin = 'localhost';   -- o mesmo valor usado no 00

-- Remove as rotinas de LABORATÓRIO (assinatura de contexto pelo Workbench e
-- envelopes falsos). Em produção elas nem devem existir; aqui garantimos.
DROP PROCEDURE IF EXISTS astro_privado.lab_entrar_como;
DROP FUNCTION  IF EXISTS astro_privado.lab_envelope;

SET @sql = CONCAT('ALTER USER ''svc_astro_migrator''@''', @host_admin, ''' ACCOUNT LOCK');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

SELECT user, host, account_locked FROM mysql.user WHERE user LIKE 'svc_astro%';
