# 07 — Debate, contraprovas e revisão cética

> Papel do `astro-auditor-cetico`: sobre os achados, dizer se a evidência sustenta, se é bug ou
> preferência, se depende de versão antiga, se já há mitigação, e reclassificar. Base: `06`, `02`, `04`, `05`, `10`.

## Reclassificação dos achados mais impactantes

| Achado | Alegação | Veredito cético | Razão (evidência) |
|---|---|---|---|
| (hipótese) Gestão de equipe sem papel na rota | Escalonamento operador→admin | **DESATUALIZADO/REFUTADO** | Gate está no service `equipe_service.py:102-103,148-149` |
| (hipótese) `pagar_folha` sem papel | Qualquer vínculo paga folha | **REFUTADO** | `folha_service.py:112-114` exige `PODE_MOVIMENTAR`+device |
| (hipótese) IDOR em `ver_cobranca` | Vaza cobrança alheia | **REFUTADO** | Intencional tipo-Pix com mascaramento (`cobrancas.py:60-68`, A-10) |
| ASTRO-001 (papel no service) | Risco de omissão em rota nova | **CONFIRMADO (P3)** | É dívida de forma, não falha atual; propor teste-guardião |
| ASTRO-002 (cobertura IDOR por teste) | Pode faltar teste negativo | **PLAUSÍVEL/NECESSITA TESTE** | 448 testes, mas não varridos por rota `{id}` |
| ASTRO-004 (Split na barra PJ) | Ocupa espaço nobre | **OPINIÃO DE DESIGN** | Preferência; só validar com usuários |
| ASTRO-006 (largura fixa desktop) | Desperdiça espaço PJ | **PLAUSÍVEL/NECESSITA TESTE** | Trade-off real mobile×desktop |
| ASTRO-010 (site sem aviso de simulação) | Visitante pode achar que é real | **CONFIRMADO (P2)** | App avisa; site `page.tsx` não |
| ASTRO-012 (alíquotas 2026) | Pode afirmar vigência | **PLAUSÍVEL** | Há hedge "serão fixadas oficialmente"; confirmar fonte datada |

## Controvérsias registradas (lados e custo)
1. **Mobile-first no desktop (ASTRO-006)** — *Pró:* identidade mobile, apresentação coesa, 1 base. *Contra:*
   tesouraria PJ perde densidade (tabelas/aprovações). *Decisão sugerida:* manter mobile + **adicionar**
   layout desktop PJ; não é "erro", é cobertura faltante. Custo: M.
2. **Biometria facial obrigatória × acessibilidade (J11)** — *Pró:* segurança forte, anti-fraude. *Contra:*
   pessoa com baixa visão/câmera ruim pode ficar sem acesso. *Decisão sugerida:* alternativa segura (não
   baixar segurança; ex.: recuperação assistida com verificação adicional). **Exige validação.**
3. **"O banco separa..." no site (ASTRO-011)** — *Pró:* linguagem simples. *Contra:* sugere instituição
   autorizada. *Decisão:* trocar por "a plataforma/arranjo"; custo P. **Exige validação jurídica.**

## Princípio aplicado
Concordância entre agentes não é prova; cada veredito acima aponta `arquivo:linha` ou marca
"necessita teste". Três hipóteses de risco foram **derrubadas** pela própria evidência — sinal de que a
auditoria está calibrada para não inflar severidade.

## O que o cético NÃO pôde revisar
Achados de **biometria adversarial, SRE/CI, acessibilidade executada e as personas de cliente** não
existem ainda (ondas pendentes) — não há o que reclassificar até rodarem.
