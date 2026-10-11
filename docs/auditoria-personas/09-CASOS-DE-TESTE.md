# 09 — Casos de teste sugeridos

> Baseado nos achados verificados (06) e nas jornadas (03). Marca "já existe" / "não existe" / "não
> verificado". Há **448 testes backend** e **43 front** (contados, não auditados um a um) — a coluna
> "estado" indica o que foi confirmado estaticamente nesta rodada.

## Autorização / IDOR (pytest — backend)
| # | Caso | Resultado esperado | Estado |
|---|---|---|---|
| T-A1 | Usuário A acessa `GET /pagamentos/transacoes/{id}` de B | 403/404 (não vaza) | não verificado — **criar matriz** (S0-1) |
| T-A2 | Usuário A acessa `GET /pagamentos/comprovante/{id}` de B | 403/404 | não verificado |
| T-A3 | `GET /cobrancas/{txid}` por terceiro | 200 **com campos sensíveis mascarados** | confirmado por código (`cobrancas.py:60-68`); falta teste explícito |
| T-A4 | Operador (não admin) chama `POST /empresas/atual/vinculos` | 403 | gate existe (`equipe_service:102-103`); confirmar teste negativo |
| T-A5 | Papel `consulta` tenta `POST /pagamentos/transferir` | 403 | servidor nega; confirmar teste |
| T-A6 | `X-Conta` de empresa sem vínculo | 403 (`conta_atual`) | confirmado por código; confirmar teste |

## Integridade financeira / idempotência / concorrência
| # | Caso | Resultado esperado | Estado |
|---|---|---|---|
| T-F1 | Mesma `Idempotency-Key`, 2ª chamada | devolve a MESMA transação (não duplica) | lógica confirmada (`deps`+`pagamento_service:49-50`) |
| T-F2 | Mesma chave, **valor diferente** | 409 | confirmado por código (`deps.escolher_chave`) |
| T-F3 | Chave de conta A reusada por conta B | não entrega a transação de A (escopo por carteira) | confirmado por código |
| T-F4 | 2 transferências simultâneas, saldo p/ uma só | só uma conclui; saldo nunca negativo | **executar** (lock) — não rodado |
| T-F5 | 2 lançamentos simultâneos somando acima da alçada diária | 2º vira pendente (reconferência no lock) | lógica confirmada (`pagamento_service:97-111`); **executar** |
| T-F6 | Transferência PF→PJ sem nota | **sem split** | confirmado por código (`pagamento_service:1-7`) |
| T-F7 | Pagar cobrança: soma bruto = líquido + IBS + CBS | sem centavo criado/perdido | **executar** (arredondamento) |
| T-F8 | Lote com 1 item inválido | falha isolada, demais consistentes/retomáveis | **executar** |

## Identidade / maker-checker
| # | Caso | Resultado esperado | Estado |
|---|---|---|---|
| T-I1 | Autor aprova a própria pendência | bloqueado (maker≠checker) | **confirmar no código de `/pendentes/decidir`** |
| T-I2 | Rebaixar/remover o último admin | 400 "precisa de ≥1 admin" | confirmado (`equipe_service:141`) |
| T-I3 | Membro suspenso tenta aprovar pendência existente | 403 | **executar** (J09) |
| T-I4 | Alçada alterada após criar a pendência | regra aplicada = a da execução | **executar** |

## Acessibilidade (Vitest + axe / manual) — não verificado
| # | Caso | Referência |
|---|---|---|
| T-X1 | Navegação por teclado alcança ações críticas | WCAG 2.2 AA |
| T-X2 | Contraste de valores (positivo/negativo/bloqueado) | AA |
| T-X3 | Fluxo quando câmera/biometria falha (J11) | caminho alternativo seguro |

## Prioridade de execução
S0-1 (T-A1..A6) e T-F4/F5/T-I1/T-I3 — são os que fecham a confiança para o pentest dos outros grupos.
