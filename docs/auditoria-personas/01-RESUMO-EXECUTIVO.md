# 01 — Resumo executivo

> Auditoria read-only do ASTRO Payment Platform, commit `289effb`, branch `main`. Conduzida pelo
> coordenador lendo o código (as 4 análises-subagente da Onda 1 falharam por limite de uso — ver
> `agentes/_INDICE-E-STATUS.md`). **Nada de código foi alterado; nada foi commitado.**

## Diagnóstico objetivo
O ASTRO v9 é um protótipo acadêmico **notavelmente endurecido** no backend. As áreas mais sensíveis —
autorização, posse de conta, integridade financeira, identidade/permissões — foram **verificadas no
código** e **não apresentam P0/P1 confirmado**. A comunicação do produto é majoritariamente responsável
(app se marca como simulação; site cita a lei e usa "estimativa"). Os pontos abertos são de **menor
gravidade** (forma/consistência) ou **dependem de execução** (testes de concorrência, biometria
adversarial, acessibilidade WCAG, SRE/CI e teste com usuários reais) — explicitamente não convertidos em
nota nem em aprovação.

## 5 pontos positivos bem sustentados (Confiança A)
1. **Posse sem IDOR óbvio** — `deps.py:159-184` confere dono (PF) e vínculo ativo (PJ); conta de sistema bloqueada.
2. **Sessão à prova de roubo de token** — DPoP (`cnf.jkt`) + vínculo de aparelho + `sid` revogável (`deps.py:99-122`).
3. **Isolamento multi-tenant no banco (RLS)** + credenciais separadas app/migrador (`deps.py:112-113`, compose).
4. **Idempotência anti-replay/forja** e **lock contra fracionamento** (`deps.py:200-225`, `pagamento_service.py:49-50,97-111`); transferência nunca aciona split.
5. **Maker-checker com invariantes** (≥1 admin, assinatura conjunta por porte) e **admin fail-closed + IP allowlist**.

## 10 riscos/melhorias principais (ver `06` e por-tema)
| # | Item | Grav. | Conf. | Onde |
|---|---|---|---|---|
| 1 | Garantir teste negativo de autorização/IDOR em TODA rota `{id}`/escrita PJ (ASTRO-002) | P2 | C | `06`,`09` |
| 2 | Teste adversarial de liveness/anti-spoof + retenção de template (LGPD) | — | N/V | `08` S0-3 |
| 3 | Site público sem aviso de "protótipo/simulação" (ASTRO-010) | P2 | A | `10` |
| 4 | Confirmar alíquotas/cronograma 2026 com fonte oficial datada (ASTRO-012) | P2 | C | `10` |
| 5 | Layout desktop para tesouraria PJ (largura fixa, ASTRO-006) | P2 | C | `05` |
| 6 | Acessibilidade: alternativa segura quando câmera/biometria falha (J11) | P2 | C | `03`,`07` |
| 7 | Densidade do menu "Mais" PJ (10 itens) esconde gestão (ASTRO-005) | P2 | C | `04` |
| 8 | Padrão "gate de papel no service" sem teste-guardião (ASTRO-001) | P3 | A | `06` |
| 9 | "O banco separa..." no site sugere instituição autorizada (ASTRO-011) | P3 | A | `10` |
| 10 | Benefícios (loja/viagens/pontos/cartões) anunciados × habilitados (J03) | P2 | C | `03` |

## Bloqueios reais
**Nenhum P0 confirmado.** O "bloqueio" prático para liberar com confiança ao pentest dos outros grupos é
**executar** os testes negativos de autorização (item 1) e o teste adversarial de biometria (item 2).

## O que permanece não verificado (não vira nota)
Execução dos 448+43 testes; concorrência reproduzida; biometria adversarial; WCAG; SRE/CI/backup; as 14
jornadas com usuários reais. Ondas independentes de QA/SRE/personas ficam **pendentes** (reinvocáveis).

## Entregáveis
`00` (inventário, rotas) · `01`–`11` completos · `agentes/_INDICE-E-STATUS.md` · 15 subagentes em
`.claude/agents/auditoria-astro/`. Próximo passo recomendado: `08` S0-1 e S0-3.
