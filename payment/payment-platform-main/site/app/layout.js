import "./globals.css";

export const metadata = {
  title: "PayFlow — Pagamentos com split de IBS/CBS",
  description:
    "Plataforma de pagamentos brasileira com split automático de IBS/CBS da Reforma Tributária. Para empresas, o imposto vai ao Governo e o líquido cai na conta, no ato.",
};

export default function RootLayout({ children }) {
  return (
    <html lang="pt-BR">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
        <link
          href="https://fonts.googleapis.com/css2?family=Instrument+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500&display=swap"
          rel="stylesheet"
        />
      </head>
      <body>{children}</body>
    </html>
  );
}
