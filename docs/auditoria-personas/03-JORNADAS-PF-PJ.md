# 03 — Jornadas PF/PJ (J01–J14)

> **Inspeção de fluxo por código** (rotas `app/src/routes/*` + endpoints `backend/app/routers/*`), commit
> `289effb`. **Nenhuma jornada foi executada** com front/back no ar — resultados = "fluxo esperado pelo
> código", a confirmar com teste real (ver `11`). Login observado: e-mail/senha + câmera/rosto (`login.tsx`).

| ID | Ator | Jornada | Rotas/endpoints (fato) | Observação de fluxo / risco a validar |
|---|---|---|---|---|
| J01 | PF | Cadastro→KYC→login/MFA→home | `criar-conta.tsx`→`POST /usuarios`(+cadastro-sessao); `login.tsx`→`/login`,`/login/mfa`; `/inicio` | Captura facial no cadastro; "Ambiente de teste" visível (`criar-conta:434`). Validar caminho quando câmera falha. |
| J02 | PF | Receber→Pix→comprovante→extrato | `_app.pix.tsx`/`_app.transferir.tsx`→`/pagamentos/transferir`; `_app.comprovante.$id`→`/pagamentos/transacoes/{id}`; `_app.extrato` | Confirmar que a tela mostra destinatário antes de enviar; comprovante escopado por `conta_atual`. |
| J03 | PF | Cartões, rendimento, pontos/loja/viagens | `_app.cartoes`; `/rendimento`; `/beneficios/*` | **Benefícios NÃO verificados** (`BENEFICIOS_HABILITADOS=0` em produção). Risco: UI anunciar o que não opera. |
| J04 | MEI | Cadastro PJ→representante→docs→conta | `POST /empresas`; `/identidade/documentos`; `/empresas/atual/documentos` (exige ADMIN) | KYB: consulta CNPJ/sócios citada no site; OCR ≠ autenticidade (a validar). |
| J05 | MEI | Cobrança com nota→split→recebimento | `POST /cobrancas` (`exigir_pj`+`PODE_MOVIMENTAR`, valida CNPJ emissor); `/split/simular` | Split marcado como simulação (`split-aviso.tsx`). Não confundir retenção futura com cobrança real 2026. |
| J06 | PME | Convidar operador/contador→aceitar→alçada | `POST /empresas/atual/vinculos`(ADMIN); `/convites/{id}/aceitar` (com rosto); `PATCH .../vinculos/{id}` | Convite por CPF; aceite com biometria; permissão mínima por papel (`equipe_service`). |
| J07 | PME | Operador lança→aprovador decide | `/pagamentos/transferir`→vira pendente; `/pagamentos/pendentes/{id}/decidir` | Maker-checker: autor não deve ser o aprovador; alçada reconferida no lock. |
| J08 | Grande | Acima do limite→assinaturas→execução | `motivo_aprovacao`→`assinatura_conjunta` por porte (`pagamento_service:66-94`) | 2 assinaturas na Grande acima do limite; atomicidade a confirmar em teste. |
| J09 | Grande | Suspender membro→pendências→sessões | `POST .../vinculos/{id}/suspender`(ADMIN); `/auth/sessoes` | Confirmar que suspenso não autoriza pendência já criada (invariante a testar). |
| J10 | PJ | Folha→funcionários→lote | `/empresas/atual/folha/pagar` (`PODE_MOVIMENTAR`+device) | Paga só funcionário cadastrado com conta PF (`folha_service:92`). Falha parcial de lote a testar. |
| J11 | Todos | Perda de aparelho/câmera→recuperar | `/auth/recuperacao`(+concluir); `/seguranca/dispositivos/{id}/bloquear` | **Ponto crítico de acessibilidade:** alternativa quando biometria é obrigatória e câmera falha. |
| J12 | Todos | Desconexão/refresh/duplo clique/troca PF↔PJ | `lib/http.ts` (401→refresh); idempotência (`deps.chave_idempotencia`); `X-Conta` | Botão duplo coberto por idempotência; troca de conta mantém isolamento (`conta_atual`). |
| J13 | Público | Site→proposta→cadastro | `site/app/page.tsx`→app | Site responsável (cita LC 214/2025, "Estimativa") mas **sem aviso de simulação** (ASTRO-010). |
| J14 | Auditor | Transação→pendência→decisão→extrato/log | `logs_auditoria`; `/empresas/atual/auditoria`(ADMIN/APROVADOR) | Trilha com autor/decisor; imutabilidade e timestamps a confirmar em teste. |

## Jornadas que mais pedem teste real (prioridade)
1. **J11** — falha de câmera/biometria (acessibilidade + segurança).
2. **J07/J08/J09** — maker-checker, assinatura conjunta e revogação eficaz (integridade PJ).
3. **J03** — benefícios anunciados × habilitados (evitar UI enganosa).

> Cada "observação" acima é **hipótese de fluxo**; converter em evidência exige subir o ambiente e
> executar os passos (Fase 2). Ver protocolo de usuários reais em `11`.
