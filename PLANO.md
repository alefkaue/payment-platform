# PayFlow — plano de produto

Banco digital **para pessoas e empresas**, cujo diferencial é resolver o imposto da
Reforma Tributária (IBS/CBS) no ato do pagamento — o **split**. Documento vivo:
decisões tomadas + o que falta, com base em pesquisa de mercado.

---

## 1. Posicionamento

- **Somos um banco digital, não uma "plataforma de pagamento".** Para o público‑alvo
  (empresas que lidam com imposto/crédito), banco faz mais sentido: pode ofertar
  crédito, rendimento e proteção (FGC até R$ 250 mil/CNPJ). IP (instituição de
  pagamento) só movimenta — não concede crédito.
- **Foco declarado: split + empresas.** É o que nos diferencia de Nubank/Inter/C6.
  O PF entra como base de usuários (ver §4), mas a tese é B2B.

## 2. Split por setor (implementado — v1)

Cada negócio tem alíquota diferente na Reforma. Já está no cálculo
(`app/src/lib/split.ts` → `REGIMES`, `aliquotaRegime`, `regimeDoSetor`) e no
simulador do site:

| Regime | Paga | Setores |
|---|---|---|
| Padrão | 100% (≈ 26,5%) | indústria, comércio, autopeças, serviços gerais |
| Reduzido 30% | 70% (≈ 18,55%) | profissões regulamentadas (advocacia, contabilidade, engenharia, medicina…) |
| Reduzido 60% | 40% (≈ 10,6%) | saúde, educação, agro, cultura |
| Zero | 0% | cesta básica nacional |

**Importante (revisão 2026-10-06):** essa tabela serve só para o **simulador**. No
pagamento real, o imposto vem **da nota fiscal** (calculado por produto/serviço,
NCM/NBS), e o banco retém o que a nota destaca. Transferência comum **não** tem split.
O split "superinteligente" (abater crédito no ato) depende da plataforma pública
da Receita/CGIBS; hoje fazemos o "inteligente" (retém o bruto da nota) e mostramos
a restituição prevista como estimativa.

## 3. "O split não é roubo" (mensagem — a reforçar na apresentação)

Objeção esperada: *"isso é o banco/governo tirando meu dinheiro"*. Não é.
- O split **não cobra nada a mais** — é exatamente o imposto que **já era devido**.
- Ele só **recolhe na hora** em vez de depois: a apuração continua (assistida pela
  Receita), mas sai quase pronta, e a **sonegação** fica mais difícil.
- **Transferência nunca sofre retenção** (PF ou PJ). Só a venda com nota tem split.
- Para a empresa, o ganho é **previsibilidade de caixa** (o imposto não fica no caixa
  esperando a guia) e **apuração quase pronta** — evitar prometer "zero apuração". Onde comunicar: hero do site, onboarding PJ e um "por quê?" no
  card de Apuração.

## 4. Atrair PF (diferencial além de loja/viagens/split)

Pesquisa: o que puxa cliente em banco digital é **rendimento, caixinhas e cashback** —
não loja/viagem. Plano para o PF ter motivo real de trocar de banco:

1. **Saldo que rende 100% do CDI** automaticamente (teaser já no app). → próximo: real.
2. **Caixinhas/metas** com rendimento e liquidez diária (Nubank rende até ~120% CDI).
3. **Cashback no cartão virtual** (ex.: 1% em compras).
4. **Cartão virtual** sem plástico (feito) + Pix grátis (feito).
5. Gancho único nosso: **"imposto já resolvido"** = simplicidade/confiança (o split é
   invisível para PF, mas vira narrativa de marca).

## 5. Cartão + segurança + banco de dados (implementado — v1)

- **Cartão virtual 100% digital** (sem plástico), na tela de Configurações:
  estados **ativo/congelado**, travas de **compras online** e **internacionais**,
  **CVV dinâmico** (gira a cada janela; não é persistido — PCI) e limite.
  Camada de dados: `types.ts (Cartao)`, `mocks`, `api.ts (meuCartao/atualizarCartao/cvvDinamico)`.
- **Banco de dados (backend):** nova tabela `cartoes` + colunas `usuarios.porte`,
  `usuarios.regime_tributario`, `carteiras.creditos` (migration
  `b2c7f1a9d3e4_cartoes_porte_creditos_regime.py`).
- **Próximo:** emissão/2ª via, cartão de crédito (fatura), limites por cartão ajustáveis,
  e amarrar a trava de compra na autorização.

## 6. Configurações da conta (implementado — v1)

`/config` (ícone de engrenagem no header; **"Sair" mora aqui dentro**, não solto):
cartão virtual, **limites** (por transação / diário / noturno, escala PF×PJ),
**segurança & acesso** (biometria para MEI/PF; certificado e‑CNPJ + alçadas/dupla
autorização para PME/Grande) e dados da conta. **Próximo:** editar limites de fato,
gestão de assinantes/alçadas (PJ), dispositivos confiáveis, notificações.

## 7. Backend ↔ frontend (a fazer)

O app usa mocks (`src/lib/api.ts`). Para virar produto: expor no FastAPI
`porte`, `creditos`, split inteligente/**apuração**, **faturas** a pagar/receber e
**auth por certificado**; depois trocar o corpo das funções do `api.ts` por `fetch`.
O `split_service.py` já bate com o `split.ts` (alíquotas/arredondamento).

## 8. Apresentação Mercedes/Scania

Montadoras/autopeças = regime **padrão** e **muito crédito** de insumo. História:
"você cobra com a nota, recebe já líquido, o imposto sai conciliado à nota, os
créditos aparecem para a apuração, e cada pessoa opera com alçada e dupla aprovação".
Usar as alíquotas do ANO (2026 = 1%) e mostrar a projeção de 2033 separada.
Cronograma: split opcional em 2027, obrigatório no B2B a partir de 2028.

## 9. Roadmap priorizado

1. Backend de verdade (auth + endpoints) e ligar o app ao FastAPI.
2. Rendimento/caixinhas e cashback (chamariz PF).
3. Fluxo "cobrar cliente" (PJ) mostrando o split inteligente ao vivo.
4. Split por CNAE/alíquotas específicas.
5. Limpeza final: remover conexão Lovable; publicar site; gerar `.apk` (Android SDK).
