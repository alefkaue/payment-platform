#!/usr/bin/env bash
# =============================================================================
# Bateria de testes de segurança do LABORATÓRIO, com evidência em arquivo.
#
# Uso (Git Bash, a partir de db-mysql/):
#   LAB=/caminho/com/os/.cnf  MYSQL=/caminho/do/mysql.exe  ./testes/rodar_testes_lab.sh
#
# LAB é uma pasta FORA do repositório com um arquivo de opções por conta
# (root.cnf, svc_astro_api.cnf, svc_astro_migrator.cnf, auditor_astro.cnf,
# leitura_astro.cnf), cada um assim:
#   [client]
#   user=svc_astro_api
#   password=<senha sorteada no script 00>
#   host=127.0.0.1
#   port=3307
#   ssl-mode=VERIFY_CA
#   ssl-ca=<pasta de dados do servidor>/ca.pem
# Senha em arquivo de opções (e não em -p na linha de comando) não aparece na
# lista de processos nem no histórico do shell.
#
# FECHAR_JANELA=1 também roda o 99 (tranca o migrador e apaga as rotinas de
# laboratório). Depois disso, repetir os testes exige recriar o laboratório.
# =============================================================================
set -u
cd "$(dirname "$0")/.."
: "${LAB:?defina LAB com a pasta dos arquivos .cnf}"
MYSQL="${MYSQL:-mysql}"
SAIDA="testes/evidencias/resultado-lab.txt"
mkdir -p testes/evidencias

como() {   # como <conta> [opções do mysql...]
  local conta="$1"; shift
  "$MYSQL" --defaults-extra-file="$LAB/$conta.cnf" "$@"
}
secao() { printf '\n==================================================================\n%s\n==================================================================\n' "$1"; }

{
echo "Execução: $(date -u '+%Y-%m-%d %H:%M:%S') UTC"
como root -N -e "SELECT CONCAT('Servidor: MySQL ', VERSION(), ' | tls_version=', @@tls_version, ' | require_secure_transport=', @@require_secure_transport, ' | validate_password.policy=', @@validate_password.policy)"

secao "C01 conexão SEM TLS (ESPERADO: ERRO 3159)"
echo "-- conta da API (REQUIRE SSL na própria conta):"
como svc_astro_api --ssl-mode=DISABLED -e "SELECT 'conectou sem TLS - FALHA DE SEGURANCA'"
echo "-- até o root, que não tem REQUIRE SSL, é barrado pelo servidor (require_secure_transport):"
como root --ssl-mode=DISABLED -e "SELECT 'conectou sem TLS - FALHA DE SEGURANCA'"

secao "C02 forçar TLS 1.1 (ESPERADO: falha, só 1.2/1.3 são aceitos)"
como svc_astro_api --tls-version=TLSv1.1 -e "SELECT 'conectou com TLS 1.1 - FALHA DE SEGURANCA'"

secao "C03 TLS 1.2 com verificação do certificado do servidor (ESPERADO: OK)"
como svc_astro_api --tls-version=TLSv1.2 -t -e "SHOW SESSION STATUS WHERE Variable_name IN ('Ssl_version','Ssl_cipher')"

secao "C04 senha errada até bloquear (conta descartável com FAILED_LOGIN_ATTEMPTS 3)"
SENHA_TESTE=$(como root -N -B -e "CREATE USER 'teste_bloqueio'@'localhost' IDENTIFIED BY RANDOM PASSWORD REQUIRE SSL FAILED_LOGIN_ATTEMPTS 3 PASSWORD_LOCK_TIME 1" | awk '{print $3}')
for i in 1 2 3 4; do
  echo "-- tentativa $i com senha errada:"
  "$MYSQL" -h127.0.0.1 -P3307 -uteste_bloqueio -p"errada-$i" --ssl-mode=REQUIRED -e "SELECT 1" 2>&1 | grep -v "Using a password"
done
echo "-- agora com a senha CERTA (ESPERADO: continua bloqueada, ERRO 3955):"
"$MYSQL" -h127.0.0.1 -P3307 -uteste_bloqueio -p"$SENHA_TESTE" --ssl-mode=REQUIRED -e "SELECT 'entrou - FALHA'" 2>&1 | grep -v "Using a password"
unset SENHA_TESTE
como root -e "DROP USER 'teste_bloqueio'@'localhost'"

secao "C05 contexto válido COPIADO para outra conexão (replay) (ESPERADO: 5 na original, 0 na outra)"
LINHA=$(como svc_astro_api -N -B -e "CALL astro_privado.lab_entrar_como('sistema', NULL, NULL);
  SELECT TO_BASE64(@astro_contexto), @astro_prova, (SELECT COUNT(*) FROM astro.carteiras)")
CTX_B64=$(echo "$LINHA" | awk '{print $1}'); PROVA=$(echo "$LINHA" | awk '{print $2}')
echo "conexão original enxergou: $(echo "$LINHA" | awk '{print $3}') carteiras"
como svc_astro_api -t -e "SET @astro_contexto = FROM_BASE64('$CTX_B64'), @astro_prova = '$PROVA';
  SELECT COUNT(*) AS outra_conexao_enxerga FROM astro.carteiras"
unset LINHA CTX_B64 PROVA

secao "C06 testes SQL da conta da API (07_testes_seguranca.sql)"
como svc_astro_api --force --unbuffered -t < 07_testes_seguranca.sql 2>&1

secao "C07 auditor: confere a corrente e lê a trilha; NÃO lê cliente nem altera a trilha"
como auditor_astro -t -e "CALL astro_auditoria.verificar_cadeia()"
como auditor_astro -t -e "SELECT seq, ocorrido_em, usuario_bd, modo_app, usuario_app, tabela, operacao, registro_id,
  JSON_EXTRACT(depois, '\$.saldo') AS saldo_depois, LEFT(hash, 16) AS hash
  FROM astro_auditoria.trilha WHERE tabela = 'carteiras' ORDER BY seq DESC LIMIT 4"
como auditor_astro --force <<'SQL'
SELECT * FROM astro.usuarios;
SELECT * FROM astro_dados.usuarios;
DELETE FROM astro_auditoria.trilha;
UPDATE astro_auditoria.trilha SET tabela = 'x';
SQL

secao "C08 somente leitura: só agregados, nenhum dado pessoal"
como leitura_astro -t -e "SELECT * FROM astro_relatorios.resumo_carteiras"
como leitura_astro --force <<'SQL'
SELECT * FROM astro.carteiras;
SELECT * FROM astro_dados.usuarios;
SELECT * FROM astro_auditoria.trilha;
INSERT INTO astro_relatorios.resumo_carteiras VALUES ('PF', 1, 1, 1);
SQL

secao "C09 até o ADMIN: apagar a trilha é barrado; adulterar sem o trigger é DETECTADO"
como root --force -e "DELETE FROM astro_auditoria.trilha WHERE seq = 3"
como root -e "DROP TRIGGER astro_auditoria.trg_trilha_imutavel_upd;
  UPDATE astro_auditoria.trilha SET depois = JSON_SET(depois, '\$.adulterado', TRUE) WHERE seq = 3"
echo "-- auditor confere depois da adulteração (ESPERADO: integra = 0, quebra na seq 3):"
como auditor_astro -t -e "CALL astro_auditoria.verificar_cadeia()"
como root -e "UPDATE astro_auditoria.trilha SET depois = JSON_REMOVE(depois, '\$.adulterado') WHERE seq = 3;
  CREATE TRIGGER astro_auditoria.trg_trilha_imutavel_upd BEFORE UPDATE ON astro_auditoria.trilha FOR EACH ROW
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Trilha de auditoria imutavel'"
echo "-- valor original restaurado (ESPERADO: integra = 1):"
como auditor_astro -t -e "CALL astro_auditoria.verificar_cadeia()"

secao "C10 conciliação financeira depois de todos os testes (ESPERADO: tudo 0)"
como leitura_astro -t -e "CALL astro_relatorios.verificar_banco()"

if [ "${FECHAR_JANELA:-0}" = "1" ]; then
  secao "C11 fecha a janela de migração (99) e tenta logar como migrador (ESPERADO: ERRO 3118)"
  como root -t < 99_fechar_janela_migracao.sql
  como svc_astro_migrator -e "SELECT 'migrador entrou - FALHA'"
  como root -N -e "SELECT CONCAT('rotinas de laboratorio restantes: ', COUNT(*)) FROM information_schema.routines
    WHERE routine_schema = 'astro_privado' AND routine_name LIKE 'lab%'"
fi
} > "$SAIDA" 2>&1

echo "Evidência gravada em db-mysql/$SAIDA"
