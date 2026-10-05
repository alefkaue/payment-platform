"use client";

import { useEffect, useRef, useState } from "react";

const ALIQUOTAS = {
  "2026": { cbs: 0.009, ibs: 0.001, rotulo: "2026 (teste)" },
  "2027": { cbs: 0.088, ibs: 0.177, rotulo: "2027+ (cheia)" },
};

const brl = (n) => Number(n || 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });

function Wordmark({ cor }) {
  return (
    <span className="wordmark" style={cor ? { color: cor } : undefined}>
      payfl<span className="ball" />w
    </span>
  );
}

function calcularSplit(valor, tipo, vigencia) {
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
      (entries) => entries.forEach((e, i) => { if (e.isIntersecting) { setTimeout(() => e.target.classList.add("vis"), Math.min(i, 8) * 70); io.unobserve(e.target); } }),
      { threshold: 0.12, rootMargin: "0px 0px -8% 0px" }
    );
    els.forEach((el) => io.observe(el));
    return () => io.disconnect();
  }, []);
}

function Calculadora() {
  const [valor, setValor] = useState("1000");
  const [tipo, setTipo] = useState("PJ");
  const [vig, setVig] = useState("2026");
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
          <select value={tipo} onChange={(e) => setTipo(e.target.value)}>
            <option value="PF">Pessoa (PF)</option>
            <option value="PJ">Empresa (PJ)</option>
          </select>
        </div>
      </div>
      <div style={{ marginTop: 14 }}>
        <label className="eyebrow">Vigência</label>
        <select value={vig} onChange={(e) => setVig(e.target.value)}>
          {Object.entries(ALIQUOTAS).map(([k, a]) => <option key={k} value={k}>{a.rotulo}</option>)}
        </select>
      </div>
      <div className="split-bar" style={{ marginTop: 22 }}>
        <div className="liq" style={{ width: `${pLiq}%` }} />
        <div className="tax" style={{ flex: 1 }} />
      </div>
      <div style={{ marginTop: 18 }}>
        <div className="linha"><span>Bruto</span><strong>{brl(r.bruto)}</strong></div>
        {r.split ? (
          <>
            <div className="linha"><span className="tax">CBS → Governo</span><strong className="tax">{brl(r.cbs)}</strong></div>
            <div className="linha"><span className="tax">IBS → Governo</span><strong className="tax">{brl(r.ibs)}</strong></div>
          </>
        ) : null}
        <div className="linha" style={{ borderBottom: "none" }}><span>Destino recebe</span><strong>{brl(r.liquido)}</strong></div>
      </div>
      {!r.split ? <p className="lead" style={{ fontSize: 14, marginTop: 8 }}>Transferências para PF não têm retenção.</p> : null}
    </div>
  );
}

export default function Home() {
  const [scrolled, setScrolled] = useState(false);
  const [faq, setFaq] = useState(null);
  useReveal();
  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 8);
    window.addEventListener("scroll", onScroll);
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  const faqs = [
    ["O que é o split de IBS/CBS?", "É a divisão automática do pagamento: quando o destino é uma empresa (PJ), o imposto (CBS + IBS) é retido no ato e enviado à conta do Governo; a empresa recebe o valor líquido. Para pessoas físicas, não há retenção."],
    ["As alíquotas são reais?", "Seguem o cronograma da Reforma Tributária: 2026 é fase de teste (CBS 0,9% + IBS 0,1%) e 2027+ é a simulação cheia (CBS 8,8% + IBS 17,7%)."],
    ["Como funciona a segurança?", "Login com senha protegida e tokens JWT de curta duração com refresh rotativo. Transferências acima de um limite exigem verificação facial (selfie) com detecção de vivacidade."],
    ["Preciso instalar algo?", "O app roda no celular (Android). O site é para conhecer a plataforma e simular o split."],
  ];

  return (
    <>
      <nav className={`nav${scrolled ? " scrolled" : ""}`}>
        <div className="container">
          <Wordmark />
          <div>
            <a className="btn btn-line" href="#calculadora">Simular split</a>
            <a className="btn btn-ink" href="#comecar">Abrir conta</a>
          </div>
        </div>
      </nav>

      <section>
        <div className="container hero">
          <div className="reveal">
            <span className="eyebrow">Reforma Tributária · IBS/CBS</span>
            <h1 className="h-hero" style={{ marginTop: 12 }}>Pagamentos que já chegam com o imposto certo.</h1>
            <p className="lead" style={{ marginTop: 18, maxWidth: "52ch" }}>
              O PayFlow divide cada pagamento no ato: para empresas, o imposto vai direto
              ao Governo e o líquido cai na conta. Sem planilha, sem apuração depois.
            </p>
            <div style={{ marginTop: 28 }}>
              <a className="btn btn-ink" href="#comecar">Abrir conta</a>
              <a className="btn btn-line" href="#calculadora">Ver na prática</a>
            </div>
          </div>
          <div className="hero-foto reveal">
            <div className="hero-card">
              <div style={{ fontSize: 13, color: "var(--mut2)", marginBottom: 8 }}>Pagamento de {brl(1000)} para empresa</div>
              <div className="split-bar"><div className="liq" style={{ width: "99%" }} /><div className="tax" style={{ flex: 1 }} /></div>
              <div style={{ display: "flex", justifyContent: "space-between", marginTop: 10, fontSize: 13 }}>
                <span style={{ color: "var(--taxt)" }}>Imposto {brl(10)}</span>
                <strong>Líquido {brl(990)}</strong>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="sec-tint">
        <div className="container">
          <span className="eyebrow reveal">Recursos</span>
          <h2 className="h-sec reveal" style={{ marginTop: 10, marginBottom: 32 }}>Tudo resolvido no momento do pagamento.</h2>
          <div className="grid-3">
            {[
              ["Split automático", "CBS e IBS calculados e repassados ao Governo na hora, para destinos PJ."],
              ["Verificação facial", "Selfie com detecção de vivacidade para autorizar valores acima do limite."],
              ["Conta Governo", "Toda retenção fica rastreável numa conta de tesouro, com total por período."],
            ].map(([t, d]) => (
              <div className="card reveal" key={t}>
                <h3 style={{ fontSize: 20, fontWeight: 600 }}>{t}</h3>
                <p className="lead" style={{ marginTop: 10, fontSize: 16 }}>{d}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section id="calculadora">
        <div className="container" style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 48, alignItems: "center" }}>
          <div className="reveal">
            <span className="eyebrow">Calculadora</span>
            <h2 className="h-sec" style={{ marginTop: 10 }}>Veja o split em tempo real.</h2>
            <p className="lead" style={{ marginTop: 16 }}>
              Digite um valor e escolha o tipo de destino. O cálculo é o mesmo motor do
              backend (<code>split_service.py</code>).
            </p>
          </div>
          <div className="reveal"><Calculadora /></div>
        </div>
      </section>

      <section className="sec-escuro">
        <div className="container">
          <span className="eyebrow reveal">Segurança</span>
          <h2 className="h-sec reveal" style={{ marginTop: 10, marginBottom: 32 }}>Feito para dinheiro de verdade.</h2>
          <div className="grid-3">
            {[
              ["JWT + refresh", "Tokens curtos com rotação de refresh e detecção de reuso."],
              ["Biometria LGPD", "O rosto vira um vetor cifrado — a foto nunca é guardada."],
              ["Auditoria", "Cada login, cadastro e transferência fica registrado."],
              ["Rate-limit", "Tentativas de login e de selfie são limitadas por janela."],
              ["Dinheiro exato", "Valores em Decimal, split sem erro de centavo."],
              ["Idempotência", "Double-click não gera transferência duplicada."],
            ].map(([t, d]) => (
              <div className="card reveal" key={t}>
                <h3 style={{ fontSize: 18, fontWeight: 600 }}>{t}</h3>
                <p className="lead" style={{ marginTop: 8, fontSize: 15 }}>{d}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section id="comecar">
        <div className="container">
          <span className="eyebrow reveal">Como começar</span>
          <h2 className="h-sec reveal" style={{ marginTop: 10, marginBottom: 32 }}>Em três passos.</h2>
          <div className="grid-3">
            {[
              ["1 · Baixe o app", "Instale o PayFlow no seu Android (APK)."],
              ["2 · Crie sua conta", "PF ou PJ, com uma selfie de cadastro."],
              ["3 · Transfira", "O split acontece sozinho quando o destino é empresa."],
            ].map(([t, d]) => (
              <div className="card tintbg reveal" key={t}>
                <h3 style={{ fontSize: 20, fontWeight: 600 }}>{t}</h3>
                <p className="lead" style={{ marginTop: 10, fontSize: 16 }}>{d}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="sec-tint">
        <div className="container" style={{ maxWidth: 820 }}>
          <span className="eyebrow reveal">Perguntas</span>
          <h2 className="h-sec reveal" style={{ marginTop: 10, marginBottom: 24 }}>Dúvidas frequentes.</h2>
          {faqs.map(([q, a], i) => (
            <div className="faq-item reveal" key={i}>
              <button className="faq-q" onClick={() => setFaq(faq === i ? null : i)}>
                {q}<span>{faq === i ? "–" : "+"}</span>
              </button>
              {faq === i ? <div className="faq-a">{a}</div> : null}
            </div>
          ))}
        </div>
      </section>

      <section>
        <div className="container">
          <div className="cta-bloco reveal">
            <h2 className="h-sec" style={{ color: "var(--onp)" }}>Pronto para pagar com o imposto certo?</h2>
            <p className="lead" style={{ color: "#c2bfb6", marginTop: 14 }}>Abra sua conta e faça a primeira transferência hoje.</p>
            <a className="btn btn-ink" style={{ background: "var(--marca)", color: "#141414", marginTop: 24 }} href="#">Abrir conta</a>
          </div>
        </div>
      </section>

      <footer>
        <div className="container" style={{ display: "flex", justifyContent: "space-between", flexWrap: "wrap", gap: 12 }}>
          <Wordmark />
          <span>© {new Date().getFullYear()} PayFlow · Split de IBS/CBS · Projeto acadêmico</span>
        </div>
      </footer>
    </>
  );
}
