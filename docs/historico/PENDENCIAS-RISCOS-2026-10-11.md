# Complemento do tratamento de riscos — 11/10/2026

## Resultado

Cartão: resolver pendências de segurança corrigíveis e verificáveis localmente.

Status: parcial quanto ao inventário inteiro; correções desta rodada concluídas.

Commits: nenhum; alterações no branch atual, sem push ou deploy Azure.

Arquivos alterados nesta rodada:

- backend/app/repositories/repository.py
- backend/app/repositories/extras.py
- backend/app/services/auth_service.py
- backend/app/services/seguranca_service.py
- backend/tests/test_acesso_runtime_postgres.py
- backend/tests/test_auditoria_atomica.py
- backend/tests/test_verificacoes_atomicas.py
- ACESSO_E_REGRAS_FINANCEIRAS.md
- docs/INVENTARIO-RISCOS-2026-10-10.md
- docs/PENDENCIAS-RISCOS-2026-10-11.md

### Correções

R09: senha de login, senha atual na troca, TOTP administrativo e verificação
facial agora reservam orçamento antes do trabalho caro. A transação considera
falhas concluídas e reservas em andamento. Limites por conta, conta/IP e IP são
conferidos juntos; uma recusa não deixa reservas parciais. E-mail/CPF continuam
usando a identidade canônica. Sucesso libera orçamento; falha permanece; uma
queda inesperada deixa a reserva ocupada até expirar a janela.

Reservas e conclusões são eventos de inserção na tabela existente; não ampliam
privilégios de UPDATE/DELETE sobre a trilha. Resultado e liberação são atômicos;
conclusão repetida não duplica falhas nem muda um resultado anterior. PostgreSQL
usa locks transacionais ordenados; SQLite usa lock local e permanece destinado
a desenvolvimento. A implementação não mantém conexão durante hash ou visão.
Referência: [locks PostgreSQL](https://www.postgresql.org/docs/16/explicit-locking.html).

Erros conhecidos de processamento facial (400/503) liberam a reserva sem gravar
um falso sucesso biométrico. Erro de autenticação facial (401) mantém a falha.
Se a persistência do resultado falhar, a reserva continua bloqueando trabalho.

R07: acrescentada auditoria mínima na mesma transação em revogação de uma
sessão, outras sessões e sessões de dispositivo, alteração KYB da empresa e
desligamento de funcionário. Com as sete operações anteriores, são 12 tipos
de alteração cobertos. Falha de auditoria reverte a alteração, inclusive UPDATE
em lote de tokens. Nenhuma revogação sem efeito gera registro mínimo adicional.
O ator mínimo continua sendo sistema; outros fluxos e a identificação completa
do iniciador ainda exigem tratamento próprio.

### Testes

- Backend completo SQLite final: 636 passaram / 46 pulados, sem falhas.
- PostgreSQL ampliado: 682 coletados, 650 passaram / 30 pulados / 2 falharam.
  As duas falhas eram expectativas em testes novos que ignoravam a biometria do
  login feito pela própria fixture. Ajustadas para comparar com o estado anterior.
  Rechecagem final de reservas e todos os testes de senha: 21 passaram no
  PostgreSQL e 21 no SQLite. Isso cobre os dois casos afetados; não se apresenta
  a primeira execução PostgreSQL como uma execução integral sem falhas.
- Privilégios/migrações isolados: 29 passaram; upgrade/downgrade/upgrade,
  aplicação dos privilégios e alembic check passaram. A nova reserva/conclusão
  funciona com a credencial restrita, sem alterar a trilha antiga.
- Testes específicos de auditoria e reservas: 32 passaram antes de acrescentar
  dois cenários de indisponibilidade, também aprovados na suíte final.
- Sem alterações novas no frontend; app/tsc/build não reexecutados nesta rodada.
  Evidência da rodada anterior: app 258 passaram / 2 pulados, tsc e build aprovados.
- git diff --check aprovado; busca dos segredos locais conhecidos sem achados.
- API reiniciada com a correção final; prontidão e site responderam HTTP 200.

A revisão também detectou uma regressão introduzida ao remover o controle antigo
usado pela troca de senha. Esse fluxo foi integrado à reserva e validado novamente;
a suíte SQLite final acima já contém a correção. Não houve mudança de esquema
nesta rodada nem uso do banco dos clientes como fixture.

### O que NÃO foi feito e por quê

- Azure, WAF, DNS/TLS, rede e desastre definitivo: dependem do ambiente ainda
  não criado; implantação continua proibida pela instrução do usuário.
- Resistência a deepfake/replay físico e release nativo: exigem aparelhos,
  modelos e medições reais; testes com stub não comprovam esses controles.
- Cifragem de todos os dados cadastrais/RLS por titular: permanecem pendentes;
  exigem projeto, migração e compatibilidade com busca, unicidade e operações
  entre contas. Não foram substituídos por uma política que a API possa contornar.
- Isolamento integral de OCR/biometria, limite HTTP distribuído, retenção e
  ensaio de restauração definitivo: continuam abertos e não foram validados
  nesta rodada. A reserva limita concorrência por sujeito, mas não é timeout
  de processamento ou proteção contra todo DDoS.
- Serviços de Pix/documentos reais: fora do objetivo de simulação definido.

Problemas que vi fora do escopo: as limitações restantes estão no
[inventário atualizado](INVENTARIO-RISCOS-2026-10-10.md). Não há garantia de
segurança absoluta; as correções não eliminam comprometimento do host, papel
compartilhado da API ou todas as falhas possíveis dos demais fluxos.

### Como testar na mão

1. Abrir http://127.0.0.1:8081/ e conferir que o aplicativo declara simulação.
2. Em banco descartável, executar pytest tests/test_verificacoes_atomicas.py
   tests/test_auditoria_atomica.py tests/test_forca_bruta.py tests/test_senha.py
   tests/test_admin_totp.py. Fixtures recriam tabelas: nunca apontar para o banco
   dos clientes. PostgreSQL é necessário para disputa real entre conexões.
3. Com conta de teste, provocar falhas até o limite e conferir 429 com Retry-After;
   sucessos abaixo do limite não devem ocupar o orçamento de falhas.
4. Conferir que bloqueio, revogação e demais alterações cobertas geram registros
   com sufixo _atomico, sem senha, hash de senha ou dados brutos nos detalhes.
5. Consultar /pronto na API local em http://127.0.0.1:8765.
