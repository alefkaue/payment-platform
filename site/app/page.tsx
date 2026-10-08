"use client";

import { useEffect, useState } from "react";

type Tipo = "PF" | "PJ";
type Vigencia = "2026" | "2027" | "2029" | "2031" | "2033";

// Tabela de transição da Reforma (mesma do app e do backend). CBS/IBS de
// referência (8,8% / 17,7%) ainda são estimativas oficiais em definição.
const ALIQUOTAS: Record<Vigencia, { cbs: number; ibs: number; rotulo: string }> = {
  "2026": { cbs: 0.009, ibs: 0.001, rotulo: "2026 — ano-teste (0,9% + 0,1%)" },
  "2027": { cbs: 0.088, ibs: 0.001, rotulo: "2027–2028 — CBS cheia, IBS 0,1%" },
  "2029": { cbs: 0.088, ibs: 0.0177, rotulo: "2029 — IBS em 10% da referência" },
  "2031": { cbs: 0.088, ibs: 0.0531, rotulo: "2031 — IBS em 30% da referência" },
  "2033": { cbs: 0.088, ibs: 0.177, rotulo: "2033 — regime pleno (≈26,5%)" },
};

type Regime = "padrao" | "reduzido_30" | "reduzido_60" | "zero";
const REGIMES: Record<Regime, { fator: number; rotulo: string }> = {
  padrao: { fator: 1, rotulo: "Padrão — indústria, comércio, autopeças" },
  reduzido_30: { fator: 0.7, rotulo: "Reduzido 30% — profissões regulamentadas" },
  reduzido_60: { fator: 0.4, rotulo: "Reduzido 60% — saúde, educação, agro" },
  zero: { fator: 0, rotulo: "Zero — cesta básica" },
};

const brl = (n: number) =>
  Number(n || 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });

const ICONES: Record<string, string[]> = {
  nota: [
    "M4 2v20l2-1 2 1 2-1 2 1 2-1 2 1 2-1 2 1V2l-2 1-2-1-2 1-2-1-2 1-2-1-2 1Z",
    "M16 8h-6a2 2 0 1 0 0 4h4a2 2 0 1 1 0 4H8",
    "M12 17.5v-11",
  ],
  raio: [
    "M4 14a1 1 0 0 1-.78-1.63l9.9-10.2a.5.5 0 0 1 .86.46l-1.92 6.02A1 1 0 0 0 13 10h7a1 1 0 0 1 .78 1.63l-9.9 10.2a.5.5 0 0 1-.86-.46l1.92-6.02A1 1 0 0 0 11 14z",
  ],
  carteira: [
    "M19 7V4a1 1 0 0 0-1-1H5a2 2 0 0 0 0 4h15a1 1 0 0 1 1 1v4h-3a2 2 0 0 0 0 4h3a1 1 0 0 0 1-1v-2a1 1 0 0 0-1-1",
    "M3 5v14a2 2 0 0 0 2 2h15a1 1 0 0 0 1-1v-4",
  ],
  creditos: [
    "M14 8A6 6 0 1 1 2 8a6 6 0 0 1 12 0Z",
    "M18.09 10.37A6 6 0 1 1 10.34 18",
    "M7 6h1v4",
    "m16.71 13.88.7.71-2.82 2.82",
  ],
  equipe: [
    "M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2",
    "M13 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0Z",
    "M22 21v-2a4 4 0 0 0-3-3.87",
    "M16 3.13a4 4 0 0 1 0 7.75",
  ],
  recorrente: ["m17 2 4 4-4 4", "M3 11v-1a4 4 0 0 1 4-4h14", "m7 22-4-4 4-4", "M21 13v1a4 4 0 0 1-4 4H3"],
  pessoa: ["M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2", "M16 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0Z"],
  empresa: [
    "M6 22V4a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v18Z",
    "M6 12H4a2 2 0 0 0-2 2v6a2 2 0 0 0 2 2h2",
    "M18 9h2a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2h-2",
    "M10 6h4M10 10h4M10 14h4M10 18h4",
  ],
  mais: ["M5 12h14", "M12 5v14"],
  menos: ["M5 12h14"],
  sol: [
    "M16 12a4 4 0 1 1-8 0 4 4 0 0 1 8 0Z",
    "M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41",
  ],
  lua: ["M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"],
};

function Icone({ nome }: { nome: keyof typeof ICONES }) {
  return (
    <svg className="icon" viewBox="0 0 24 24" aria-hidden>
      {ICONES[nome].map((d) => (
        <path key={d} d={d} />
      ))}
    </svg>
  );
}

/** Logotipo oficial (svg/logo-astro-*.svg); a cor segue o tema: só preto ou branco. */
function Logo() {
  return (
    <svg className="logo" viewBox="0 -61.28 353.76 62.56" role="img" aria-label="Astro">
      <path d="M0 0 22.47 -60H36.33L58.8 0H44.31L29.4 -36.06L14.49 0Z" />
      <path d="M71.4 -19.6H86.68Q87.08 -16.88 89.16 -14.8Q91.24 -12.72 94.72 -11.6Q98.2 -10.48 102.84 -10.48Q109.48 -10.48 113.28 -12.32Q117.08 -14.16 117.08 -17.52Q117.08 -20.08 114.88 -21.48Q112.68 -22.88 106.68 -23.52L95.08 -24.72Q83 -25.92 77.6 -30.32Q72.2 -34.72 72.2 -42.32Q72.2 -48.32 75.76 -52.56Q79.32 -56.8 85.76 -59.04Q92.2 -61.28 100.84 -61.28Q109.4 -61.28 115.96 -58.8Q122.52 -56.32 126.44 -51.92Q130.36 -47.52 130.68 -41.6H115.4Q115.08 -44.08 113.2 -45.8Q111.32 -47.52 108.16 -48.52Q105 -49.52 100.6 -49.52Q94.52 -49.52 90.96 -47.8Q87.4 -46.08 87.4 -42.88Q87.4 -40.48 89.52 -39.12Q91.64 -37.76 97.08 -37.12L109.32 -35.76Q117.72 -34.88 122.76 -32.96Q127.8 -31.04 130.04 -27.68Q132.28 -24.32 132.28 -19.2Q132.28 -13.04 128.56 -8.44Q124.84 -3.84 118.16 -1.28Q111.48 1.28 102.6 1.28Q93.4 1.28 86.48 -1.36Q79.56 -4 75.6 -8.68Q71.64 -13.36 71.4 -19.6Z" />
      <path d="M165.72 -53.28H180.84V0H165.72ZM142.36 -60H204.2V-46.64H142.36Z" />
      <path d="M229.96 -33.6H252.44Q256.68 -33.6 259.16 -35.56Q261.64 -37.52 261.64 -41.04Q261.64 -44.56 259.16 -46.52Q256.68 -48.48 252.44 -48.48H227.8L234.6 -55.92V0H219.48V-60H254.44Q261.16 -60 266.2 -57.6Q271.24 -55.2 274.04 -50.96Q276.84 -46.72 276.84 -41.04Q276.84 -35.44 274.04 -31.2Q271.24 -26.96 266.2 -24.56Q261.16 -22.16 254.44 -22.16H229.96ZM239.64 -28.08H256.68L278.76 0H261.24Z" />
      <path d="M353.76 -30C353.76 -12.77 339.79 1.2 322.56 1.2C305.33 1.2 291.36 -12.77 291.36 -30C291.36 -47.23 305.33 -61.2 322.56 -61.2C330.92 -61.2 338.51 -57.91 344.12 -52.56C339.6 -56.48 333.7 -58.86 327.24 -58.86C313.02 -58.86 301.5 -47.34 301.5 -33.12C301.5 -18.9 313.02 -7.38 327.24 -7.38C341.46 -7.38 352.98 -18.9 352.98 -33.12C352.98 -35.96 352.52 -38.7 351.67 -41.26C353.02 -37.77 353.76 -33.97 353.76 -30Z" />
    </svg>
  );
}

/** Símbolo Eclipse (anel aberto — nunca fechar). */
function Eclipse() {
  return (
    <svg className="eclipse" viewBox="10 10 80 80" aria-hidden>
      <path d="M90 50C90 72.09 72.09 90 50 90C27.91 90 10 72.09 10 50C10 27.91 27.91 10 50 10C60.72 10 70.45 14.22 77.63 21.08C71.84 16.05 64.28 13 56 13C37.77 13 23 27.77 23 46C23 64.23 37.77 79 56 79C74.23 79 89 64.23 89 46C89 42.35 88.41 38.85 87.32 35.57C89.05 40.04 90 44.91 90 50Z" />
    </svg>
  );
}

function calcularSplit(valor: string | number, tipo: Tipo, vigencia: Vigencia, fator = 1) {
  const v = Math.round(Number(valor || 0) * 100) / 100;
  if (tipo !== "PJ") return { bruto: v, cbs: 0, ibs: 0, liquido: v, split: false };
  const a = ALIQUOTAS[vigencia];
  const cbs = Math.round(v * a.cbs * fator * 100) / 100;
  const ibs = Math.round(v * a.ibs * fator * 100) / 100;
  return { bruto: v, cbs, ibs, liquido: Math.round((v - cbs - ibs) * 100) / 100, split: true };
}

function useReveal() {
  useEffect(() => {
    const els = document.querySelectorAll(".reveal");
    const io = new IntersectionObserver(
      (entries) =>
        entries.forEach((e, i) => {
          if (e.isIntersecting) {
            setTimeout(() => e.target.classList.add("vis"), Math.min(i, 8) * 70);
            io.unobserve(e.target);
          }
        }),
      { threshold: 0.12, rootMargin: "0px 0px -8% 0px" },
    );
    els.forEach((el) => io.observe(el));
    return () => io.disconnect();
  }, []);
}

function Calculadora() {
  const [valor, setValor] = useState("10000");
  const [tipo, setTipo] = useState<Tipo>("PJ");
  const [vig, setVig] = useState<Vigencia>("2033");
  const [regime, setRegime] = useState<Regime>("padrao");
  const r = calcularSplit(valor, tipo, vig, REGIMES[regime].fator);
  const pLiq = r.bruto > 0 ? (r.liquido / r.bruto) * 100 : 100;
  return (
    <div className="card">
      <div className="campos">
        <div className="campos-2">
          <div className="campo">
            <label className="label" htmlFor="calc-valor">
              Valor (R$)
            </label>
            <input
              id="calc-valor"
              className="tabular"
              inputMode="decimal"
              value={valor}
              onChange={(e) => setValor(e.target.value)}
            />
          </div>
          <div className="campo">
            <span className="label">Quem vende</span>
            <div className="chips" role="group" aria-label="Quem vende">
              {(
                [
                  ["PF", "Pessoa"],
                  ["PJ", "Empresa"],
                ] as [Tipo, string][]
              ).map(([k, t]) => (
                <button
                  key={k}
                  type="button"
                  className="chip"
                  aria-pressed={tipo === k}
                  onClick={() => setTipo(k)}
                >
                  {t}
                </button>
              ))}
            </div>
          </div>
        </div>
        <div className="campo">
          <label className="label" htmlFor="calc-ano">
            Ano
          </label>
          <select id="calc-ano" value={vig} onChange={(e) => setVig(e.target.value as Vigencia)}>
            {(Object.entries(ALIQUOTAS) as [Vigencia, (typeof ALIQUOTAS)[Vigencia]][]).map(
              ([k, a]) => (
                <option key={k} value={k}>
                  {a.rotulo}
                </option>
              ),
            )}
          </select>
        </div>
        {tipo === "PJ" ? (
          <div className="campo">
            <label className="label" htmlFor="calc-regime">
              Regime do setor
            </label>
            <select
              id="calc-regime"
              value={regime}
              onChange={(e) => setRegime(e.target.value as Regime)}
            >
              {(Object.entries(REGIMES) as [Regime, (typeof REGIMES)[Regime]][]).map(([k, g]) => (
                <option key={k} value={k}>
                  {g.rotulo}
                </option>
              ))}
            </select>
          </div>
        ) : null}
      </div>

      <div className="split-bar" style={{ marginTop: 32 }} aria-hidden>
        <div className="liq" style={{ width: `${pLiq}%` }} />
        {r.split && r.cbs + r.ibs > 0 ? <div className="tax" style={{ flex: 1 }} /> : null}
      </div>
      <div style={{ marginTop: 16 }}>
        <div className="linha">
          <span className="muted">Bruto</span>
          <strong>{brl(r.bruto)}</strong>
        </div>
        {r.split ? (
          <>
            <div className="linha">
              <span className="tax">CBS → Fisco</span>
              <strong className="tax">{brl(r.cbs)}</strong>
            </div>
            <div className="linha">
              <span className="tax">IBS → Fisco</span>
              <strong className="tax">{brl(r.ibs)}</strong>
            </div>
          </>
        ) : null}
        <div className="linha total">
          <span>Destino recebe</span>
          <strong>{brl(r.liquido)}</strong>
        </div>
      </div>
      <p className="nota">
        {r.split
          ? "Estimativa. No pagamento real, o banco separa a CBS e o IBS que estão na nota fiscal. Os créditos das suas compras entram na apuração."
          : "Sem nota de empresa, não há split: transferências entre contas chegam cheias."}
      </p>
    </div>
  );
}

type Tema = "dark" | "light";

function useTema(): [Tema, () => void] {
  const [tema, setTema] = useState<Tema>("dark");
  useEffect(() => {
    setTema(document.documentElement.dataset.theme === "light" ? "light" : "dark");
  }, []);
  const alternar = () => {
    const novo: Tema = tema === "dark" ? "light" : "dark";
    setTema(novo);
    document.documentElement.dataset.theme = novo;
    try {
      localStorage.setItem("astro-tema", novo);
    } catch {
      /* sem storage: o tema vale só nesta visita */
    }
  };
  return [tema, alternar];
}

export default function Home() {
  const [scrolled, setScrolled] = useState(false);
  const [faq, setFaq] = useState<number | null>(null);
  const [tema, alternarTema] = useTema();
  useReveal();
  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 8);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  const faqs: [string, string][] = [
    [
      "Serve para mim ou para minha empresa?",
      "Para os dois. Pessoa física tem conta, Pix e cartão — transferências nunca têm retenção. Empresa (PJ) cobra com a nota fiscal e recebe o pagamento já com a CBS e o IBS da nota separados.",
    ],
    [
      "O que é o split de IBS/CBS?",
      "É a divisão do pagamento prevista na Reforma (LC 214/2025): quando um cliente paga uma venda com nota fiscal, o banco separa a CBS e o IBS destacados na nota e os envia ao Fisco; a empresa recebe o líquido. Transferência comum (sócio, reembolso, empréstimo) não tem split. Em 2027 o split é opcional e, a partir de 2028, obrigatório no B2B.",
    ],
    [
      "As alíquotas são reais?",
      "Seguem a transição da Reforma: 2026 é ano-teste (CBS 0,9% + IBS 0,1%); em 2027–2028 a CBS fica cheia (≈8,8%) e o IBS segue em 0,1%; o IBS sobe aos poucos de 2029 a 2032 e chega ao pleno (≈17,7%) em 2033. As alíquotas de referência ainda serão fixadas oficialmente.",
    ],
    [
      "Como a empresa entra na conta?",
      "Como nos bancos digitais: cada pessoa entra com o próprio login e verificação facial e escolhe a empresa. O sócio que abre a conta (conferimos o CNPJ e o quadro de sócios na Receita) adiciona outras pessoas com papéis e alçadas; acima da alçada, outra pessoa aprova.",
    ],
    [
      "Precisa instalar algo?",
      "O app roda no celular (Android, via .apk) e também no navegador. O site é a vitrine para conhecer a plataforma e simular o split.",
    ],
  ];

  const feats: [keyof typeof ICONES, string, string][] = [
    ["nota", "Cobrança com nota", "Pix com QR dinâmico e boleto vinculados à NF-e. No pagamento, a CBS e o IBS da nota são separados."],
    ["raio", "Apuração quase pronta", "Cada recebimento chega conciliado com a nota e com o imposto separado. A apuração continua, mas sem garimpo."],
    ["carteira", "Fluxo de caixa sem susto", "O imposto da venda não fica no seu caixa esperando a guia: você recebe o líquido."],
    ["creditos", "Créditos acompanhados", "Veja os créditos de IBS/CBS das suas compras e a estimativa do que volta na apuração."],
    ["equipe", "Alçadas e dupla aprovação", "Cada pessoa com seu papel e limite. Acima da alçada, outra pessoa aprova com verificação facial."],
    ["recorrente", "Pix Automático e lote", "Cobranças recorrentes autorizadas uma vez, pagamentos em lote e webhooks para o seu ERP."],
  ];

  const passos: [string, string, string][] = [
    ["01", "Baixe ou abra", "No navegador agora, ou instale o app no Android (.apk)."],
    ["02", "Crie sua conta", "PF com biometria; empresa com certificado digital e-CNPJ."],
    ["03", "Receba já líquido", "O cliente paga a cobrança e o imposto da nota já sai separado: você recebe o líquido."],
  ];

  return (
    <>
      <nav className={`nav${scrolled ? " scrolled" : ""}`}>
        <div className="container">
          <a href="#" aria-label="Astro — início">
            <Logo />
          </a>
          <div className="nav-acoes">
            <a className="btn-text nav-simular" href="#calculadora">
              Simular split
            </a>
            <button
              type="button"
              className="icon-btn"
              onClick={alternarTema}
              aria-label={tema === "dark" ? "Usar tema claro" : "Usar tema escuro"}
              title={tema === "dark" ? "Tema claro" : "Tema escuro"}
            >
              <Icone nome={tema === "dark" ? "sol" : "lua"} />
            </button>
            <a className="btn btn-primary btn-sm" href="#comecar">
              Abrir conta
            </a>
          </div>
        </div>
      </nav>

      <main>
        {/* HERO */}
        <section style={{ paddingTop: 0 }}>
          <div className="container hero">
            <div className="reveal">
              <span className="label">Feito para a Reforma Tributária</span>
              <h1 className="h-hero">O imposto se resolve na hora da venda.</h1>
              <p className="lead">
                Conta digital para pessoas e empresas. Cobre com a nota fiscal e receba com a CBS e
                o IBS já separados no pagamento.
              </p>
              <div className="acoes">
                <a className="btn btn-primary" href="#comecar">
                  Abrir conta grátis
                </a>
                <a className="btn btn-secondary" href="#calculadora">
                  Ver na prática
                </a>
              </div>
            </div>
            <div className="hero-foto reveal">
              <img src="/fotos/pj.jpg" alt="Lojista recebendo um pagamento por aproximação" />
              <div className="hero-card">
                <div className="linha-topo">
                  Venda de {brl(10000)} com nota · alíquotas de 2033
                </div>
                <div className="split-bar" aria-hidden>
                  <div className="liq" style={{ width: "73.5%" }} />
                  <div className="tax" style={{ flex: 1 }} />
                </div>
                <div className="valores tabular">
                  <strong>Líquido {brl(7350)}</strong>
                  <span className="muted">IBS/CBS {brl(2650)}</span>
                </div>
                <div style={{ marginTop: 12 }}>
                  <span className="status ok">Pago · imposto separado no ato</span>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* DOIS PÚBLICOS */}
        <section className="sec-alt">
          <div className="container">
            <div className="sec-head reveal">
              <span className="label">Para você e para sua empresa</span>
              <h2 className="h-sec">Uma conta, dois mundos.</h2>
            </div>
            <div className="grid-2">
              <div className="card reveal">
                <div className="card-ico">
                  <Icone nome="pessoa" />
                </div>
                <h3 className="h-card">Pessoa física</h3>
                <p className="lead">
                  Conta e Pix sem mensalidade, cartão virtual e saldo que rende. Transferências
                  nunca têm retenção de imposto.
                </p>
              </div>
              <div className="card reveal">
                <div className="card-ico">
                  <Icone nome="empresa" />
                </div>
                <h3 className="h-card">Empresa (PJ)</h3>
                <p className="lead">
                  Cobra com a nota, recebe com o IBS/CBS separado no ato e acompanha os créditos
                  para a apuração. Do MEI à indústria.
                </p>
              </div>
            </div>
          </div>
        </section>

        {/* DIFERENCIAL B2B */}
        <section>
          <div className="container">
            <div className="sec-head reveal">
              <span className="label">Para empresas</span>
              <h2 className="h-sec">A Reforma vira vantagem no seu caixa.</h2>
              <p className="lead">
                Montadoras, autopeças e indústria acumulam crédito de IBS/CBS nas compras de insumo.
                A Astro separa o imposto de cada venda pela nota e mostra os créditos que entram na
                apuração — preparada para o split da LC 214/2025.
              </p>
            </div>
            <div className="grid-3">
              {feats.map(([ic, t, d]) => (
                <div className="card reveal" key={t}>
                  <div className="card-ico">
                    <Icone nome={ic} />
                  </div>
                  <h3 className="h-card">{t}</h3>
                  <p className="lead">{d}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* CALCULADORA */}
        <section id="calculadora" className="sec-alt">
          <div className="container calc-grid">
            <div className="reveal">
              <span className="label">Calculadora</span>
              <h2 className="h-sec" style={{ marginTop: 16 }}>
                Veja o split em tempo real.
              </h2>
              <p className="lead" style={{ marginTop: 16 }}>
                Digite um valor e escolha quem vende. É o mesmo motor de cálculo do app e do
                backend — CBS e IBS no cronograma oficial da Reforma.
              </p>
            </div>
            <div className="reveal">
              <Calculadora />
            </div>
          </div>
        </section>

        {/* COMO COMEÇAR */}
        <section id="comecar">
          <div className="container">
            <div className="sec-head reveal">
              <span className="label">Como começar</span>
              <h2 className="h-sec">Em três passos.</h2>
            </div>
            <div className="grid-3">
              {passos.map(([n, t, d]) => (
                <div className="card reveal" key={n}>
                  <div className="passo-num">{n}</div>
                  <h3 className="h-card">{t}</h3>
                  <p className="lead">{d}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* FAQ */}
        <section className="sec-alt">
          <div className="container">
            <div className="faq">
              <div className="sec-head reveal">
                <span className="label">Perguntas</span>
                <h2 className="h-sec">Dúvidas frequentes.</h2>
              </div>
              {faqs.map(([q, a], i) => (
                <div className="faq-item reveal" key={q}>
                  <button
                    className="faq-q"
                    aria-expanded={faq === i}
                    onClick={() => setFaq(faq === i ? null : i)}
                  >
                    {q}
                    <Icone nome={faq === i ? "menos" : "mais"} />
                  </button>
                  {faq === i ? <div className="faq-a">{a}</div> : null}
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* CTA */}
        <section>
          <div className="container">
            <div className="cta reveal">
              <Eclipse />
              <h2 className="h-sec">Pronto para o imposto certo, no ato?</h2>
              <p className="lead">Abra sua conta de pessoa ou empresa e receba já líquido.</p>
              <div className="acoes">
                <a className="btn btn-primary" href="#comecar">
                  Abrir conta grátis
                </a>
              </div>
            </div>
          </div>
        </section>
      </main>

      <footer>
        <div className="container">
          <Logo />
          <span>© {new Date().getFullYear()} Astro · Split de IBS/CBS · Projeto acadêmico</span>
        </div>
      </footer>
    </>
  );
}
