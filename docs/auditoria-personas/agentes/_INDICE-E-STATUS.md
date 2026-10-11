# Agentes — índice, status e onde cada análise aterrissou

> **Modelo de execução (transparência):** as 4 análises da Onda técnica 1 foram lançadas como subagentes
> nativos, mas **falharam por limite de uso da sessão (HTTP 429)** antes de produzir relatório. O
> coordenador então conduziu a análise **lendo o código diretamente** (read-only), consolidando os
> resultados nos relatórios numerados. Os 15 arquivos de agente estão em
> `.claude/agents/auditoria-astro/` e podem ser reinvocados para análise independente adicional.

| Agente | Status | Onde está o resultado | Achado-chave |
|---|---|---|---|
| astro-arquitetura | Coordenador (código) | `02`, `06` (ASTRO-001) | Camadas sólidas; gate de papel no service (P3) |
| astro-ledger-pagamentos | Coordenador (código) | `02`, `06` (F-04/05/06), `09` | Idempotência por conta, lock anti-fracionamento, sem split em transferência |
| astro-seguranca-aplicacao | Coordenador (código) | `02`, `06` (F-01/02/03/09), `09` | DPoP+RLS+admin fail-closed; IDOR amostral refutado; varrer rotas `{id}` (ASTRO-002) |
| astro-identidade-permissoes | Coordenador (código) | `02`, `04` (matriz), `06` (F-07/08) | Posse+vínculo, ≥1 admin, maker-checker |
| astro-regulatorio-confianca | Coordenador (código) | `10` | Site responsável, mas sem aviso de simulação (ASTRO-010/011/012) |
| astro-ux-arquitetura-informacao | Coordenador (código) | `04` | IA diferenciada PF×PJ; densidade PJ no "Mais" (ASTRO-005) |
| astro-ui-design-system | Coordenador (parcial) | `05` | shadcn + aria; largura fixa desktop a testar (ASTRO-006/007) |
| astro-auditor-cetico | Coordenador | `07` | 3 hipóteses refutadas; reclassificação dos achados |
| astro-qa-acessibilidade | **PENDENTE** | — | Exige executar testes + axe/WCAG (ver `09` T-X*) |
| astro-sre-entrega | **PENDENTE** | — | Exige inspecionar CI/infra/deploy |
| astro-pf-primeiro-contato | PENDENTE (inspeção em `03`) | `03` J01–J03 | Jornadas por código; falta teste com usuário |
| astro-pf-acessibilidade | PENDENTE (parcial em `03`/`07`) | `03` J11, `07` | Falha de câmera/biometria é o ponto crítico |
| astro-mei-titular | PENDENTE (inspeção em `03`) | `03` J04–J05 | — |
| astro-pme-financeiro | PENDENTE (inspeção em `03`) | `03` J06–J07 | — |
| astro-grande-empresa | PENDENTE (inspeção em `03`) | `03` J08–J10, J14 | — |

## Como obter as análises independentes (opcional)
Reinvocar os subagentes por onda (3–4 em paralelo) quando o limite de uso permitir. Eles acrescentam
**independência** (sem contaminação) aos achados já consolidados pelo coordenador — útil para os eixos
QA/acessibilidade, SRE e personas, que hoje estão como inspeção ou pendentes.
