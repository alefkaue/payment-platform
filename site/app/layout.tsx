import "./globals.css";
import type { Metadata } from "next";
import type { ReactNode } from "react";

export const metadata: Metadata = {
  title: "Astro — Pagamentos com split de IBS/CBS",
  description:
    "Banco digital para pessoas e empresas, feito para a Reforma Tributária: o IBS/CBS é separado no ato e abatido pelos créditos. Para empresas, recebimento já líquido.",
  icons: {
    icon: [{ url: "/favicon.svg", type: "image/svg+xml" }, { url: "/favicon.ico" }],
    apple: "/apple-touch-icon.png",
  },
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="pt-BR" suppressHydrationWarning>
      <head>
        {/* Aplica o tema salvo antes da pintura (padrão da marca: escuro). */}
        <script
          dangerouslySetInnerHTML={{
            __html:
              "try{if(localStorage.getItem('astro-tema')==='light')document.documentElement.dataset.theme='light'}catch(e){}",
          }}
        />
        <meta name="theme-color" content="#0A0A0A" />
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
        <link
          href="https://fonts.googleapis.com/css2?family=Instrument+Sans:wght@400;500;600&family=Unbounded:wght@500;600&display=swap"
          rel="stylesheet"
        />
      </head>
      <body>{children}</body>
    </html>
  );
}
