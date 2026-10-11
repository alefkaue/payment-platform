# 06 — Matriz de achados (verificados pelo coordenador)

> Fonte: revisão **read-only** direta do código no commit `289effb` (as ondas de subagentes caíram por
> limite de uso; o coordenador verificou as áreas críticas de autorização e finanças). Confiança: **A**
> = reproduzido no código citado; **B/C** = indício/necessita a Fase 1/2; **D** = preferência.
> Gravidade: P0 bloqueante · P1 alta · P2 média · P3 baixa.

## Resumo
Nenhum **P0/P1 confirmado** nas áreas auditadas. O backend aplica autorização de posse, DPoP, isolamento
RLS, idempotência anti-replay/forja e maker-checker com invariantes. **Três pré-hipóteses de risco foram
investigadas e REFUTADAS no código** (ver seção "Refutados"). Os itens abertos reais são de menor
gravidade (arquitetura/consistência) ou **não verificados** (biometria adversarial, regulatório, UX,
jornadas — pendentes).

## Forças confirmadas (Confiança A)

| ID | Área | Evidência | Por que importa |
|---|---|---|---|
| F-01 | Posse de conta sem IDOR | `deps.py:159-184` (`conta_atual`): PF confere `usuario_id`; PJ exige vínculo; sistema bloqueado | Impede operar/ler conta alheia via `X-Conta` |
| F-02 | Posse de sessão (DPoP) + aparelho + revogação | `deps.py:99-122` | Token roubado sem a chave do aparelho não serve; sessão cai na hora |
| F-03 | Isolamento multi-tenant (RLS) | `deps.py:112-113` → `db/isolamento.autorizar_usuario`; papéis `astro_app`/`astro_migrator` | Credencial SQL sem contexto não lê saldos |
| F-04 | Idempotência anti-replay e anti-forja | `deps.py:200-225` (branco rejeitado, header≠corpo, prefixo `u:`); `pagamento_service.py:49-50` (escopo por carteira) | Replay não duplica; cliente não forja chave de sistema |
| F-05 | Integridade contra fracionamento concorrente | `pagamento_service.py:97-111` (soma do dia reconferida dentro do lock) | Duas requisições simultâneas não furam a alçada diária |
| F-06 | Transferência nunca aciona split | `pagamento_service.py:1-7` | Pix comum PF→PJ não é tributado por engano |
| F-07 | Maker-checker com invariantes | `equipe_service.py:141` (≥1 admin ativo); `pagamento_service.py:66-94` (assinatura conjunta por porte) | Empresa não fica sem admin; Grande exige 2 assinaturas |
| F-08 | Gate de papel consistente | `exigir_papel(ADMIN)` em `equipe_service.py:102-103,148-149`, `folha_service.py:45,69`, `seguranca.py` (limites/chaves/webhooks/creditos); `PODE_MOVIMENTAR` em folha/cobrança | Operador/consulta não executam ação de admin |
| F-09 | Admin fail-closed + IP allowlist | `deps.py:137-144` (em produção sem allowlist → 403) | Painel admin não abre de rede arbitrária |
| F-10 | NF-e valida emissor e pagador | `cobranca_service.py:103` (CNPJ emissor), `:177-178` (documento do pagador) | Cobrança não é paga pela conta errada |

## Pré-hipóteses REFUTADAS na verificação (registro de honestidade)

| Hipótese inicial | Resultado | Evidência |
|---|---|---|
| Gestão de vínculo (convidar/alterar/suspender/revogar) sem papel na rota → escalonamento | **REFUTADO**: gate de ADMIN está no service | `equipe_service.py:102-103,148-149` |
| `pagar_folha` sem gate de papel | **REFUTADO**: `exigir_papel(*PODE_MOVIMENTAR)` + device | `folha_service.py:112-114` |
| `ver_cobranca` (GET /cobrancas/{txid}) com IDOR | **REFUTADO**: intencional tipo-Pix, com **mascaramento** de campos sensíveis salvo biller/pagador | `cobrancas.py:60-68` (SECURITY_AUDIT A-10) |

## Achados abertos (reais, baixa gravidade)

### ASTRO-001 — Autorização por papel vive no service, não declarada na assinatura da rota
- **Tipo:** dívida técnica / arquitetura · **Gravidade:** P3 · **Confiança:** A
- **Impacto:** quem adicionar uma NOVA rota PJ precisa lembrar de chamar `exigir_papel`/`exigir_pj` dentro do service; o router não evidencia a política. Risco futuro de omissão, não falha atual.
- **Evidências:** `routers/contas.py:156-195` (rotas sem gate visível) × `services/equipe_service.py:102-149` (gate presente).
- **Sugestão:** manter, mas documentar o padrão (ou adicionar teste que garanta que toda rota PJ de escrita exige papel). **Teste de aceite:** teste que falha se uma rota de escrita PJ não rejeitar papel `CONSULTA`.

### ASTRO-002 — Cobertura de teste por-rota de IDOR/papel não confirmada nesta fase
- **Tipo:** QA · **Gravidade:** P2 · **Confiança:** C
- **Impacto:** há 448 testes, mas não foi verificado (estaticamente) que **cada** GET por id e cada rota de escrita PJ tem teste negativo de autorização. Lacuna possível, não confirmada.
- **Sugestão/Teste de aceite:** matriz de autorização (pendente em `09-CASOS-DE-TESTE.md`) cobrindo todas as rotas `{id}`.

## Dimensões NÃO verificadas (pendentes — não convertidas em nota)
Biometria/liveness adversarial; regulatório/promessas (site, "banco/Pix/FGC", split 2026); UX e
arquitetura de informação; acessibilidade WCAG; SRE/CI/backup; as 14 jornadas (J01–J14). Exigem reinvocar
os subagentes correspondentes e/ou subir o ambiente.
