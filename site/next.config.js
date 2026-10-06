/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Permite exportar como site estático (next build && next export) para hospedar
  // em qualquer lugar (Azure Static Web Apps, GitHub Pages, etc.).
  output: "standalone",
};

module.exports = nextConfig;
