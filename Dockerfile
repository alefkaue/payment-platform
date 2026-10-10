# Backend de DEMONSTRAÇÃO da Astro para deploy gratuito (Render: "Public Git
# Repository" com as opções padrão, ou o render.yaml desta pasta).
# - Sem TensorFlow: biometria em modo teste (aprova o rosto), CNPJ sem consulta.
# - DEPOSITO_DEMO: o botão Depositar do app coloca dinheiro de teste.
# - Segredos e CORS_ORIGINS (URL exata do app, sem curinga) vêm do ambiente; sem
#   eles o entrypoint não sobe (ver backend/entrypoint-demo.sh e render.yaml).
# Produção de verdade: backend/Dockerfile (com DeepFace) e AMBIENTE=producao.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    AMBIENTE=desenvolvimento \
    BIOMETRIA_STUB=1 \
    CNPJ_PROVEDOR=stub \
    DEPOSITO_DEMO=1

WORKDIR /app
COPY backend/requirements-demo.txt .
RUN pip install --no-cache-dir -r requirements-demo.txt

COPY backend/app ./app
COPY backend/alembic ./alembic
COPY backend/alembic.ini .
COPY backend/entrypoint-demo.sh .
RUN chmod +x entrypoint-demo.sh \
    && useradd --create-home --uid 10001 astro \
    && chown -R astro:astro /app
USER astro

EXPOSE 8000
ENTRYPOINT ["./entrypoint-demo.sh"]
