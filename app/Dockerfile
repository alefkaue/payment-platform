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
# Usa node + npm (igual ao time). O bun.lock do repo está defasado dos overrides
# do package.json; o package-lock.json é o lockfile autoritativo e atual.
FROM node:22-alpine AS build
WORKDIR /app

# Camada de dependências (cacheia enquanto o lock não muda).
COPY package.json package-lock.json ./
RUN npm ci

# Código e build.
COPY . .
# Padrão: stack LOCAL integrado — modo development apontando para a API em
# http://localhost:8000 (o modo production do app EXIGE HTTPS, impossível em
# localhost puro). Para o deploy real (VPC/Azure com HTTPS), builde em produção:
#   --build-arg VITE_MODE=production --build-arg VITE_API_URL=https://sua-api.exemplo
# Ou em produção só-demonstração (mocks, sem backend):
#   --build-arg VITE_MODE=production --build-arg VITE_MODO_DEMO=1 --build-arg VITE_API_URL=
ARG VITE_MODE=development
ARG VITE_MODO_DEMO=0
ARG VITE_API_URL=http://localhost:8000
ENV VITE_MODE=${VITE_MODE} VITE_MODO_DEMO=${VITE_MODO_DEMO} VITE_API_URL=${VITE_API_URL}
# vite build direto com o modo escolhido (npm run build fixaria produção).
RUN npx --no-install vite build --mode ${VITE_MODE}

# Correção de ordem de scripts: o shell tem o bundle como <script type="module"
# async>, que, com o JS em cache, roda ANTES do script inline que cria window.$_TSR
# (hidratação) -> "Cannot set properties of undefined". Sem async, o módulo é
# deferido e roda depois do inline. Mantém a página de renderizar.
RUN sed -i 's/ async=""//g' dist/client/_shell.html
RUN node scripts/cabecalhos-container.mjs

# ---- runtime ----
# nginx-unprivileged: roda como usuário sem privilégio (uid 101) na porta 8080.
FROM nginxinc/nginx-unprivileged:1.27-alpine AS runtime
COPY --chown=nginx:nginx nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build --chown=nginx:nginx /app/dist/client /usr/share/nginx/html
COPY --from=build /app/security-headers.conf /etc/nginx/security-headers.conf
EXPOSE 8080
