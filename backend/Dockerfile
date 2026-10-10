# Backend de PRODUÇÃO da Astro (Azure Container Apps, ver infra/azure e AZURE.md).
# O Dockerfile da raiz é o de demonstração (Render); este não liga nenhum modo de teste.
FROM python:3.12-slim

# - libgl1 / libglib2.0-0: OpenCV e MediaPipe (sem elas: "ImportError: libGL.so.1").
# - tesseract-ocr + idioma por: OCR dos documentos do KYC (DOCUMENTO_PROVEDOR=tesseract).
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
        libgl1 \
        libglib2.0-0 \
        tesseract-ocr \
        tesseract-ocr-por \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    AMBIENTE=producao \
    BIOMETRIA_MOTOR=opencv \
    DOCUMENTO_PROVEDOR=tesseract \
    MODELOS_DIR=/opt/astro/modelos

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Modelos da biometria baixados NO BUILD e conferidos pelo SHA-256 fixado em
# app/core/modelos.py. Em runtime MODELOS_DOWNLOAD=0: o container nunca baixa nada.
# A pasta fica do root e só leitura para o usuário da API (modelo trocado = não carrega).
COPY app ./app
RUN AMBIENTE=desenvolvimento python -m app.core.modelos baixar \
    && chmod -R a-w /opt/astro/modelos
ENV MODELOS_DOWNLOAD=0

COPY scripts ./scripts
COPY alembic ./alembic
COPY alembic.ini entrypoint.sh ./

# Usuário sem privilégio e código só leitura: uma falha na API não reescreve a própria API.
RUN useradd --create-home --uid 10001 astro \
    && chmod 0555 entrypoint.sh
USER astro
ENV HOME=/home/astro

EXPOSE 8000

ENTRYPOINT ["./entrypoint.sh"]
