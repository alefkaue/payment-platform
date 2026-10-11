# 05 — Design e responsividade

> Inspeção read-only parcial (nav/layout/componentes), commit `289effb`. **Tokens/contraste não foram
> auditados a fundo** — marcado como não verificado onde aplicável. Sem screenshots (não capturadas).

## Sinais observados (fato)
- Stack: React + Tailwind + **shadcn/ui** (`app/src/components/ui/*` — ~45 componentes base).
- Componentes próprios em `components/payflow/*` (ex.: `liveness.tsx`, `AvisoSimulacao.tsx`, `split-aviso.tsx`).
- Acessibilidade estrutural presente: `aria-label`, `role="tablist"`, `role="dialog"` (`_app.tsx`).
- Layout mobile-first; sidebar no desktop e barra inferior no mobile (`nav.ts` comenta os dois modos).

## Forças (Confiança A/B)
- Base de componentes madura (shadcn) tende a dar estados e acessibilidade coerentes "de fábrica".
- Aviso de simulação componentizado e reutilizado — consistência de mensagem (B).

## Achados

### ASTRO-006 — Largura fixa de telefone no desktop (decisão a testar, não erro)
- **Tipo:** UX/responsivo · **Gravidade:** P2 · **Confiança:** C
- **Impacto:** o app renderiza em largura de telefone; no desktop isso pode desperdiçar espaço para
  tesouraria PJ (tabelas de Equipe/Pendentes/Extrato/Auditoria). Pode ser proposital para a apresentação
  mobile, mas prejudica o trabalho PJ denso.
- **Evidência:** layout mobile-first (`_app.tsx`, `nav.ts`); telas PJ com listas (`_app.equipe`, `_app.pendentes`).
- **Sugestão:** manter mobile, mas oferecer **layout desktop** (sidebar + tabelas largas) para PJ.
  **Teste de aceite:** operador PME conclui aprovação/extrato no desktop sem rolagem horizontal. **Validar.**

### ASTRO-007 — Profundidade de tokens/contraste não confirmada
- **Tipo:** design/acessibilidade · **Gravidade:** P2 · **Confiança:** C (não verificado a fundo)
- **Impacto:** não foi auditado se cores de valor (positivo/negativo/bloqueado) e contraste atendem AA, nem
  se há tokens únicos de formatação monetária em todas as telas.
- **Sugestão:** auditoria de contraste AA + revisão de `lib/format.ts` como única fonte de formatação.
  **Teste de aceite:** checklist AA por tela crítica (ver `09`).

## Não verificado (pendente)
Tipografia/escala, estados `loading/disabled/error/success` tela a tela, touch targets, animação, e
responsividade real em breakpoints — exigem subir o app e/ou a onda `astro-ui-design-system`.
