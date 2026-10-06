"use client";

import { useEffect, useState, type CSSProperties } from "react";

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

function Wordmark({ cor }: { cor?: string }) {
  return (
    <span className="wordmark" style={cor ? { color: cor } : undefined}>
      payfl<span className="ball" />w
    </span>
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
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
        <div>
          <label className="eyebrow">Valor</label>
          <input inputMode="decimal" value={valor} onChange={(e) => setValor(e.target.value)} />
        </div>
        <div>
          <label className="eyebrow">Quem vende</label>
          <select value={tipo} onChange={(e) => setTipo(e.target.value as Tipo)}>
            <option value="PF">Pessoa (PF)</option>
            <option value="PJ">Empresa com nota (PJ)</option>
          </select>
        </div>
      </div>
      <div style={{ marginTop: 14 }}>
        <label className="eyebrow">Ano</label>
        <select value={vig} onChange={(e) => setVig(e.target.value as Vigencia)}>
          {(Object.entries(ALIQUOTAS) as [Vigencia, (typeof ALIQUOTAS)[Vigencia]][]).map(([k, a]) => (
            <option key={k} value={k}>
              {a.rotulo}
            </option>
          ))}
        </select>
      </div>
      {tipo === "PJ" ? (
        <div style={{ marginTop: 14 }}>
          <label className="eyebrow">Regime do setor</label>
          <select value={regime} onChange={(e) => setRegime(e.target.value as Regime)}>
            {(Object.entries(REGIMES) as [Regime, (typeof REGIMES)[Regime]][]).map(([k, g]) => (
              <option key={k} value={k}>
                {g.rotulo}
              </option>
            ))}
          </select>
        </div>
      ) : null}
      <div className="split-bar" style={{ marginTop: 22 }}>
        <div className="liq" style={{ width: `${pLiq}%` }} />
        <div className="tax" style={{ flex: 1 }} />
      </div>
      <div style={{ marginTop: 18 }}>
        <div className="linha">
          <span>Bruto</span>
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
        <div className="linha" style={{ borderBottom: "none" }}>
          <span>Destino recebe</span>
          <strong>{brl(r.liquido)}</strong>
        </div>
      </div>
      {!r.split ? (
        <p className="lead" style={{ fontSize: 14, marginTop: 8 }}>
          Sem nota de empresa, não há split: transferências entre contas chegam cheias.
        </p>
      ) : (
        <p className="lead" style={{ fontSize: 14, marginTop: 8 }}>
          Estimativa. No pagamento real, o banco separa a CBS e o IBS que estão na nota fiscal.
          Os créditos das suas compras entram na apuração.
        </p>
      )}
    </div>
  );
}

export default function Home() {
  const [scrolled, setScrolled] = useState(false);
  const [faq, setFaq] = useState<number | null>(null);
  useReveal();
  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 8);
    window.addEventListener("scroll", onScroll);
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

  const feats: [string, string, string][] = [
    ["🧾", "Cobrança com nota", "Pix com QR dinâmico e boleto vinculados à NF-e. No pagamento, a CBS e o IBS da nota são separados."],
    ["⚡", "Apuração quase pronta", "Cada recebimento chega conciliado com a nota e com o imposto separado. A apuração continua, mas sem garimpo."],
    ["🛡️", "Fluxo de caixa sem susto", "O imposto da venda não fica no seu caixa esperando a guia: você recebe o líquido."],
    ["🪙", "Créditos acompanhados", "Veja os créditos de IBS/CBS das suas compras e a estimativa do que volta na apuração."],
    ["🔐", "Alçadas e dupla aprovação", "Cada pessoa com seu papel e limite. Acima da alçada, outra pessoa aprova com verificação facial."],
    ["🔁", "Pix Automático e lote", "Cobranças recorrentes autorizadas uma vez, pagamentos em lote e webhooks para o seu ERP."],
  ];

  const cardWhite: CSSProperties = { background: "#fff" };

  return (
    <>
      <nav className={`nav${scrolled ? " scrolled" : ""}`}>
        <div className="container">
          <Wordmark />
          <div>
            <a className="btn btn-line" href="#calculadora">
              Simular split
            </a>
            <a className="btn btn-ink" href="#comecar">
              Abrir conta
            </a>
          </div>
        </div>
      </nav>

      {/* HERO */}
      <section>
        <div className="container hero">
          <div className="reveal">
            <span className="chip">
              <span className="dot-gold" /> Feito para a Reforma Tributária
            </span>
            <h1 className="h-hero" style={{ marginTop: 16 }}>
              O banco onde o imposto se resolve na hora da venda.
            </h1>
            <p className="lead" style={{ marginTop: 18, maxWidth: "52ch" }}>
              Conta digital para pessoas e empresas. Cobre com a nota fiscal e receba com a CBS e o
              IBS já separados no pagamento — o imposto resolvido na hora da venda.
            </p>
            <div style={{ marginTop: 28 }}>
              <a className="btn btn-gold" href="#comecar">
                Abrir conta grátis
              </a>
              <a className="btn btn-line" href="#calculadora">
                Ver na prática
              </a>
            </div>
          </div>
          <div className="hero-foto reveal">
            <img src="/fotos/pj.jpg" alt="Logística e indústria" />
            <div className="hero-card">
              <div style={{ fontSize: 13, color: "var(--mut2)", marginBottom: 8 }}>
                Venda de {brl(10000)} com nota · alíquotas de 2033
              </div>
              <div className="split-bar">
                <div className="liq" style={{ width: "73.5%" }} />
                <div className="tax" style={{ flex: 1 }} />
              </div>
              <div
                style={{ display: "flex", justifyContent: "space-between", marginTop: 10, fontSize: 13 }}
              >
                <strong style={{ color: "var(--pos)" }}>Líquido {brl(7350)}</strong>
                <span style={{ color: "var(--taxt)" }}>IBS/CBS {brl(2650)}</span>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* DOIS PÚBLICOS */}
      <section className="sec-tint">
        <div className="container">
          <span className="eyebrow reveal">Para você e para sua empresa</span>
          <h2 className="h-sec reveal" style={{ marginTop: 10, marginBottom: 32 }}>
            Um banco, dois mundos.
          </h2>
          <div className="grid-2">
            <div className="card reveal">
              <div className="feat-ico">🙂</div>
              <h3 style={{ fontSize: 22, fontWeight: 600 }}>Pessoa física</h3>
              <p className="lead" style={{ marginTop: 10, fontSize: 16 }}>
                Conta e Pix sem mensalidade, cartão virtual e saldo que rende. Transferências
                nunca têm retenção de imposto.
              </p>
            </div>
            <div className="card reveal">
              <div className="feat-ico">🏭</div>
              <h3 style={{ fontSize: 22, fontWeight: 600 }}>Empresa (PJ)</h3>
              <p className="lead" style={{ marginTop: 10, fontSize: 16 }}>
                Cobra com a nota, recebe com o IBS/CBS separado no ato e acompanha os créditos
                para a apuração. Do MEI à indústria.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* DIFERENCIAL B2B (ESCURO) */}
      <section className="sec-escuro">
        <div className="container">
          <span className="eyebrow reveal">Para empresas</span>
          <h2 className="h-sec reveal" style={{ marginTop: 10, marginBottom: 12 }}>
            A Reforma vira vantagem no seu caixa.
          </h2>
          <p className="lead reveal" style={{ marginBottom: 32, maxWidth: "60ch" }}>
            Montadoras, autopeças e indústria acumulam crédito de IBS/CBS nas compras de insumo. O
            PayFlow separa o imposto de cada venda pela nota e mostra os créditos que entram na
            apuração — preparado para o split da LC 214/2025.
          </p>
          <div className="grid-3">
            {feats.map(([ic, t, d]) => (
              <div className="card reveal" key={t}>
                <div className="feat-ico">{ic}</div>
                <h3 style={{ fontSize: 19, fontWeight: 600 }}>{t}</h3>
                <p className="lead" style={{ marginTop: 8, fontSize: 15 }}>
                  {d}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* CALCULADORA */}
      <section id="calculadora">
        <div
          className="container"
          style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 48, alignItems: "center" }}
        >
          <div className="reveal">
            <span className="eyebrow">Calculadora</span>
            <h2 className="h-sec" style={{ marginTop: 10 }}>
              Veja o split em tempo real.
            </h2>
            <p className="lead" style={{ marginTop: 16 }}>
              Digite um valor e escolha o destino. É o mesmo motor de cálculo do app e do backend —
              CBS e IBS no cronograma oficial da Reforma.
            </p>
          </div>
          <div className="reveal">
            <Calculadora />
          </div>
        </div>
      </section>

      {/* COMO COMEÇAR */}
      <section id="comecar" className="sec-tint">
        <div className="container">
          <span className="eyebrow reveal">Como começar</span>
          <h2 className="h-sec reveal" style={{ marginTop: 10, marginBottom: 32 }}>
            Em três passos.
          </h2>
          <div className="grid-3">
            {(
              [
                ["1 · Baixe ou abra", "No navegador agora, ou instale o app no Android (.apk)."],
                ["2 · Crie sua conta", "PF com biometria; empresa com certificado digital e-CNPJ."],
                ["3 · Receba já líquido", "O cliente paga a cobrança e o imposto da nota já sai separado: você recebe o líquido."],
              ] as [string, string][]
            ).map(([t, d]) => (
              <div className="card reveal" key={t} style={cardWhite}>
                <h3 style={{ fontSize: 20, fontWeight: 600 }}>{t}</h3>
                <p className="lead" style={{ marginTop: 10, fontSize: 16 }}>
                  {d}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* FAQ */}
      <section>
        <div className="container" style={{ maxWidth: 820 }}>
          <span className="eyebrow reveal">Perguntas</span>
          <h2 className="h-sec reveal" style={{ marginTop: 10, marginBottom: 24 }}>
            Dúvidas frequentes.
          </h2>
          {faqs.map(([q, a], i) => (
            <div className="faq-item reveal" key={i}>
              <button className="faq-q" onClick={() => setFaq(faq === i ? null : i)}>
                {q}
                <span>{faq === i ? "–" : "+"}</span>
              </button>
              {faq === i ? <div className="faq-a">{a}</div> : null}
            </div>
          ))}
        </div>
      </section>

      {/* CTA */}
      <section style={{ paddingTop: 0 }}>
        <div className="container">
          <div className="cta-bloco reveal">
            <h2 className="h-sec" style={{ color: "var(--onp)" }}>
              Pronto para o imposto certo, no ato?
            </h2>
            <p className="lead" style={{ color: "#c2bfb6", marginTop: 14 }}>
              Abra sua conta de pessoa ou empresa e receba já líquido.
            </p>
            <a className="btn btn-gold" style={{ marginTop: 24 }} href="#">
              Abrir conta grátis
            </a>
          </div>
        </div>
      </section>

      <footer>
        <div
          className="container"
          style={{ display: "flex", justifyContent: "space-between", flexWrap: "wrap", gap: 12 }}
        >
          <Wordmark />
          <span>© {new Date().getFullYear()} PayFlow · Split de IBS/CBS · Projeto acadêmico</span>
        </div>
      </footer>
    </>
  );
}
