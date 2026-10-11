# Imagem do FRONTEND (SPA Vite) servido por nginx sem privilégio.
# Build feito dentro do container (não exige bun/node na máquina).
#
# O build de produção EXIGE VITE_API_URL (o vite.config trava deploy sem API —
# ver app/vite.config). Passe pela --build-arg na hora do build:
#   docker build -t matheussousaavelino/payment-platform-app:<tag> \
#     --build-arg VITE_API_URL=https://sua-api.exemplo .
#
# Nenhum segredo entra na imagem: VITE_API_URL é só a URL pública da API.

# ---- build ----
FROM oven/bun:1-alpine AS build
WORKDIR /app

# Camada de dependências (cacheia enquanto o lock não muda).
# Sem --frozen-lockfile: o bun.lock do repo está defasado do package.json
# (overrides). O build resolve as dependências; não altera o repositório.
COPY package.json bun.lock bunfig.toml ./
RUN bun install

# Código e build. VITE_API_URL é injetada no bundle em tempo de build.
COPY . .
# VITE_MODE=development aceita API em http://localhost (desenvolvimento).
# Para produção com HTTPS (ex.: deploy na Azure/VPS), builde assim:
#   --build-arg VITE_MODE=production --build-arg VITE_API_URL=https://sua-api
ARG VITE_API_URL=http://localhost:8000
ARG VITE_MODE=development
ENV VITE_API_URL=${VITE_API_URL}
# Chama o vite direto (o script "build" chama `node`, que não existe na imagem bun).
RUN bunx vite build --mode ${VITE_MODE}

# ---- runtime ----
# nginx-unprivileged: roda como usuário sem privilégio (uid 101) na porta 8080.
FROM nginxinc/nginx-unprivileged:1.27-alpine AS runtime
COPY --chown=nginx:nginx nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build --chown=nginx:nginx /app/dist/client /usr/share/nginx/html
EXPOSE 8080
