# 10 — Riscos regulatórios e promessas

> Revisão read-only de `site/app/page.tsx` e marcadores de simulação no app, commit `289effb`.
> **Não é parecer jurídico** — itens marcados "exige validação jurídica/regulatória". Fontes com data.

## Panorama (preliminar, Confiança A no texto citado)
O produto se comunica de forma **majoritariamente responsável**: o app tem componente dedicado
`AvisoSimulacao.tsx` ("simulação/fictício/Demonstração") usado em `criar-conta.tsx:434` ("Ambiente de
teste"), `login.tsx:188`, `_app.split.tsx:119`, `_app.depositar.tsx:22-23` ("dinheiro de teste"); o site
usa "Estimativa" (`site/app/page.tsx:237`) e cita a lei e a transição. **Não há** alegação de FGC,
garantia, rendimento ou cashback no site (grep sem ocorrências).

## Forças (Confiança A)
- **Split descrito como estimativa** e condicionado à nota: `page.tsx:237-238` ("Sem nota... não há split").
- **Base legal citada:** LC 214/2025 e cronograma (2026 ano-teste; 2027 opcional; 2028 obrigatório B2B;
  pleno em 2033) — `page.tsx:283,287`, com a ressalva "As alíquotas de referência ainda serão fixadas
  oficialmente" (`:287`). Hedge correto.
- **Transferência sem split** explicitada ao público: `page.tsx:279,283`.
- **App se identifica como simulação** em telas sensíveis (cadastro, login, split, depósito).

## Achados

### ASTRO-010 — Site público sem aviso de protótipo/simulação
- **Tipo:** compliance/transparência · **Gravidade:** P2 · **Confiança:** A
- **Impacto:** o app avisa que é simulação, mas o **site de marketing** (`site/app/page.tsx`) apresenta a
  plataforma como produto em operação, sem rótulo de "protótipo acadêmico / ambiente de simulação". Um
  visitante pode crer que é um serviço financeiro ativo.
- **Evidência:** `site/app/page.tsx` (FAQs e features descrevem capacidade real; nenhum marcador de
  simulação encontrado no arquivo).
- **Sugestão:** faixa/nota no site: "Protótipo acadêmico — ambiente de simulação, sem movimentação de
  dinheiro real." **Teste de aceite:** o aviso aparece acima da dobra na home. **Exige validação
  jurídica/regulatória.**

### ASTRO-011 — Uso de "o banco" na descrição do mecanismo
- **Tipo:** compliance/terminologia · **Gravidade:** P3 · **Confiança:** A
- **Impacto:** `page.tsx:237,283` dizem "o banco separa a CBS e o IBS". Descritivo, mas pode sugerir que o
  ASTRO é uma instituição autorizada. "Como nos bancos digitais" (`:291`) é comparação, risco menor.
- **Sugestão:** trocar por "a plataforma/o arranjo de pagamento separa..."; evitar afirmar ser "banco".
  **Exige validação jurídica/regulatória.**

### ASTRO-012 — Alíquotas-teste de 2026 e cronograma: confirmar com fonte oficial datada
- **Tipo:** compliance · **Gravidade:** P2 · **Confiança:** C
- **Impacto:** `page.tsx:287` afirma "2026 é ano-teste (CBS 0,9% + IBS 0,1%)". Precisa bater com os
  comunicados da Receita Federal (testes do Split Payment a partir de **15/10/2026**, ambiente controlado,
  sem efeito em operações reais — comunicado 30/09/2026) e com a LC 214/2025. Números no código **não**
  comprovam vigência legal.
- **Sugestão:** citar a fonte/data ao lado da estimativa e marcar "valores de referência, sujeitos a
  fixação oficial". **Exige validação jurídica/regulatória.**

## Dados pessoais (LGPD) — a aprofundar
Biometria é dado sensível. O código cifra template (`core/dados_pessoais.py`, `security.cifrar_embedding`),
mas **consentimento, base legal, retenção e minimização declarados ao usuário** não foram auditados aqui —
pendente (persona acessibilidade + regulatório), **exige validação jurídica**.

## Fontes (consultar atualização)
- Receita Federal — Split Payment, comunicado 30/09/2026 (testes a partir de 15/10/2026).
- LC 214/2025 (Reforma Tributária — IBS/CBS). ANPD/LGPD (dado biométrico sensível).
