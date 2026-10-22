-- =============================================================================
-- 01_ddl_tabelas.sql  —  executar como svc_astro_migrator
-- =============================================================================
-- As 32 tabelas do Astro (backend/app/db/models.py, v7 + migrações até
-- f41b26ce0133), convertidas de PostgreSQL 16 para MySQL 8.
--
-- DECISÕES DE TIPO (o PORQUÊ está em SEGURANCA-BANCO-MYSQL.md §2):
--   ENGINE=InnoDB          único motor do MySQL com FK, transação e lock de linha.
--   utf8mb4                UTF-8 completo (o "utf8" antigo do MySQL não guarda emoji
--                          — e produtos.emoji existe).
--   id INT AUTO_INCREMENT  igual ao `integer` + sequência do original; o ORM espera int.
--   DECIMAL(14,2)          dinheiro exato. FLOAT/DOUBLE erram centavos (0.1+0.2).
--   DATETIME(6) em UTC     substitui TIMESTAMPTZ; o servidor roda em time_zone +00:00.
--   ENUM(...)              só onde o models.py usa Enum do SQLAlchemy (o ORM cria ENUM
--                          nativo no MySQL e grava o NOME do membro: 'PF', 'ADMIN'...).
--   VARCHAR + CHECK        nos "status" que o models.py guarda como texto.
--   TEXT ascii_bin         colunas CIFRADAS pela aplicação (envelope "pii:v1:...").
--                          ascii_bin = comparação byte a byte, sensível a maiúsculas.
--   *_indice               HMAC do valor em claro, gerado a partir do envelope: é por
--                          ele que se busca CPF/e-mail/chave Pix sem decifrar nada.
--   utf8mb4_bin            em chaves de idempotência/txid: no MySQL o padrão é
--                          INSENSÍVEL a maiúsculas ('Abc' = 'abc'); no PostgreSQL não.
--                          Sem _bin, uma UNIQUE mudaria de comportamento.
--
-- Nomes de constraint seguem o original (ck_..., uq_..., ix_...) para facilitar a
-- comparação. No MySQL o nome de CHECK/FK é único por BANCO, não por tabela.
-- =============================================================================

USE astro_dados;

-- -----------------------------------------------------------------------------
-- Pessoas, empresas e vínculos
-- -----------------------------------------------------------------------------

CREATE TABLE usuarios (
  id                        INT          NOT NULL AUTO_INCREMENT,
  nome                      TEXT CHARACTER SET ascii COLLATE ascii_bin NOT NULL,  -- cifrado
  cpf                       TEXT CHARACTER SET ascii COLLATE ascii_bin NULL,      -- cifrado (nulo só p/ admin)
  cpf_indice                CHAR(64) CHARACTER SET ascii COLLATE ascii_bin
                            GENERATED ALWAYS AS (CASE WHEN SUBSTR(cpf,1,7)='pii:v1:' THEN SUBSTR(cpf,8,64) END) STORED,
  email                     TEXT CHARACTER SET ascii COLLATE ascii_bin NOT NULL,  -- cifrado
  email_indice              CHAR(64) CHARACTER SET ascii COLLATE ascii_bin
                            GENERATED ALWAYS AS (CASE WHEN SUBSTR(email,1,7)='pii:v1:' THEN SUBSTR(email,8,64) END) STORED,
  senha_hash                VARCHAR(255) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,  -- bcrypt/argon2, nunca a senha
  papel                     ENUM('USUARIO','ADMIN') NOT NULL DEFAULT 'USUARIO',
  embedding_facial_cifrado  BLOB NULL,                                            -- Fernet (EMBEDDING_KEY)
  data_nascimento           TEXT CHARACTER SET ascii COLLATE ascii_bin NULL,      -- cifrado
  celular                   TEXT CHARACTER SET ascii COLLATE ascii_bin NULL,      -- cifrado
  kyc_status                VARCHAR(12)  NOT NULL DEFAULT 'pendente',
  ativo                     BOOLEAN      NOT NULL DEFAULT TRUE,
  pontos                    INT          NOT NULL DEFAULT 0,
  -- MAIS SEGURO que o original: no PostgreSQL o segredo TOTP ficava em texto puro.
  -- Aqui só aceita envelope cifrado (a aplicação precisa incluir o campo em CAMPOS).
  totp_segredo              TEXT CHARACTER SET ascii COLLATE ascii_bin NULL,
  totp_passo_usado          INT          NULL,
  criado_em                 DATETIME(6)  NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  UNIQUE KEY usuarios_cpf_key (cpf_indice),
  UNIQUE KEY ix_usuarios_email (email_indice),
  CONSTRAINT ck_usuario_pontos CHECK (pontos >= 0),
  CONSTRAINT ck_usuario_kyc    CHECK (kyc_status IN ('pendente','em_analise','aprovado','reprovado')),
  CONSTRAINT ck_pii_usuarios_nome  CHECK (nome  IS NULL OR (SUBSTR(nome,1,7)='pii:v1:'  AND SUBSTR(nome,72,1)=':'  AND CHAR_LENGTH(nome)>170)),
  CONSTRAINT ck_pii_usuarios_cpf   CHECK (cpf   IS NULL OR (SUBSTR(cpf,1,7)='pii:v1:'   AND SUBSTR(cpf,72,1)=':'   AND CHAR_LENGTH(cpf)>170)),
  CONSTRAINT ck_pii_usuarios_email CHECK (email IS NULL OR (SUBSTR(email,1,7)='pii:v1:' AND SUBSTR(email,72,1)=':' AND CHAR_LENGTH(email)>170)),
  CONSTRAINT ck_pii_usuarios_celular CHECK (celular IS NULL OR (SUBSTR(celular,1,7)='pii:v1:' AND SUBSTR(celular,72,1)=':' AND CHAR_LENGTH(celular)>170)),
  CONSTRAINT ck_pii_usuarios_data_nascimento CHECK (data_nascimento IS NULL OR (SUBSTR(data_nascimento,1,7)='pii:v1:' AND SUBSTR(data_nascimento,72,1)=':' AND CHAR_LENGTH(data_nascimento)>170)),
  CONSTRAINT ck_pii_usuarios_totp_segredo CHECK (totp_segredo IS NULL OR (SUBSTR(totp_segredo,1,7)='pii:v1:' AND SUBSTR(totp_segredo,72,1)=':' AND CHAR_LENGTH(totp_segredo)>170)),
  -- MAIS SEGURO: hash de senha precisa ter cara de hash (bcrypt $2..$ ou argon2 $argon2..).
  CONSTRAINT ck_usuario_senha_hash CHECK (senha_hash LIKE '$2%' OR senha_hash LIKE '$argon2%' OR senha_hash LIKE 'pbkdf2%')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE empresas (
  id                        INT          NOT NULL AUTO_INCREMENT,
  cnpj                      TEXT CHARACTER SET ascii COLLATE ascii_bin NOT NULL,  -- cifrado
  cnpj_indice               CHAR(64) CHARACTER SET ascii COLLATE ascii_bin
                            GENERATED ALWAYS AS (CASE WHEN SUBSTR(cnpj,1,7)='pii:v1:' THEN SUBSTR(cnpj,8,64) END) STORED,
  razao_social              TEXT CHARACTER SET ascii COLLATE ascii_bin NOT NULL,  -- cifrado
  nome_fantasia             TEXT CHARACTER SET ascii COLLATE ascii_bin NULL,      -- cifrado
  porte                     VARCHAR(10)  NOT NULL DEFAULT 'PME',
  regime_apuracao           ENUM('REGULAR','SIMPLES','MEI') NOT NULL DEFAULT 'REGULAR',
  cnae                      VARCHAR(10)  NULL,
  setor                     VARCHAR(80)  NULL,
  situacao_cadastral        VARCHAR(30)  NULL,
  verificada_em             DATETIME(6)  NULL,
  verificada_por            VARCHAR(20)  NULL,
  representante_usuario_id  INT          NULL,
  kyb_status                VARCHAR(12)  NOT NULL DEFAULT 'pendente',
  criado_em                 DATETIME(6)  NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  UNIQUE KEY empresas_cnpj_key (cnpj_indice),
  CONSTRAINT fk_empresa_representante FOREIGN KEY (representante_usuario_id) REFERENCES usuarios (id),
  CONSTRAINT ck_empresa_porte CHECK (porte IN ('MEI','PME','GRANDE')),
  CONSTRAINT ck_empresa_kyb   CHECK (kyb_status IN ('pendente','em_analise','aprovado','reprovado')),
  CONSTRAINT ck_pii_empresas_cnpj CHECK (cnpj IS NULL OR (SUBSTR(cnpj,1,7)='pii:v1:' AND SUBSTR(cnpj,72,1)=':' AND CHAR_LENGTH(cnpj)>170)),
  CONSTRAINT ck_pii_empresas_razao_social CHECK (razao_social IS NULL OR (SUBSTR(razao_social,1,7)='pii:v1:' AND SUBSTR(razao_social,72,1)=':' AND CHAR_LENGTH(razao_social)>170)),
  CONSTRAINT ck_pii_empresas_nome_fantasia CHECK (nome_fantasia IS NULL OR (SUBSTR(nome_fantasia,1,7)='pii:v1:' AND SUBSTR(nome_fantasia,72,1)=':' AND CHAR_LENGTH(nome_fantasia)>170))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE vinculos (
  id                        INT          NOT NULL AUTO_INCREMENT,
  usuario_id                INT          NULL,      -- nulo enquanto o convite não é aceito
  empresa_id                INT          NOT NULL,
  cpf                       TEXT CHARACTER SET ascii COLLATE ascii_bin NULL,      -- cifrado
  cpf_indice                CHAR(64) CHARACTER SET ascii COLLATE ascii_bin
                            GENERATED ALWAYS AS (CASE WHEN SUBSTR(cpf,1,7)='pii:v1:' THEN SUBSTR(cpf,8,64) END) STORED,
  nome                      TEXT CHARACTER SET ascii COLLATE ascii_bin NULL,      -- cifrado
  email                     TEXT CHARACTER SET ascii COLLATE ascii_bin NULL,      -- cifrado
  celular                   TEXT CHARACTER SET ascii COLLATE ascii_bin NULL,      -- cifrado
  cargo                     VARCHAR(80)  NULL,
  papel                     ENUM('ADMIN','APROVADOR','OPERADOR','CONSULTA') NOT NULL,
  alcada                    DECIMAL(14,2) NULL,
  alcada_diaria             DECIMAL(14,2) NULL,
  status                    VARCHAR(12)  NOT NULL DEFAULT 'ativo',
  ativo                     BOOLEAN      NOT NULL DEFAULT TRUE,
  criado_por_usuario_id     INT          NULL,
  aceito_em                 DATETIME(6)  NULL,
  status_em                 DATETIME(6)  NULL,
  ultimo_acesso_em          DATETIME(6)  NULL,
  criado_em                 DATETIME(6)  NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  UNIQUE KEY uq_vinculo_usuario_empresa (usuario_id, empresa_id),
  UNIQUE KEY uq_vinculo_empresa_cpf (empresa_id, cpf_indice),
  KEY ix_vinculos_usuario_id (usuario_id),
  KEY ix_vinculos_empresa_id (empresa_id),
  KEY ix_vinculos_cpf (cpf_indice),
  CONSTRAINT fk_vinculo_usuario    FOREIGN KEY (usuario_id) REFERENCES usuarios (id),
  CONSTRAINT fk_vinculo_empresa    FOREIGN KEY (empresa_id) REFERENCES empresas (id),
  CONSTRAINT fk_vinculo_criado_por FOREIGN KEY (criado_por_usuario_id) REFERENCES usuarios (id),
  CONSTRAINT ck_vinculo_alcada        CHECK (alcada IS NULL OR alcada >= 0),
  CONSTRAINT ck_vinculo_alcada_diaria CHECK (alcada_diaria IS NULL OR alcada_diaria >= 0),
  CONSTRAINT ck_vinculo_status  CHECK (status IN ('pendente','aguardando','ativo','suspenso','revogado','recusado')),
  CONSTRAINT ck_vinculo_ativo   CHECK (ativo = (status = 'ativo')),
  CONSTRAINT ck_vinculo_titular CHECK (status <> 'ativo' OR usuario_id IS NOT NULL),
  CONSTRAINT ck_pii_vinculos_cpf CHECK (cpf IS NULL OR (SUBSTR(cpf,1,7)='pii:v1:' AND SUBSTR(cpf,72,1)=':' AND CHAR_LENGTH(cpf)>170)),
  CONSTRAINT ck_pii_vinculos_nome CHECK (nome IS NULL OR (SUBSTR(nome,1,7)='pii:v1:' AND SUBSTR(nome,72,1)=':' AND CHAR_LENGTH(nome)>170)),
  CONSTRAINT ck_pii_vinculos_email CHECK (email IS NULL OR (SUBSTR(email,1,7)='pii:v1:' AND SUBSTR(email,72,1)=':' AND CHAR_LENGTH(email)>170)),
  CONSTRAINT ck_pii_vinculos_celular CHECK (celular IS NULL OR (SUBSTR(celular,1,7)='pii:v1:' AND SUBSTR(celular,72,1)=':' AND CHAR_LENGTH(celular)>170))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- -----------------------------------------------------------------------------
-- Dispositivos (vem antes de transacoes, que aponta para ela)
-- -----------------------------------------------------------------------------

CREATE TABLE dispositivos (
  id            INT          NOT NULL AUTO_INCREMENT,
  usuario_id    INT          NOT NULL,
  id_hash       CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,  -- SHA-256 do id do aparelho
  nome          VARCHAR(80)  NULL,
  confiavel     BOOLEAN      NOT NULL DEFAULT FALSE,
  confiavel_em  DATETIME(6)  NULL,
  bloqueado     BOOLEAN      NOT NULL DEFAULT FALSE,
  bloqueado_em  DATETIME(6)  NULL,
  removido      BOOLEAN      NOT NULL DEFAULT FALSE,
  ultimo_uso    DATETIME(6)  NULL,
  atestacao     VARCHAR(12)  NULL,
  atestacao_em  DATETIME(6)  NULL,
  criado_em     DATETIME(6)  NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  UNIQUE KEY uq_dispositivo_usuario (usuario_id, id_hash),
  KEY ix_dispositivos_usuario_id (usuario_id),
  CONSTRAINT fk_dispositivo_usuario FOREIGN KEY (usuario_id) REFERENCES usuarios (id),
  CONSTRAINT ck_dispositivo_id_hash CHECK (id_hash REGEXP '^[0-9a-f]{64}$')   -- MAIS SEGURO
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- -----------------------------------------------------------------------------
-- Carteiras e movimentação
-- -----------------------------------------------------------------------------

CREATE TABLE carteiras (
  id               INT           NOT NULL AUTO_INCREMENT,
  titular_tipo     ENUM('PF','PJ','SISTEMA') NOT NULL,
  usuario_id       INT           NULL,
  empresa_id       INT           NULL,
  sistema          VARCHAR(20)   NULL,          -- CAIXA | TRIBUTOS | FISCO
  agencia          VARCHAR(4)    NOT NULL DEFAULT '0001',
  numero           VARCHAR(12)   NOT NULL,      -- gerado pelo banco, com dígito
  saldo            DECIMAL(14,2) NOT NULL DEFAULT 0,
  saldo_bloqueado  DECIMAL(14,2) NOT NULL DEFAULT 0,
  criado_em        DATETIME(6)   NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  UNIQUE KEY carteiras_sistema_key (sistema),
  UNIQUE KEY ix_carteiras_numero (numero),
  UNIQUE KEY uq_carteira_usuario (usuario_id),   -- uma carteira por pessoa
  UNIQUE KEY uq_carteira_empresa (empresa_id),   -- uma carteira por empresa
  CONSTRAINT fk_carteira_usuario FOREIGN KEY (usuario_id) REFERENCES usuarios (id),
  CONSTRAINT fk_carteira_empresa FOREIGN KEY (empresa_id) REFERENCES empresas (id),
  -- Titular explícito: PF tem só usuario_id; PJ só empresa_id; SISTEMA só "sistema".
  CONSTRAINT ck_carteira_titular CHECK (
       (titular_tipo = 'PF'      AND usuario_id IS NOT NULL AND empresa_id IS NULL AND sistema IS NULL)
    OR (titular_tipo = 'PJ'      AND empresa_id IS NOT NULL AND usuario_id IS NULL AND sistema IS NULL)
    OR (titular_tipo = 'SISTEMA' AND usuario_id IS NULL AND empresa_id IS NULL AND sistema IN ('CAIXA','TRIBUTOS','FISCO'))),
  -- Saldo negativo só na conta de liquidação CAIXA (ela emite depósitos).
  CONSTRAINT ck_carteira_saldo     CHECK (saldo >= 0 OR (titular_tipo = 'SISTEMA' AND sistema = 'CAIXA')),
  CONSTRAINT ck_carteira_bloqueado CHECK (saldo_bloqueado >= 0),
  CONSTRAINT ck_carteira_numero    CHECK (numero REGEXP '^[0-9]{6,10}-[0-9]$' AND agencia REGEXP '^[0-9]{4}$')  -- MAIS SEGURO
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE autorizacoes_recorrentes (
  id                     INT           NOT NULL AUTO_INCREMENT,
  recebedor_carteira_id  INT           NOT NULL,
  pagador_carteira_id    INT           NOT NULL,
  descricao              TEXT CHARACTER SET ascii COLLATE ascii_bin NOT NULL,  -- cifrado
  valor_maximo           DECIMAL(14,2) NOT NULL,
  periodicidade          VARCHAR(10)   NOT NULL,
  status                 VARCHAR(10)   NOT NULL DEFAULT 'pendente',
  aceita_em              DATETIME(6)   NULL,
  cancelada_em           DATETIME(6)   NULL,
  criado_em              DATETIME(6)   NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  KEY ix_autorizacoes_recorrentes_recebedor_carteira_id (recebedor_carteira_id),
  KEY ix_autorizacoes_recorrentes_pagador_carteira_id (pagador_carteira_id),
  CONSTRAINT fk_autorizacao_recebedor FOREIGN KEY (recebedor_carteira_id) REFERENCES carteiras (id),
  CONSTRAINT fk_autorizacao_pagador   FOREIGN KEY (pagador_carteira_id)   REFERENCES carteiras (id),
  CONSTRAINT ck_autorizacao_valor   CHECK (valor_maximo > 0),
  CONSTRAINT ck_autorizacao_contas  CHECK (pagador_carteira_id <> recebedor_carteira_id),
  CONSTRAINT ck_autorizacao_periodo CHECK (periodicidade IN ('semanal','mensal','anual')),
  CONSTRAINT ck_autorizacao_status  CHECK (status IN ('pendente','ativa','cancelada','recusada')),
  CONSTRAINT ck_pii_autorizacoes_recorrentes_descricao CHECK (descricao IS NULL OR (SUBSTR(descricao,1,7)='pii:v1:' AND SUBSTR(descricao,72,1)=':' AND CHAR_LENGTH(descricao)>170))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE repasses_tributo (
  id         INT           NOT NULL AUTO_INCREMENT,
  cbs_total  DECIMAL(14,2) NOT NULL,
  ibs_total  DECIMAL(14,2) NOT NULL,
  corte      DATETIME(6)   NOT NULL,
  criado_em  DATETIME(6)   NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  CONSTRAINT ck_repasse_totais CHECK (cbs_total >= 0 AND ibs_total >= 0 AND cbs_total + ibs_total > 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE transacoes (
  id                     INT           NOT NULL AUTO_INCREMENT,
  origem_carteira_id     INT           NOT NULL,
  destino_carteira_id    INT           NOT NULL,
  tipo                   VARCHAR(20)   NOT NULL DEFAULT 'transferencia',
  valor_bruto            DECIMAL(14,2) NOT NULL,   -- o que a origem paga
  cbs                    DECIMAL(14,2) NOT NULL DEFAULT 0,
  ibs                    DECIMAL(14,2) NOT NULL DEFAULT 0,
  liquido                DECIMAL(14,2) NOT NULL,   -- o que o destino recebe
  tipo_destino           ENUM('PF','PJ','SISTEMA') NOT NULL,
  aplicou_split          BOOLEAN       NOT NULL DEFAULT FALSE,
  auth_metodo            ENUM('SENHA','SELFIE','APROVACAO','AUTOMATICO','SISTEMA') NOT NULL DEFAULT 'SENHA',
  status                 ENUM('CONCLUIDA','RETIDA','DEVOLVIDA','DEVOLVIDA_PARCIAL') NOT NULL DEFAULT 'CONCLUIDA',
  bloqueio_ate           DATETIME(6)   NULL,
  autor_usuario_id       INT           NULL,
  dispositivo_id         INT           NULL,
  descricao              TEXT CHARACTER SET ascii COLLATE ascii_bin NULL,  -- cifrado
  verificacao_facial     TEXT CHARACTER SET ascii COLLATE ascii_bin NULL,  -- cifrado (era JSONB)
  idempotency_key        VARCHAR(200)  CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NULL,
  transacao_original_id  INT           NULL,
  criado_em              DATETIME(6)   NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  UNIQUE KEY transacoes_idempotency_key_key (idempotency_key),  -- impede Pix duplicado
  KEY ix_transacoes_origem_carteira_id (origem_carteira_id),
  KEY ix_transacoes_destino_carteira_id (destino_carteira_id),
  KEY ix_transacoes_criado_em (criado_em),
  KEY ix_transacoes_origem_criado (origem_carteira_id, criado_em),
  KEY ix_transacoes_destino_criado (destino_carteira_id, criado_em),
  KEY ix_transacoes_status_bloqueio (status, bloqueio_ate),
  CONSTRAINT fk_transacao_origem      FOREIGN KEY (origem_carteira_id)    REFERENCES carteiras (id),
  CONSTRAINT fk_transacao_destino     FOREIGN KEY (destino_carteira_id)   REFERENCES carteiras (id),
  CONSTRAINT fk_transacao_autor       FOREIGN KEY (autor_usuario_id)      REFERENCES usuarios (id),
  CONSTRAINT fk_transacao_dispositivo FOREIGN KEY (dispositivo_id)        REFERENCES dispositivos (id),
  CONSTRAINT fk_transacao_original    FOREIGN KEY (transacao_original_id) REFERENCES transacoes (id),
  CONSTRAINT ck_transacao_valores CHECK (valor_bruto > 0 AND liquido >= 0 AND cbs >= 0 AND ibs >= 0),
  CONSTRAINT ck_transacao_contas  CHECK (origem_carteira_id <> destino_carteira_id),
  CONSTRAINT ck_transacao_tipo    CHECK (tipo IN ('transferencia','cobranca','deposito','rendimento','repasse_tributo','devolucao','estorno','resgate_pontos')),
  -- Conservação: dinheiro não aparece nem some. bruto = líquido + CBS + IBS.
  CONSTRAINT ck_transacao_conservacao CHECK (
       (tipo = 'repasse_tributo' AND NOT aplicou_split AND valor_bruto = liquido AND ROUND(valor_bruto,2) = ROUND(cbs + ibs,2))
    OR (tipo <> 'repasse_tributo' AND ROUND(valor_bruto,2) = ROUND(liquido + cbs + ibs,2) AND (aplicou_split OR (cbs = 0 AND ibs = 0)))),
  CONSTRAINT ck_transacao_split CHECK (NOT aplicou_split OR tipo IN ('cobranca','resgate_pontos')),
  CONSTRAINT ck_pii_transacoes_descricao CHECK (descricao IS NULL OR (SUBSTR(descricao,1,7)='pii:v1:' AND SUBSTR(descricao,72,1)=':' AND CHAR_LENGTH(descricao)>170)),
  CONSTRAINT ck_pii_transacoes_verificacao_facial CHECK (verificacao_facial IS NULL OR (SUBSTR(verificacao_facial,1,7)='pii:v1:' AND SUBSTR(verificacao_facial,72,1)=':' AND CHAR_LENGTH(verificacao_facial)>170))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- Ledger: toda mudança de saldo vira uma linha aqui (append-only, ver 04).
CREATE TABLE historico_saldo (
  id                  INT           NOT NULL AUTO_INCREMENT,
  carteira_id         INT           NOT NULL,
  saldo_anterior      DECIMAL(14,2) NOT NULL,
  saldo_novo          DECIMAL(14,2) NOT NULL,
  bloqueado_anterior  DECIMAL(14,2) NOT NULL DEFAULT 0,
  bloqueado_novo      DECIMAL(14,2) NOT NULL DEFAULT 0,
  motivo              VARCHAR(40)   NOT NULL DEFAULT 'transferencia',
  transacao_id        INT           NULL,
  criado_em           DATETIME(6)   NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  KEY ix_historico_saldo_carteira_id (carteira_id),
  KEY ix_historico_transacao (transacao_id),
  CONSTRAINT fk_historico_carteira  FOREIGN KEY (carteira_id)  REFERENCES carteiras (id),
  CONSTRAINT fk_historico_transacao FOREIGN KEY (transacao_id) REFERENCES transacoes (id),
  CONSTRAINT ck_historico_bloqueado CHECK (bloqueado_anterior >= 0 AND bloqueado_novo >= 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE split_liquidacoes (
  id                   INT           NOT NULL AUTO_INCREMENT,
  transacao_id         INT           NOT NULL,
  natureza             VARCHAR(20)   NOT NULL,      -- CBS | IBS | LIQUIDO
  carteira_destino_id  INT           NOT NULL,
  valor                DECIMAL(14,2) NOT NULL,
  repasse_id           INT           NULL,
  estornada            BOOLEAN       NOT NULL DEFAULT FALSE,
  criado_em            DATETIME(6)   NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  UNIQUE KEY uq_split_transacao_natureza (transacao_id, natureza),
  KEY ix_split_liquidacoes_transacao_id (transacao_id),
  KEY ix_split_liquidacoes_repasse_id (repasse_id),
  KEY ix_split_repasse_pendente (natureza, estornada, repasse_id, criado_em),
  CONSTRAINT fk_split_transacao FOREIGN KEY (transacao_id)        REFERENCES transacoes (id),
  CONSTRAINT fk_split_carteira  FOREIGN KEY (carteira_destino_id) REFERENCES carteiras (id),
  CONSTRAINT fk_split_repasse   FOREIGN KEY (repasse_id)          REFERENCES repasses_tributo (id),
  CONSTRAINT ck_split_valor    CHECK (valor >= 0),
  CONSTRAINT ck_split_natureza CHECK (natureza IN ('CBS','IBS','LIQUIDO')),
  CONSTRAINT ck_split_repasse  CHECK (NOT estornada OR repasse_id IS NULL)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE creditos_tributarios (
  id             INT           NOT NULL AUTO_INCREMENT,
  empresa_id     INT           NOT NULL,
  tributo        VARCHAR(4)    NOT NULL,
  valor          DECIMAL(14,2) NOT NULL,
  fonte          VARCHAR(20)   NOT NULL,
  referencia     VARCHAR(80)   NULL,
  consultado_em  DATETIME(6)   NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  KEY ix_creditos_tributarios_empresa_id (empresa_id),
  CONSTRAINT fk_credito_empresa FOREIGN KEY (empresa_id) REFERENCES empresas (id),
  CONSTRAINT ck_credito_valor   CHECK (valor >= 0),
  CONSTRAINT ck_credito_tributo CHECK (tributo IN ('CBS','IBS'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE cobrancas (
  id                     INT           NOT NULL AUTO_INCREMENT,
  txid                   VARCHAR(35)   CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  recebedor_carteira_id  INT           NOT NULL,
  valor                  DECIMAL(14,2) NOT NULL,
  descricao              TEXT CHARACTER SET ascii COLLATE ascii_bin NULL,  -- cifrado
  vencimento             DATE          NULL,
  pagador_documento      TEXT CHARACTER SET ascii COLLATE ascii_bin NULL,  -- cifrado
  nfe_chave              VARCHAR(44)   CHARACTER SET ascii COLLATE ascii_bin NULL,
  cbs                    DECIMAL(14,2) NOT NULL DEFAULT 0,
  ibs                    DECIMAL(14,2) NOT NULL DEFAULT 0,
  linha_digitavel        VARCHAR(60)   NOT NULL,
  status                 VARCHAR(12)   NOT NULL DEFAULT 'aberta',
  grupo_parcelamento     VARCHAR(35)   CHARACTER SET ascii COLLATE ascii_bin NULL,
  parcela_numero         INT           NOT NULL DEFAULT 1,
  parcelas_total         INT           NOT NULL DEFAULT 1,
  autorizacao_id         INT           NULL,
  transacao_id           INT           NULL,
  paga_em                DATETIME(6)   NULL,
  criado_por_usuario_id  INT           NULL,
  criado_em              DATETIME(6)   NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  UNIQUE KEY ix_cobrancas_txid (txid),
  UNIQUE KEY uq_cobranca_transacao (transacao_id),
  KEY ix_cobrancas_recebedor_carteira_id (recebedor_carteira_id),
  KEY ix_cobrancas_nfe_chave (nfe_chave),
  KEY ix_cobrancas_grupo_parcelamento (grupo_parcelamento),
  CONSTRAINT fk_cobranca_recebedor   FOREIGN KEY (recebedor_carteira_id) REFERENCES carteiras (id),
  CONSTRAINT fk_cobranca_autorizacao FOREIGN KEY (autorizacao_id)        REFERENCES autorizacoes_recorrentes (id),
  CONSTRAINT fk_cobranca_transacao   FOREIGN KEY (transacao_id)          REFERENCES transacoes (id),
  CONSTRAINT fk_cobranca_criado_por  FOREIGN KEY (criado_por_usuario_id) REFERENCES usuarios (id),
  CONSTRAINT ck_cobranca_valores   CHECK (valor > 0 AND cbs >= 0 AND ibs >= 0 AND cbs + ibs <= valor),
  CONSTRAINT ck_cobranca_nota      CHECK (nfe_chave IS NOT NULL OR (cbs = 0 AND ibs = 0)),
  CONSTRAINT ck_cobranca_parcelas  CHECK (parcela_numero >= 1 AND parcelas_total >= parcela_numero),
  CONSTRAINT ck_cobranca_status    CHECK (status IN ('aberta','paga','cancelada','estornada')),
  CONSTRAINT ck_cobranca_pagamento CHECK (status NOT IN ('paga','estornada') OR (transacao_id IS NOT NULL AND paga_em IS NOT NULL)),
  CONSTRAINT ck_cobranca_txid      CHECK (txid REGEXP '^[A-Za-z0-9]{26,35}$'),            -- MAIS SEGURO
  CONSTRAINT ck_cobranca_nfe       CHECK (nfe_chave IS NULL OR nfe_chave REGEXP '^[0-9]{44}$'),  -- MAIS SEGURO
  CONSTRAINT ck_pii_cobrancas_descricao CHECK (descricao IS NULL OR (SUBSTR(descricao,1,7)='pii:v1:' AND SUBSTR(descricao,72,1)=':' AND CHAR_LENGTH(descricao)>170)),
  CONSTRAINT ck_pii_cobrancas_pagador_documento CHECK (pagador_documento IS NULL OR (SUBSTR(pagador_documento,1,7)='pii:v1:' AND SUBSTR(pagador_documento,72,1)=':' AND CHAR_LENGTH(pagador_documento)>170))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE chaves_pix (
  id            INT          NOT NULL AUTO_INCREMENT,
  carteira_id   INT          NOT NULL,
  tipo          VARCHAR(10)  NOT NULL,
  valor         TEXT CHARACTER SET ascii COLLATE ascii_bin NOT NULL,  -- cifrado
  valor_indice  CHAR(64) CHARACTER SET ascii COLLATE ascii_bin
                GENERATED ALWAYS AS (CASE WHEN SUBSTR(valor,1,7)='pii:v1:' THEN SUBSTR(valor,8,64) END) STORED,
  criado_em     DATETIME(6)  NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  UNIQUE KEY uq_chave_tipo_valor (tipo, valor_indice),
  KEY ix_chaves_pix_carteira_id (carteira_id),
  KEY ix_chaves_pix_valor (valor_indice),
  CONSTRAINT fk_chave_carteira FOREIGN KEY (carteira_id) REFERENCES carteiras (id),
  CONSTRAINT ck_chave_tipo CHECK (tipo IN ('cpf','cnpj','email','celular','aleatoria')),
  CONSTRAINT ck_pii_chaves_pix_valor CHECK (valor IS NULL OR (SUBSTR(valor,1,7)='pii:v1:' AND SUBSTR(valor,72,1)=':' AND CHAR_LENGTH(valor)>170))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE operacoes_pendentes (
  id                       INT           NOT NULL AUTO_INCREMENT,
  empresa_id               INT           NOT NULL,
  tipo                     VARCHAR(20)   NOT NULL,
  valor                    DECIMAL(14,2) NOT NULL,
  payload                  TEXT CHARACTER SET ascii COLLATE ascii_bin NOT NULL,  -- cifrado (era JSONB)
  descricao                TEXT CHARACTER SET ascii COLLATE ascii_bin NULL,      -- cifrado
  aprovacoes_necessarias   INT           NOT NULL DEFAULT 1,
  aprovacoes               TEXT CHARACTER SET ascii COLLATE ascii_bin NULL,      -- cifrado (era JSONB)
  criado_por_usuario_id    INT           NOT NULL,
  status                   VARCHAR(10)   NOT NULL DEFAULT 'pendente',
  decidido_por_usuario_id  INT           NULL,
  decidido_em              DATETIME(6)   NULL,
  resultado                TEXT CHARACTER SET ascii COLLATE ascii_bin NULL,      -- cifrado (era JSONB)
  criado_em                DATETIME(6)   NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  idempotency_key          VARCHAR(140)  CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NULL,
  PRIMARY KEY (id),
  -- No PostgreSQL era um índice ÚNICO PARCIAL (WHERE idempotency_key IS NOT NULL).
  -- O MySQL não tem índice parcial, mas NULL nunca colide numa UNIQUE: mesmo efeito.
  UNIQUE KEY uq_pendente_empresa_chave (empresa_id, idempotency_key),
  KEY ix_operacoes_pendentes_empresa_id (empresa_id),
  CONSTRAINT fk_pendente_empresa    FOREIGN KEY (empresa_id)              REFERENCES empresas (id),
  CONSTRAINT fk_pendente_criado_por FOREIGN KEY (criado_por_usuario_id)   REFERENCES usuarios (id),
  CONSTRAINT fk_pendente_decidido   FOREIGN KEY (decidido_por_usuario_id) REFERENCES usuarios (id),
  CONSTRAINT ck_pendente_valor      CHECK (valor >= 0),
  CONSTRAINT ck_pendente_aprovacoes CHECK (aprovacoes_necessarias IN (1,2)),
  CONSTRAINT ck_pendente_status     CHECK (status IN ('pendente','aprovada','rejeitada','falhou','expirada','cancelada','executando')),
  -- MAIS SEGURO: quem decide não pode ser quem criou (maker-checker no próprio banco).
  CONSTRAINT ck_pendente_quatro_olhos CHECK (decidido_por_usuario_id IS NULL OR status IN ('rejeitada','cancelada','expirada') OR decidido_por_usuario_id <> criado_por_usuario_id),
  CONSTRAINT ck_pii_operacoes_pendentes_payload CHECK (payload IS NULL OR (SUBSTR(payload,1,7)='pii:v1:' AND SUBSTR(payload,72,1)=':' AND CHAR_LENGTH(payload)>170)),
  CONSTRAINT ck_pii_operacoes_pendentes_descricao CHECK (descricao IS NULL OR (SUBSTR(descricao,1,7)='pii:v1:' AND SUBSTR(descricao,72,1)=':' AND CHAR_LENGTH(descricao)>170)),
  CONSTRAINT ck_pii_operacoes_pendentes_aprovacoes CHECK (aprovacoes IS NULL OR (SUBSTR(aprovacoes,1,7)='pii:v1:' AND SUBSTR(aprovacoes,72,1)=':' AND CHAR_LENGTH(aprovacoes)>170)),
  CONSTRAINT ck_pii_operacoes_pendentes_resultado CHECK (resultado IS NULL OR (SUBSTR(resultado,1,7)='pii:v1:' AND SUBSTR(resultado,72,1)=':' AND CHAR_LENGTH(resultado)>170))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE contestacoes (
  id                     INT           NOT NULL AUTO_INCREMENT,
  transacao_id           INT           NOT NULL,
  aberta_por_usuario_id  INT           NOT NULL,
  motivo                 TEXT CHARACTER SET ascii COLLATE ascii_bin NOT NULL,  -- cifrado
  status                 VARCHAR(12)   NOT NULL DEFAULT 'aberta',
  valor_devolvido        DECIMAL(14,2) NOT NULL DEFAULT 0,
  decidida_em            DATETIME(6)   NULL,
  criado_em              DATETIME(6)   NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  UNIQUE KEY contestacoes_transacao_id_key (transacao_id),
  CONSTRAINT fk_contestacao_transacao FOREIGN KEY (transacao_id)          REFERENCES transacoes (id),
  CONSTRAINT fk_contestacao_usuario   FOREIGN KEY (aberta_por_usuario_id) REFERENCES usuarios (id),
  CONSTRAINT ck_contestacao_valor  CHECK (valor_devolvido >= 0),
  CONSTRAINT ck_contestacao_status CHECK (status IN ('aberta','procedente','improcedente')),
  CONSTRAINT ck_pii_contestacoes_motivo CHECK (motivo IS NULL OR (SUBSTR(motivo,1,7)='pii:v1:' AND SUBSTR(motivo,72,1)=':' AND CHAR_LENGTH(motivo)>170))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- -----------------------------------------------------------------------------
-- Segurança
-- -----------------------------------------------------------------------------

CREATE TABLE limites (
  id                      INT           NOT NULL AUTO_INCREMENT,
  carteira_id             INT           NOT NULL,
  por_transacao           DECIMAL(14,2) NOT NULL,
  diurno                  DECIMAL(14,2) NOT NULL,
  noturno                 DECIMAL(14,2) NOT NULL,
  pendente_por_transacao  DECIMAL(14,2) NULL,
  pendente_diurno         DECIMAL(14,2) NULL,
  pendente_noturno        DECIMAL(14,2) NULL,
  pendente_vigente_em     DATETIME(6)   NULL,
  atualizado_em           DATETIME(6)   NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  UNIQUE KEY limites_carteira_id_key (carteira_id),
  CONSTRAINT fk_limite_carteira FOREIGN KEY (carteira_id) REFERENCES carteiras (id),
  CONSTRAINT ck_limite_valores   CHECK (por_transacao >= 0 AND diurno >= 0 AND noturno >= 0),
  CONSTRAINT ck_limite_pendentes CHECK ((pendente_por_transacao IS NULL OR pendente_por_transacao >= 0)
                                    AND (pendente_diurno IS NULL OR pendente_diurno >= 0)
                                    AND (pendente_noturno IS NULL OR pendente_noturno >= 0))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE dpop_jtis (
  jti        VARCHAR(64)  CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  expira_em  DATETIME(6)  NOT NULL,
  PRIMARY KEY (jti),
  KEY ix_dpop_jtis_expira_em (expira_em)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE desafios_biometria (
  id          INT          NOT NULL AUTO_INCREMENT,
  publico_id  VARCHAR(40)  CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  acao        VARCHAR(80)  NOT NULL,
  usuario_id  INT          NULL,
  expira_em   DATETIME(6)  NOT NULL,
  usado       BOOLEAN      NOT NULL DEFAULT FALSE,
  criado_em   DATETIME(6)  NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  UNIQUE KEY ix_desafios_biometria_publico_id (publico_id),
  CONSTRAINT fk_desafio_usuario FOREIGN KEY (usuario_id) REFERENCES usuarios (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE refresh_tokens (
  id               INT          NOT NULL AUTO_INCREMENT,
  usuario_id       INT          NOT NULL,
  jti              VARCHAR(64)  CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  token_hash       CHAR(64)     CHARACTER SET ascii COLLATE ascii_bin NOT NULL,  -- só o SHA-256
  expira_em        DATETIME(6)  NOT NULL,
  revogado         BOOLEAN      NOT NULL DEFAULT FALSE,
  substituido_por  VARCHAR(64)  CHARACTER SET ascii COLLATE ascii_bin NULL,
  sessao_id        VARCHAR(40)  CHARACTER SET ascii COLLATE ascii_bin NULL,
  dispositivo_id   INT          NULL,
  ip               TEXT CHARACTER SET ascii COLLATE ascii_bin NULL,  -- cifrado
  user_agent       TEXT CHARACTER SET ascii COLLATE ascii_bin NULL,  -- cifrado
  criado_em        DATETIME(6)  NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  UNIQUE KEY ix_refresh_tokens_jti (jti),
  KEY ix_refresh_tokens_usuario_id (usuario_id),
  KEY ix_refresh_tokens_token_hash (token_hash),
  KEY ix_refresh_tokens_sessao_id (sessao_id),
  KEY ix_refresh_sessao_ativa (sessao_id, revogado, expira_em),
  CONSTRAINT fk_refresh_usuario     FOREIGN KEY (usuario_id)     REFERENCES usuarios (id),
  CONSTRAINT fk_refresh_dispositivo FOREIGN KEY (dispositivo_id) REFERENCES dispositivos (id),
  CONSTRAINT ck_refresh_token_hash  CHECK (token_hash REGEXP '^[0-9a-f]{64}$'),   -- MAIS SEGURO
  CONSTRAINT ck_pii_refresh_tokens_ip CHECK (ip IS NULL OR (SUBSTR(ip,1,7)='pii:v1:' AND SUBSTR(ip,72,1)=':' AND CHAR_LENGTH(ip)>170)),
  CONSTRAINT ck_pii_refresh_tokens_user_agent CHECK (user_agent IS NULL OR (SUBSTR(user_agent,1,7)='pii:v1:' AND SUBSTR(user_agent,72,1)=':' AND CHAR_LENGTH(user_agent)>170))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE sessoes_mfa (
  id                 INT          NOT NULL AUTO_INCREMENT,
  usuario_id         INT          NULL,
  referencia         TEXT CHARACTER SET ascii COLLATE ascii_bin NULL,  -- cifrado
  referencia_indice  CHAR(64) CHARACTER SET ascii COLLATE ascii_bin
                     GENERATED ALWAYS AS (CASE WHEN SUBSTR(referencia,1,7)='pii:v1:' THEN SUBSTR(referencia,8,64) END) STORED,
  reserva_id         INT          NULL,
  tipo               VARCHAR(40)  NOT NULL,
  sucesso            BOOLEAN      NOT NULL,
  ip                 TEXT CHARACTER SET ascii COLLATE ascii_bin NULL,  -- cifrado
  ip_indice          CHAR(64) CHARACTER SET ascii COLLATE ascii_bin
                     GENERATED ALWAYS AS (CASE WHEN SUBSTR(ip,1,7)='pii:v1:' THEN SUBSTR(ip,8,64) END) STORED,
  detalhe            TEXT CHARACTER SET ascii COLLATE ascii_bin NULL,  -- cifrado (era JSONB)
  criado_em          DATETIME(6)  NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  -- No PostgreSQL: índice único PARCIAL "WHERE tipo='mfa_usado' AND sucesso".
  -- No MySQL: uma coluna gerada que só tem valor nessa condição (NULL nas
  -- demais) + UNIQUE nela. Resultado igual: um MFA conclui um único login.
  mfa_usado_referencia CHAR(64) CHARACTER SET ascii COLLATE ascii_bin
                     GENERATED ALWAYS AS (CASE WHEN tipo = 'mfa_usado' AND sucesso THEN referencia_indice END) STORED,
  PRIMARY KEY (id),
  UNIQUE KEY uq_mfa_usado_referencia (mfa_usado_referencia),
  KEY ix_sessoes_mfa_referencia (referencia_indice),
  KEY ix_sessoes_mfa_ip (ip_indice),
  KEY ix_sessoes_mfa_reserva_id (reserva_id),
  KEY ix_sessoes_tipo_criado (tipo, criado_em),
  KEY ix_mfa_referencia_tipo_criado (referencia_indice, tipo, criado_em),
  KEY ix_mfa_ip_tipo_criado (ip_indice, tipo, criado_em),
  CONSTRAINT fk_mfa_usuario FOREIGN KEY (usuario_id) REFERENCES usuarios (id),
  CONSTRAINT fk_mfa_reserva FOREIGN KEY (reserva_id) REFERENCES sessoes_mfa (id),
  CONSTRAINT ck_pii_sessoes_mfa_referencia CHECK (referencia IS NULL OR (SUBSTR(referencia,1,7)='pii:v1:' AND SUBSTR(referencia,72,1)=':' AND CHAR_LENGTH(referencia)>170)),
  CONSTRAINT ck_pii_sessoes_mfa_ip CHECK (ip IS NULL OR (SUBSTR(ip,1,7)='pii:v1:' AND SUBSTR(ip,72,1)=':' AND CHAR_LENGTH(ip)>170)),
  CONSTRAINT ck_pii_sessoes_mfa_detalhe CHECK (detalhe IS NULL OR (SUBSTR(detalhe,1,7)='pii:v1:' AND SUBSTR(detalhe,72,1)=':' AND CHAR_LENGTH(detalhe)>170))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- Trilha de negócio gravada PELA APLICAÇÃO (append-only). A trilha técnica,
-- gravada por TRIGGER, fica em astro_auditoria.trilha (script 04).
CREATE TABLE logs_auditoria (
  id          INT          NOT NULL AUTO_INCREMENT,
  ator        TEXT CHARACTER SET ascii COLLATE ascii_bin NOT NULL,  -- cifrado
  acao        VARCHAR(80)  NOT NULL,
  usuario_id  INT          NULL,
  empresa_id  INT          NULL,
  ip          TEXT CHARACTER SET ascii COLLATE ascii_bin NULL,      -- cifrado
  detalhe     TEXT CHARACTER SET ascii COLLATE ascii_bin NULL,      -- cifrado (era JSONB)
  criado_em   DATETIME(6)  NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  KEY ix_logs_auditoria_usuario_id (usuario_id),
  KEY ix_logs_auditoria_empresa_id (empresa_id),
  KEY ix_logs_auditoria_criado_em (criado_em),
  CONSTRAINT fk_log_usuario FOREIGN KEY (usuario_id) REFERENCES usuarios (id),
  CONSTRAINT fk_log_empresa FOREIGN KEY (empresa_id) REFERENCES empresas (id),
  CONSTRAINT ck_pii_logs_auditoria_ator CHECK (ator IS NULL OR (SUBSTR(ator,1,7)='pii:v1:' AND SUBSTR(ator,72,1)=':' AND CHAR_LENGTH(ator)>170)),
  CONSTRAINT ck_pii_logs_auditoria_ip CHECK (ip IS NULL OR (SUBSTR(ip,1,7)='pii:v1:' AND SUBSTR(ip,72,1)=':' AND CHAR_LENGTH(ip)>170)),
  CONSTRAINT ck_pii_logs_auditoria_detalhe CHECK (detalhe IS NULL OR (SUBSTR(detalhe,1,7)='pii:v1:' AND SUBSTR(detalhe,72,1)=':' AND CHAR_LENGTH(detalhe)>170))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- -----------------------------------------------------------------------------
-- Identidade (KYC/KYB)
-- -----------------------------------------------------------------------------

CREATE TABLE kyc_casos (
  id            INT          NOT NULL AUTO_INCREMENT,
  usuario_id    INT          NULL,
  empresa_id    INT          NULL,
  tipo          VARCHAR(4)   NOT NULL,
  status        VARCHAR(12)  NOT NULL,
  nivel_risco   VARCHAR(8)   NOT NULL DEFAULT 'baixo',
  motivos       TEXT CHARACTER SET ascii COLLATE ascii_bin NULL,  -- cifrado (era JSONB)
  criado_em     DATETIME(6)  NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  concluido_em  DATETIME(6)  NULL,
  PRIMARY KEY (id),
  KEY ix_kyc_casos_usuario_id (usuario_id),
  KEY ix_kyc_casos_empresa_id (empresa_id),
  CONSTRAINT fk_kyc_usuario FOREIGN KEY (usuario_id) REFERENCES usuarios (id),
  CONSTRAINT fk_kyc_empresa FOREIGN KEY (empresa_id) REFERENCES empresas (id),
  CONSTRAINT ck_kyc_tipo   CHECK (tipo IN ('pf','pj')),
  CONSTRAINT ck_kyc_status CHECK (status IN ('aprovado','em_analise','reprovado')),
  CONSTRAINT ck_pii_kyc_casos_motivos CHECK (motivos IS NULL OR (SUBSTR(motivos,1,7)='pii:v1:' AND SUBSTR(motivos,72,1)=':' AND CHAR_LENGTH(motivos)>170))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- A IMAGEM do documento nunca é guardada (LGPD): só o SHA-256 e o que foi conferido.
CREATE TABLE documentos_identidade (
  id            INT           NOT NULL AUTO_INCREMENT,
  caso_id       INT           NOT NULL,
  tipo          VARCHAR(12)   NOT NULL,
  status        VARCHAR(12)   NOT NULL,
  provedor      VARCHAR(20)   NOT NULL,
  sha256        VARCHAR(140)  CHARACTER SET ascii COLLATE ascii_bin NOT NULL,  -- "frente" ou "frente:verso"
  campos        TEXT CHARACTER SET ascii COLLATE ascii_bin NULL,  -- cifrado
  verificacoes  TEXT CHARACTER SET ascii COLLATE ascii_bin NULL,  -- cifrado
  criado_em     DATETIME(6)   NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  KEY ix_documentos_identidade_caso_id (caso_id),
  KEY ix_documentos_identidade_sha256 (sha256),   -- novo: a checagem de duplicidade busca por ele
  CONSTRAINT fk_documento_caso FOREIGN KEY (caso_id) REFERENCES kyc_casos (id),
  CONSTRAINT ck_documento_sha256 CHECK (sha256 REGEXP '^[0-9a-f]{64}(:[0-9a-f]{64})?$'),  -- MAIS SEGURO
  CONSTRAINT ck_pii_documentos_identidade_campos CHECK (campos IS NULL OR (SUBSTR(campos,1,7)='pii:v1:' AND SUBSTR(campos,72,1)=':' AND CHAR_LENGTH(campos)>170)),
  CONSTRAINT ck_pii_documentos_identidade_verificacoes CHECK (verificacoes IS NULL OR (SUBSTR(verificacoes,1,7)='pii:v1:' AND SUBSTR(verificacoes,72,1)=':' AND CHAR_LENGTH(verificacoes)>170))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE documentos_empresa (
  id                      INT          NOT NULL AUTO_INCREMENT,
  empresa_id              INT          NOT NULL,
  tipo                    VARCHAR(20)  NOT NULL,
  mime                    VARCHAR(40)  NOT NULL,
  tamanho                 INT          NOT NULL,
  sha256                  CHAR(64)     CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  status                  VARCHAR(12)  NOT NULL,
  verificacoes            TEXT CHARACTER SET ascii COLLATE ascii_bin NULL,  -- cifrado
  enviado_por_usuario_id  INT          NULL,
  criado_em               DATETIME(6)  NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  KEY ix_documentos_empresa_empresa_id (empresa_id),
  CONSTRAINT fk_docempresa_empresa FOREIGN KEY (empresa_id)             REFERENCES empresas (id),
  CONSTRAINT fk_docempresa_usuario FOREIGN KEY (enviado_por_usuario_id) REFERENCES usuarios (id),
  CONSTRAINT ck_documento_tamanho CHECK (tamanho > 0),
  CONSTRAINT ck_docempresa_sha256 CHECK (sha256 REGEXP '^[0-9a-f]{64}$'),   -- MAIS SEGURO
  CONSTRAINT ck_pii_documentos_empresa_verificacoes CHECK (verificacoes IS NULL OR (SUBSTR(verificacoes,1,7)='pii:v1:' AND SUBSTR(verificacoes,72,1)=':' AND CHAR_LENGTH(verificacoes)>170))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE funcionarios (
  id                     INT           NOT NULL AUTO_INCREMENT,
  empresa_id             INT           NOT NULL,
  nome                   TEXT CHARACTER SET ascii COLLATE ascii_bin NOT NULL,  -- cifrado
  cpf                    TEXT CHARACTER SET ascii COLLATE ascii_bin NOT NULL,  -- cifrado
  cpf_indice             CHAR(64) CHARACTER SET ascii COLLATE ascii_bin
                         GENERATED ALWAYS AS (CASE WHEN SUBSTR(cpf,1,7)='pii:v1:' THEN SUBSTR(cpf,8,64) END) STORED,
  cargo                  VARCHAR(80)   NULL,
  salario                DECIMAL(14,2) NULL,
  ativo                  BOOLEAN       NOT NULL DEFAULT TRUE,
  criado_por_usuario_id  INT           NULL,
  criado_em              DATETIME(6)   NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  desligado_em           DATETIME(6)   NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uq_funcionario_empresa_cpf (empresa_id, cpf_indice),
  KEY ix_funcionarios_empresa_id (empresa_id),
  CONSTRAINT fk_funcionario_empresa    FOREIGN KEY (empresa_id)            REFERENCES empresas (id),
  CONSTRAINT fk_funcionario_criado_por FOREIGN KEY (criado_por_usuario_id) REFERENCES usuarios (id),
  CONSTRAINT ck_funcionario_salario CHECK (salario IS NULL OR salario > 0),
  CONSTRAINT ck_pii_funcionarios_nome CHECK (nome IS NULL OR (SUBSTR(nome,1,7)='pii:v1:' AND SUBSTR(nome,72,1)=':' AND CHAR_LENGTH(nome)>170)),
  CONSTRAINT ck_pii_funcionarios_cpf CHECK (cpf IS NULL OR (SUBSTR(cpf,1,7)='pii:v1:' AND SUBSTR(cpf,72,1)=':' AND CHAR_LENGTH(cpf)>170))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- -----------------------------------------------------------------------------
-- Integrações e produtos
-- -----------------------------------------------------------------------------

CREATE TABLE webhooks (
  id          INT           NOT NULL AUTO_INCREMENT,
  empresa_id  INT           NOT NULL,
  url         VARCHAR(300)  NOT NULL,
  segredo     VARCHAR(512)  CHARACTER SET ascii COLLATE ascii_bin NOT NULL,  -- cifrado (WEBHOOK_KEYS)
  eventos     JSON          NOT NULL,     -- lista de eventos (não é dado pessoal)
  ativo       BOOLEAN       NOT NULL DEFAULT TRUE,
  criado_em   DATETIME(6)   NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  KEY ix_webhooks_empresa_id (empresa_id),
  CONSTRAINT fk_webhook_empresa FOREIGN KEY (empresa_id) REFERENCES empresas (id),
  -- MAIS SEGURO: no PostgreSQL nada impedia gravar o segredo em claro.
  CONSTRAINT ck_webhook_segredo_cifrado CHECK (segredo LIKE 'enc:v1:%' AND CHAR_LENGTH(segredo) > 80),
  CONSTRAINT ck_webhook_url     CHECK (url LIKE 'https://%'),
  CONSTRAINT ck_webhook_eventos CHECK (JSON_TYPE(eventos) = 'ARRAY')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE webhook_entregas (
  id               INT          NOT NULL AUTO_INCREMENT,
  webhook_id       INT          NOT NULL,
  evento           VARCHAR(40)  NOT NULL,
  payload          TEXT CHARACTER SET ascii COLLATE ascii_bin NOT NULL,  -- cifrado
  status           VARCHAR(10)  NOT NULL DEFAULT 'pendente',
  tentativas       INT          NOT NULL DEFAULT 0,
  ultima_resposta  TEXT CHARACTER SET ascii COLLATE ascii_bin NULL,      -- cifrado
  atualizado_em    DATETIME(6)  NULL,
  criado_em        DATETIME(6)  NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  KEY ix_webhook_entregas_webhook_id (webhook_id),
  KEY ix_entregas_status_tentativas (status, tentativas),
  CONSTRAINT fk_entrega_webhook FOREIGN KEY (webhook_id) REFERENCES webhooks (id),
  CONSTRAINT ck_entrega_tentativas CHECK (tentativas >= 0),
  CONSTRAINT ck_entrega_status     CHECK (status IN ('pendente','entregue','falhou')),
  CONSTRAINT ck_pii_webhook_entregas_payload CHECK (payload IS NULL OR (SUBSTR(payload,1,7)='pii:v1:' AND SUBSTR(payload,72,1)=':' AND CHAR_LENGTH(payload)>170)),
  CONSTRAINT ck_pii_webhook_entregas_ultima_resposta CHECK (ultima_resposta IS NULL OR (SUBSTR(ultima_resposta,1,7)='pii:v1:' AND SUBSTR(ultima_resposta,72,1)=':' AND CHAR_LENGTH(ultima_resposta)>170))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE rendimentos (
  id           INT            NOT NULL AUTO_INCREMENT,
  carteira_id  INT            NOT NULL,
  data         DATE           NOT NULL,
  saldo_base   DECIMAL(14,2)  NOT NULL,
  valor        DECIMAL(14,2)  NOT NULL,
  taxa_diaria  DECIMAL(12,10) NOT NULL,
  criado_em    DATETIME(6)    NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  UNIQUE KEY uq_rendimento_carteira_dia (carteira_id, data),
  KEY ix_rendimentos_carteira_id (carteira_id),
  CONSTRAINT fk_rendimento_carteira FOREIGN KEY (carteira_id) REFERENCES carteiras (id),
  CONSTRAINT ck_rendimento_valores CHECK (saldo_base > 0 AND valor > 0 AND taxa_diaria > 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE produtos (
  id                   INT           NOT NULL AUTO_INCREMENT,
  nome                 VARCHAR(120)  NOT NULL,
  descricao            VARCHAR(280)  NOT NULL,
  preco                DECIMAL(14,2) NOT NULL,
  categoria            VARCHAR(40)   NOT NULL,
  emoji                VARCHAR(8)    NOT NULL,   -- por isso utf8mb4: emoji tem 4 bytes
  lojista_carteira_id  INT           NOT NULL,
  ativo                BOOLEAN       NOT NULL DEFAULT TRUE,
  PRIMARY KEY (id),
  CONSTRAINT fk_produto_lojista FOREIGN KEY (lojista_carteira_id) REFERENCES carteiras (id),
  CONSTRAINT ck_produto_preco CHECK (preco > 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE voos (
  id                    INT           NOT NULL AUTO_INCREMENT,
  origem                VARCHAR(3)    NOT NULL,
  origem_cidade         VARCHAR(60)   NOT NULL,
  destino               VARCHAR(3)    NOT NULL,
  destino_cidade        VARCHAR(60)   NOT NULL,
  companhia             VARCHAR(40)   NOT NULL,
  saida                 VARCHAR(5)    NOT NULL,
  chegada               VARCHAR(5)    NOT NULL,
  duracao               VARCHAR(10)   NOT NULL,
  direto                BOOLEAN       NOT NULL DEFAULT TRUE,
  preco                 DECIMAL(14,2) NOT NULL,
  milhas                INT           NOT NULL,
  parceiro_carteira_id  INT           NOT NULL,
  ativo                 BOOLEAN       NOT NULL DEFAULT TRUE,
  PRIMARY KEY (id),
  CONSTRAINT fk_voo_parceiro FOREIGN KEY (parceiro_carteira_id) REFERENCES carteiras (id),
  CONSTRAINT ck_voo_preco CHECK (preco > 0 AND milhas > 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE pontos_movimentos (
  id            INT          NOT NULL AUTO_INCREMENT,
  usuario_id    INT          NOT NULL,
  delta         INT          NOT NULL,
  motivo        VARCHAR(20)  NOT NULL,
  descricao     VARCHAR(140) NOT NULL,
  transacao_id  INT          NULL,
  criado_em     DATETIME(6)  NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  KEY ix_pontos_movimentos_usuario_id (usuario_id),
  CONSTRAINT fk_pontos_usuario   FOREIGN KEY (usuario_id)   REFERENCES usuarios (id),
  CONSTRAINT fk_pontos_transacao FOREIGN KEY (transacao_id) REFERENCES transacoes (id),
  CONSTRAINT ck_pontos_motivo CHECK (motivo IN ('compra_loja','compra_voo','resgate_voo','estorno_resgate'))   -- MAIS SEGURO
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE cartoes (
  id                      INT           NOT NULL AUTO_INCREMENT,
  carteira_id             INT           NOT NULL,
  apelido                 VARCHAR(60)   NOT NULL DEFAULT 'Cartão virtual',
  numero_masc             VARCHAR(32)   NOT NULL,   -- só a máscara (PCI): **** 1234
  bandeira                VARCHAR(20)   NOT NULL DEFAULT 'Visa',
  validade                VARCHAR(5)    NOT NULL,   -- MM/AA
  `virtual`               BOOLEAN       NOT NULL DEFAULT TRUE,  -- VIRTUAL é palavra reservada: crase
  estado                  VARCHAR(12)   NOT NULL DEFAULT 'ativo',
  compras_online          BOOLEAN       NOT NULL DEFAULT TRUE,
  compras_internacionais  BOOLEAN       NOT NULL DEFAULT FALSE,
  limite                  DECIMAL(14,2) NOT NULL DEFAULT 0,
  criado_em               DATETIME(6)   NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  KEY ix_cartoes_carteira_id (carteira_id),
  CONSTRAINT fk_cartao_carteira FOREIGN KEY (carteira_id) REFERENCES carteiras (id),
  CONSTRAINT ck_cartao_limite   CHECK (limite >= 0),
  -- MAIS SEGURO: impede gravar o número completo do cartão (no máx. 4 dígitos seguidos).
  CONSTRAINT ck_cartao_mascara  CHECK (numero_masc NOT REGEXP '[0-9]{5,}'),
  CONSTRAINT ck_cartao_validade CHECK (validade REGEXP '^(0[1-9]|1[0-2])/[0-9]{2}$')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- Conferência: 32 tabelas, todas InnoDB e utf8mb4.
SELECT COUNT(*) AS tabelas,
       SUM(engine = 'InnoDB') AS innodb,
       SUM(table_collation LIKE 'utf8mb4%') AS utf8mb4
  FROM information_schema.tables
 WHERE table_schema = 'astro_dados' AND table_type = 'BASE TABLE';
