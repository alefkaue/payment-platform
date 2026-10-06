"use client";

import { useEffect, useState, type CSSProperties } from "react";

type Tipo = "PF" | "PJ";
type Vigencia = "2026" | "2027";

const ALIQUOTAS: Record<Vigencia, { cbs: number; ibs: number; rotulo: string }> = {
  "2026": { cbs: 0.009, ibs: 0.001, rotulo: "2026 (fase de teste)" },
  "2027": { cbs: 0.088, ibs: 0.177, rotulo: "2027+ (regime cheio)" },
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

function calcularSplit(valor: string | number, tipo: Tipo, vigencia: Vigencia) {
  const v = Math.round(Number(valor || 0) * 100) / 100;
  if (tipo !== "PJ") return { bruto: v, cbs: 0, ibs: 0, liquido: v, split: false };
  const a = ALIQUOTAS[vigencia];
  const cbs = Math.round(v * a.cbs * 100) / 100;
  const ibs = Math.round(v * a.ibs * 100) / 100;
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
  const [vig, setVig] = useState<Vigencia>("2027");
  const r = calcularSplit(valor, tipo, vig);
  const pLiq = r.bruto > 0 ? (r.liquido / r.bruto) * 100 : 100;
  return (
    <div className="card">
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
        <div>
          <label className="eyebrow">Valor</label>
          <input inputMode="decimal" value={valor} onChange={(e) => setValor(e.target.value)} />
        </div>
        <div>
          <label className="eyebrow">Destino</label>
          <select value={tipo} onChange={(e) => setTipo(e.target.value as Tipo)}>
            <option value="PF">Pessoa (PF)</option>
            <option value="PJ">Empresa (PJ)</option>
          </select>
        </div>
      </div>
      <div style={{ marginTop: 14 }}>
        <label className="eyebrow">Vigência</label>
        <select value={vig} onChange={(e) => setVig(e.target.value as Vigencia)}>
          {(Object.entries(ALIQUOTAS) as [Vigencia, (typeof ALIQUOTAS)[Vigencia]][]).map(([k, a]) => (
            <option key={k} value={k}>
              {a.rotulo}
            </option>
          ))}
        </select>
      </div>
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
          Pessoa física não sofre retenção — recebe o valor cheio.
        </p>
      ) : (
        <p className="lead" style={{ fontSize: 14, marginTop: 8 }}>
          Na empresa, o imposto pode ser abatido pelos créditos de IBS/CBS acumulados nas compras.
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
      "Para os dois. Pessoa física tem conta, Pix, cartão, loja e viagens — sem retenção de imposto. Empresa (PJ) recebe com o IBS/CBS separado no ato e ainda usa os créditos tributários para abater o que deve.",
    ],
    [
      "O que é o split de IBS/CBS?",
      "É a divisão automática do pagamento prevista na Reforma (LC 214/2025): quando o destino é uma empresa, o imposto é separado no momento da liquidação e vai ao Fisco; a empresa recebe o líquido. No B2B, o split é inteligente — consulta seus créditos antes de reter.",
    ],
    [
      "As alíquotas são reais?",
      "Seguem o cronograma da Reforma: 2026 é fase de teste (CBS 0,9% + IBS 0,1%) e 2027+ é o regime cheio (CBS 8,8% + IBS 17,7% ≈ 26,5%).",
    ],
    [
      "Como a empresa entra na conta?",
      "Depende do porte. MEI usa biometria do titular. Pequenas, médias e grandes usam certificado digital e-CNPJ (ICP-Brasil) — o mesmo que assina a nota fiscal — com múltiplos assinantes e dupla autorização por alçada.",
    ],
    [
      "Precisa instalar algo?",
      "O app roda no celular (Android, via .apk) e também no navegador. O site é a vitrine para conhecer a plataforma e simular o split.",
    ],
  ];

  const feats: [string, string, string][] = [
    ["🪙", "Créditos de IBS/CBS", "O crédito das suas compras abate o imposto das vendas em tempo real — não fica preso para recuperar depois."],
    ["⚡", "Apuração automática", "O imposto é calculado e separado em cada venda. Sem fechamento mensal, sem contador apurando depois."],
    ["🛡️", "Fluxo de caixa protegido", "O dinheiro do imposto nunca passa pelo seu caixa. Você recebe o líquido e não precisa provisionar."],
    ["🧾", "Contas a pagar e receber", "Faturas B2B conciliadas com a NF-e, a receber e a pagar, dentro do mesmo app."],
    ["🔐", "Acesso por e-CNPJ", "Certificado digital ICP-Brasil, múltiplos assinantes e dupla autorização por alçada."],
    ["📊", "Pronta para o porte", "Do MEI (biometria) à grande empresa (certificado + maker-checker)."],
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
              O banco onde o imposto se resolve sozinho.
            </h1>
            <p className="lead" style={{ marginTop: 18, maxWidth: "52ch" }}>
              Conta digital para pessoas e empresas. No B2B, o IBS/CBS é separado no ato e abatido
              pelos seus créditos — sem planilha, sem apuração depois.
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
                Recebimento de {brl(10000)} · empresa
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
                Conta e Pix sem mensalidade, cartão, loja e viagens com pontos. O imposto já vem
                embutido — você nunca sofre retenção.
              </p>
            </div>
            <div className="card reveal">
              <div className="feat-ico">🏭</div>
              <h3 style={{ fontSize: 22, fontWeight: 600 }}>Empresa (PJ)</h3>
              <p className="lead" style={{ marginTop: 10, fontSize: 16 }}>
                Recebe com o IBS/CBS separado no ato, usa os créditos tributários para abater o
                imposto e zera a apuração. Do MEI à indústria.
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
            PayFlow usa esse crédito automaticamente — o split inteligente da LC 214/2025.
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
                ["3 · Receba já líquido", "O split acontece sozinho — o imposto nunca passa pelo seu caixa."],
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
