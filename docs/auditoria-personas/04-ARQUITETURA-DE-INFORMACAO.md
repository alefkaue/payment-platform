# 04 — Arquitetura de informação

> Revisão read-only de `app/src/lib/nav.ts` e `app/src/routes/_app.tsx`, commit `289effb`. Inspeção de
> estrutura — não substitui teste com usuário (ver `11`).

## Sitemap atual (fato, por perfil)

**PF — barra principal:** Início · Pix · Cartões · Extrato.
**PF — "Mais":** Entenda o split · Notificações · Convites de empresas · Meu perfil · Segurança · Ajuda.

**PJ — barra principal:** Início · Pagar · Contas · Split.
**PJ — "Mais":** Extrato · Equipe & alçadas · Folha · Aprovações · Auditoria · Cartão corporativo ·
Notificações · Perfil · Segurança · Ajuda.

Seletor de "Conta em uso" (`_app.tsx:217`, `role="tablist"`) troca entre conta pessoal e empresas.
`navPrimaria` filtra o atalho "Pagar" para o papel `consulta` (`nav.ts:107-110`).

## Forças (Confiança A)
- **IA diferenciada por perfil** — PF e PJ têm barras distintas e condizentes com a tarefa (PF: Pix/cartão;
  PJ: pagar/contas/split). `nav.ts:38-48`.
- **Progressive disclosure** — itens secundários no menu "Mais" com `hint` explicativo (`nav.ts:51-104`),
  reduzindo sobrecarga da barra principal.
- **Permissão reflete na navegação** — `consulta` não vê atalho de mover (defesa também no servidor).
- **Acessibilidade estrutural** — `aria-label`, `role="tablist"`, `role="dialog"` presentes (`_app.tsx`).

## Achados

### ASTRO-004 — "Split" na barra principal PJ pode competir com tarefas mais frequentes
- **Tipo:** UX/IA · **Gravidade:** P3 · **Confiança:** D (preferência — validar)
- **Impacto:** para PME/Grande, "Aprovações" (pendentes) e "Extrato" tendem a ser mais usados no dia a dia
  do que "Split" (simulação). Hoje Aprovações está no "Mais" (`nav.ts:82`).
- **Sugestão:** testar promover "Aprovações" à barra principal PJ para papéis aprovador/admin. **Teste de
  aceite:** teste com 3–5 operadores (ver `11`). **É preferência até validar.**

### ASTRO-005 — Densidade PJ no "Mais" (10 itens) pode esconder funções-chave
- **Tipo:** UX/IA · **Gravidade:** P2 · **Confiança:** C
- **Impacto:** Equipe, Folha, Aprovações, Auditoria ficam todas no mesmo menu "Mais" com 10 itens;
  descoberta pode ser difícil em telefone. Tesouraria provavelmente se beneficia de uma visão desktop com
  esses itens sempre visíveis (ver `05`).
- **Sugestão:** agrupar "Gestão" (Equipe/Folha/Aprovações/Auditoria) como seção nomeada no "Mais" e, no
  desktop, expor na sidebar. **Validar com PME/Grande.**

## Matriz de acesso por papel (observada)
| Função | PF | PJ consulta | PJ operador | PJ aprovador | PJ admin |
|---|---|---|---|---|---|
| Ver saldo/extrato/auditoria | ✓ | ✓ (auditoria: admin/aprovador) | ✓ | ✓ | ✓ |
| Mover/pagar | ✓ | ✗ (atalho oculto + servidor nega) | ✓ (até alçada) | ✓ | ✓ |
| Equipe/alçadas, webhooks, chaves, folha cadastrar | — | ✗ | ✗ | ✗ | ✓ (`exigir_papel(ADMIN)`) |
| Aprovar pendência | — | ✗ | ✗ | ✓ | ✓ |
(Base: `nav.ts`, `deps.exigir_papel`, `seguranca.py`, `equipe_service.py`, `folha_service.py`.)

## Proposta (incremental, sem reformar tudo)
1. Validar barra principal PJ por papel (promover Aprovações). 2. Seção "Gestão" no "Mais". 3. Sidebar
desktop para PJ com Gestão visível. Nada disso exige refazer o visual — só reorganizar `nav.ts` e o layout.
