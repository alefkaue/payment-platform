-- =============================================================================
-- 00_bootstrap_admin.sql  —  executar como ADMINISTRADOR do servidor
-- =============================================================================
-- QUEM RODA: root (laboratório local) ou o admin criado pela Azure (bootstrap).
-- QUANDO:    uma única vez, antes de todos os outros scripts.
--
-- POR QUE um script separado só para o admin?
--   O admin pode tudo. Se a aplicação ou as migrações usassem essa conta, um
--   SQL injection ou um vazamento de senha entregaria o servidor inteiro. Então
--   o admin só: (1) endurece o servidor, (2) cria os bancos, (3) cria papéis e
--   contas. Depois disso ninguém mais usa o admin no dia a dia.
--
-- SENHAS: nenhuma senha aparece neste arquivo. As contas são criadas com
--   IDENTIFIED BY RANDOM PASSWORD: o MySQL sorteia a senha e a mostra UMA vez no
--   resultado. Copie cada senha direto para o Azure Key Vault (ver
--   infra/README.md) e feche a aba. Não cole senha em arquivo, chat ou commit.
-- =============================================================================

-- -----------------------------------------------------------------------------
-- PARTE A — Endurecimento do servidor  (SÓ NO LABORATÓRIO LOCAL)
-- -----------------------------------------------------------------------------
-- Na Azure o admin não tem SUPER: esses mesmos valores são aplicados como
-- "parâmetros do servidor" pelo Bicep (infra/main.bicep). Lá, pule a PARTE A.
--
-- SET PERSIST grava em mysqld-auto.cnf: o valor sobrevive a reinícios.

-- Usuários anônimos (''@...) aceitam login com QUALQUER nome. Removemos.
DROP USER IF EXISTS ''@'localhost', ''@'%';
-- O banco "test" vem aberto a todos em instalações antigas.
DROP DATABASE IF EXISTS test;

-- Política de senha forte. Execute o INSTALL só uma vez; se aparecer o erro
-- 3529 ("Cannot load component ... already exists"), ele já está instalado.
-- Na Azure o equivalente é: CALL mysql.az_install_validate_password_plugin();
INSTALL COMPONENT 'file://component_validate_password';
SET PERSIST validate_password.policy             = 'STRONG';  -- exige dicionário/variedade
SET PERSIST validate_password.length             = 14;
SET PERSIST validate_password.mixed_case_count   = 1;
SET PERSIST validate_password.number_count       = 1;
SET PERSIST validate_password.special_char_count = 1;
SET PERSIST validate_password.check_user_name    = ON;        -- senha não pode conter o login

-- Ciclo de vida de senha (padrão para contas sem cláusula própria).
SET PERSIST default_password_lifetime = 90;   -- dias
SET PERSIST password_history          = 5;    -- não repetir as 5 últimas
SET PERSIST password_reuse_interval   = 365;  -- nem as usadas no último ano

-- Só conexões cifradas, e só TLS 1.2/1.3 (1.0/1.1 têm ataques conhecidos).
SET PERSIST require_secure_transport = ON;
SET PERSIST tls_version = 'TLSv1.2,TLSv1.3';
ALTER INSTANCE RELOAD TLS;

-- LOAD DATA LOCAL permite ao servidor pedir arquivos do cliente: desligado.
SET PERSIST local_infile = OFF;
-- Papéis só ficam ativos quando definidos como DEFAULT ROLE da conta (sem
-- "ativar tudo" automaticamente — mesma ideia do NOINHERIT do PostgreSQL).
SET PERSIST activate_all_roles_on_login = OFF;
-- Permite REVOKE parcial de um GRANT global (ver SEGURANCA-BANCO-MYSQL.md §3.5).
SET PERSIST partial_revokes = ON;
-- Modo estrito: valor inválido vira ERRO, nunca é truncado em silêncio.
SET PERSIST sql_mode = 'STRICT_ALL_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION,ONLY_FULL_GROUP_BY';
-- Todas as datas em UTC (o PostgreSQL usava TIMESTAMPTZ; aqui DATETIME + UTC).
SET PERSIST time_zone = '+00:00';
-- Com binlog ligado, criar função/trigger sem SUPER exige isto. A Azure já
-- usa ON; ligamos aqui para o laboratório se comportar igual à nuvem.
SET PERSIST log_bin_trust_function_creators = ON;
-- Tempo de espera por lock (equivale ao lock_timeout de 5s do original).
SET PERSIST innodb_lock_wait_timeout = 5;

-- -----------------------------------------------------------------------------
-- PARTE B — Bancos (schemas)       (local E Azure)
-- -----------------------------------------------------------------------------
-- POR QUE cinco bancos? Separar é o que permite dar privilégio mínimo:
--   astro_dados      tabelas reais. NINGUÉM da aplicação tem acesso direto.
--   astro_privado    chave de contexto e funções de política (o "motor" do RLS).
--   astro_auditoria  trilha append-only com encadeamento de hash.
--   astro            o que a API enxerga: views com o MESMO nome das tabelas
--                    (o ORM continua funcionando) + procedures.
--   astro_relatorios agregados sem dado pessoal (papel somente leitura).
CREATE DATABASE IF NOT EXISTS astro_dados      CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
CREATE DATABASE IF NOT EXISTS astro_privado    CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
CREATE DATABASE IF NOT EXISTS astro_auditoria  CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
CREATE DATABASE IF NOT EXISTS astro            CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
CREATE DATABASE IF NOT EXISTS astro_relatorios CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

-- -----------------------------------------------------------------------------
-- PARTE C — Papéis (ROLES)
-- -----------------------------------------------------------------------------
-- Um papel é um "pacote de privilégios". As contas recebem papéis; os GRANTs
-- ficam nos papéis. Trocar uma pessoa = trocar a conta, sem refazer GRANTs.
-- Papel no MySQL é uma conta TRANCADA (não aceita login); o host '%' de um
-- papel não abre acesso nenhum, porque ninguém consegue logar nele.
CREATE ROLE IF NOT EXISTS astro_app, astro_migrator, astro_auditor, astro_readonly;

-- O migrador cria e altera estrutura (DDL) nos bancos do Astro, e só neles.
-- Sem GRANT OPTION (não distribui privilégio), sem nada em *.* (global).
GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, DROP, ALTER, INDEX, REFERENCES,
      CREATE VIEW, SHOW VIEW, CREATE ROUTINE, ALTER ROUTINE, EXECUTE, TRIGGER
   ON astro_dados.* TO astro_migrator;
GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, DROP, ALTER, INDEX, REFERENCES,
      CREATE VIEW, SHOW VIEW, CREATE ROUTINE, ALTER ROUTINE, EXECUTE, TRIGGER
   ON astro_privado.* TO astro_migrator;
GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, DROP, ALTER, INDEX, REFERENCES,
      CREATE VIEW, SHOW VIEW, CREATE ROUTINE, ALTER ROUTINE, EXECUTE, TRIGGER
   ON astro_auditoria.* TO astro_migrator;
GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, DROP, ALTER, INDEX, REFERENCES,
      CREATE VIEW, SHOW VIEW, CREATE ROUTINE, ALTER ROUTINE, EXECUTE, TRIGGER
   ON astro.* TO astro_migrator;
GRANT SELECT, CREATE VIEW, SHOW VIEW, DROP, CREATE ROUTINE, ALTER ROUTINE, EXECUTE
   ON astro_relatorios.* TO astro_migrator;
-- astro_app, astro_auditor e astro_readonly recebem privilégios no script 05,
-- porque um GRANT em view só funciona depois que a view existe.

-- -----------------------------------------------------------------------------
-- PARTE D — Contas
-- -----------------------------------------------------------------------------
-- Ajuste os hosts ANTES de rodar. Nunca use '%' sozinho em conta de login:
--   laboratório:  'localhost'
--   Azure:        a sub-rede da aplicação, ex. '10.40.2.%' (o curinga fica
--                 preso à sub-rede privada, que nem tem acesso pela internet).
SET @host_app    = 'localhost';   -- de onde a API conecta
SET @host_admin  = 'localhost';   -- de onde migrador/auditor conectam (jump box)

-- Conta da API.
--   REQUIRE SSL              recusa conexão sem TLS, mesmo se o servidor mudar
--   MAX_USER_CONNECTIONS 30  = CONNECTION LIMIT 30 do original
--   FAILED_LOGIN_ATTEMPTS    10 erros seguidos travam por 1 dia (força bruta).
--                            Para a API usamos 10 (e não 3) porque o banco não
--                            é acessível de fora e um bloqueio derruba o app.
--   PASSWORD EXPIRE 180 DAY  rotação obrigatória (Key Vault avisa antes)
SET @sql = CONCAT(
  'CREATE USER IF NOT EXISTS ''svc_astro_api''@''', @host_app, '''',
  ' IDENTIFIED WITH caching_sha2_password BY RANDOM PASSWORD',
  ' REQUIRE SSL',
  ' WITH MAX_USER_CONNECTIONS 30',
  ' PASSWORD EXPIRE INTERVAL 180 DAY PASSWORD HISTORY 5 PASSWORD REUSE INTERVAL 365 DAY',
  ' FAILED_LOGIN_ATTEMPTS 10 PASSWORD_LOCK_TIME 1');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

-- Conta de migração: só é DESTRAVADA durante uma janela de migração.
-- O script 05 a trava (ACCOUNT LOCK) ao final.
SET @sql = CONCAT(
  'CREATE USER IF NOT EXISTS ''svc_astro_migrator''@''', @host_admin, '''',
  ' IDENTIFIED WITH caching_sha2_password BY RANDOM PASSWORD',
  ' REQUIRE SSL WITH MAX_USER_CONNECTIONS 2',
  ' PASSWORD EXPIRE INTERVAL 90 DAY PASSWORD HISTORY 5 PASSWORD REUSE INTERVAL 365 DAY',
  ' FAILED_LOGIN_ATTEMPTS 5 PASSWORD_LOCK_TIME 1');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

-- Contas de PESSOAS (exemplo). Na Azure, prefira contas Microsoft Entra
-- (CREATE AADUSER, ver infra/README.md): sem senha local, com MFA e
-- desativação central quando a pessoa sai da equipe.
--   PASSWORD REQUIRE CURRENT  trocar a senha exige saber a atual
SET @sql = CONCAT(
  'CREATE USER IF NOT EXISTS ''auditor_astro''@''', @host_admin, '''',
  ' IDENTIFIED WITH caching_sha2_password BY RANDOM PASSWORD',
  ' REQUIRE SSL WITH MAX_USER_CONNECTIONS 3',
  ' PASSWORD EXPIRE INTERVAL 90 DAY PASSWORD HISTORY 5 PASSWORD REUSE INTERVAL 365 DAY',
  ' PASSWORD REQUIRE CURRENT FAILED_LOGIN_ATTEMPTS 5 PASSWORD_LOCK_TIME 1');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

SET @sql = CONCAT(
  'CREATE USER IF NOT EXISTS ''leitura_astro''@''', @host_admin, '''',
  ' IDENTIFIED WITH caching_sha2_password BY RANDOM PASSWORD',
  ' REQUIRE SSL WITH MAX_USER_CONNECTIONS 3',
  ' PASSWORD EXPIRE INTERVAL 90 DAY PASSWORD HISTORY 5 PASSWORD REUSE INTERVAL 365 DAY',
  ' PASSWORD REQUIRE CURRENT FAILED_LOGIN_ATTEMPTS 5 PASSWORD_LOCK_TIME 1');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

-- Cada conta recebe UM papel, e ele é o papel padrão (ativo no login).
SET @sql = CONCAT('GRANT astro_app TO ''svc_astro_api''@''', @host_app, '''');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;
SET @sql = CONCAT('SET DEFAULT ROLE astro_app TO ''svc_astro_api''@''', @host_app, '''');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

SET @sql = CONCAT('GRANT astro_migrator TO ''svc_astro_migrator''@''', @host_admin, '''');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;
SET @sql = CONCAT('SET DEFAULT ROLE astro_migrator TO ''svc_astro_migrator''@''', @host_admin, '''');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

SET @sql = CONCAT('GRANT astro_auditor TO ''auditor_astro''@''', @host_admin, '''');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;
SET @sql = CONCAT('SET DEFAULT ROLE astro_auditor TO ''auditor_astro''@''', @host_admin, '''');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

SET @sql = CONCAT('GRANT astro_readonly TO ''leitura_astro''@''', @host_admin, '''');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;
SET @sql = CONCAT('SET DEFAULT ROLE astro_readonly TO ''leitura_astro''@''', @host_admin, '''');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

-- Conferência: nenhuma conta de login com host '%', nenhuma sem TLS.
SELECT user, host, ssl_type, account_locked, password_lifetime,
       JSON_EXTRACT(user_attributes, '$.Password_locking') AS bloqueio_por_erro
  FROM mysql.user
 WHERE user IN ('svc_astro_api','svc_astro_migrator','auditor_astro','leitura_astro')
 ORDER BY user;
