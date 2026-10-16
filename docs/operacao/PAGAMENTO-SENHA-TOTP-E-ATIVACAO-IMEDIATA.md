# Pagamento por senha/TOTP e ativação imediata de conta (acadêmico)

Relatório das mudanças do `prompt.md` referentes a **autenticação de pagamento (#2)** e **ativação
imediata de conta (#3)**. A verificação documental simulada (#1) foi feita pelo time (ver
[DOCUMENTO-COLETA-ACADEMICA.md](DOCUMENTO-COLETA-ACADEMICA.md)).

> A plataforma **não** comprova identidade civil, **não** atesta autenticidade governamental de documentos
> e **não** movimenta dinheiro real. É protótipo acadêmico para pentest.

## 1. O que foi alterado (nesta entrega)
- **Transferência e lote** deixam de exigir **reconhecimento facial** e passam a confirmar por **SENHA**
  da conta (reautenticação no backend). Acima de `LIMITE_AUTENTICACAO_ADICIONAL` (padrão **R$ 5.000,00**),
  exigem também um **2º fator TOTP** (app autenticador).
- **Ativação imediata de conta** no modo acadêmico: a conta opera assim que criada, sem fila de aprovação
  de KYC. (`backend/app/repositories/repository.py:_exigir_identidade_financeira`.)
- Novos endpoints para **ativar o TOTP** do usuário: `POST /auth/totp` e `POST /auth/totp/confirmar`;
  `/auth/eu` passa a informar `tem_totp`.

## 2. Por que a verificação documental é simulada
No modo acadêmico (`DOCUMENTO_VERIFICAR_IDENTIDADE=0`, só com `DEMONSTRACAO_PUBLICA=1`), não há comparação
de nome/CPF/nascimento/rosto do documento com o cadastro, nem consulta externa de autenticidade. O
objetivo é deixar os participantes criarem contas e testarem os controles sem depender de verificação real
de identidade.

## 3. O que o sistema realmente verifica na imagem
Validação **estrutural** do arquivo (tipo, tamanho, decodificação) e classificação **visual** de que a
imagem parece um documento de identificação aceito (RG/CNH/CIN). **Não** afirma detectar falsificações nem
comprovar identidade. O caso fica como `identidade = não verificada`. (Detalhe em DOCUMENTO-COLETA-ACADEMICA.)

## 4. Por que removemos o reconhecimento facial do pagamento
Facilitar o teste e alinhar ao contexto acadêmico, trocando o 2º fator biométrico por **senha** (sempre) e
**TOTP** (acima do limite) — mecanismos auditáveis por quem for pentestar, sem depender de câmera. A
autorização final continua **no backend**; nada é liberado só pela interface.

## 5. Como funciona a confirmação por valor
- **≤ R$ 5.000,00:** confirma com a **senha** da conta. Senha errada → recusado (401).
- **> R$ 5.000,00:** exige **senha + código TOTP**. O código tem validade curta (passo de 30 s), é
  **anti-replay** (um código já usado é recusado) e, se o usuário **não tiver TOTP ativo**, o pagamento
  **não é liberado** (403) — precisa ativar o 2º fator antes.
- Limite **configurável** por `LIMITE_AUTENTICACAO_ADICIONAL` (Decimal, sem erro de ponto flutuante).
- A confirmação acompanha a própria operação (valor, destinatário, conta de origem no mesmo pedido), então
  uma confirmação anterior não autoriza outra transação; o TOTP não se reutiliza.

> **Limite de R$ 5.000** é decisão **acadêmica** (dar liberdade ao pentest), **não** recomendação para
> instituição financeira real — que exigiria 2º fator em valores bem menores ou por avaliação de risco.

## 6. Por que as contas são ativadas imediatamente
No ambiente acadêmico a identidade é simulada; exigir KYC "aprovado" travaria todos. A conta fica
**operacional** na hora, com a identidade documental marcada **não verificada**. `ativo` (operacional) **≠**
`identidade_verificada`. A checagem de **usuário ativo** (não suspenso/revogado) continua — a ativação
imediata **não** contorna autenticação, autorização, saldo, limites, idempotência, auditoria nem alçadas PJ.

## 7. Riscos aceitos APENAS no ambiente acadêmico
- Documento não prova identidade nem autenticidade (coleta simulada).
- Contas operam sem verificação real de identidade.
- Limite de 2º fator alto (R$ 5.000) para dar liberdade ao teste.
Esses relaxamentos só valem com `DEMONSTRACAO_PUBLICA=1`; em produção real as travas de boot impedem.

## 8. O que seria necessário num ambiente financeiro real
Verificação de identidade (KYC/KYB) com documento+biometria e consulta oficial; 2º fator obrigatório em
valores baixos ou por risco; antifraude e monitoramento; WAF/borda; e revisão jurídica/regulatória (BCB,
LGPD). Nada disso é substituído pelas decisões acadêmicas acima.

## 9. Testes realizados (executados)
`python -m pytest` (SQLite, no container do backend):
- **711 passaram, 61 pulados** (os pulados exigem PostgreSQL). Inclui a matriz nova de pagamento:
  R$100 e R$5.000 só com senha; R$5.000,01 só com senha+TOTP; senha errada → 401; TOTP errado/reutilizado
  → 401; acima do limite sem TOTP ativo → 403; reenvio idempotente não duplica.
- Ativação imediata: conta pendente opera no modo acadêmico; usuário inativo continua bloqueado; produção
  real ainda exige KYC aprovado.
- **Falhas pré-existentes (não relacionadas):** `tests/test_instalacao_containers.py` depende de
  Docker/host e falha neste runner — já existia antes desta mudança.

## Pendente (coerência #4, próxima etapa)
- Aplicar a mesma regra (senha/TOTP, sem facial) a **cobrança, folha e aprovação de pendências** (ainda
  usam facial).
- **Frontend/Android:** telas de confirmação enviam o rosto; precisam enviar `senha`/`codigo_totp` e ter a
  tela de ativação do TOTP. **Não redesplegar o backend sem atualizar o front junto**, senão os pagamentos
  no site param (front manda rosto, backend espera senha).
