FROM python:3.12-slim

# opencv-python (usado pelo DeepFace para MFA facial) precisa de libs nativas que a
# imagem slim não traz. Sem isso o container derruba na primeira requisição de
# biometria com "ImportError: libGL.so.1".
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 \
        libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Opcional: baixar os pesos do DeepFace durante o BUILD (em vez da 1ª requisição).
# Descomente se o build tiver internet para github.com:
# RUN python -c "from deepface import DeepFace; \
#     DeepFace.build_model('Facenet', task='facial_recognition'); \
#     DeepFace.build_model('Fasnet', task='spoofing')"

COPY app ./app
COPY alembic ./alembic
COPY alembic.ini .
COPY entrypoint.sh .
RUN chmod +x entrypoint.sh

# Roda como usuário SEM privilégio (item #17 da auditoria: antes rodava como root).
# O cache dos pesos do DeepFace fica em /home/payflow/.deepface -- por isso o HOME
# precisa pertencer ao usuário.
RUN useradd --create-home --uid 10001 payflow \
    && chown -R payflow:payflow /app
USER payflow
ENV HOME=/home/payflow

EXPOSE 8000

ENTRYPOINT ["./entrypoint.sh"]
