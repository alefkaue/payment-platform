FROM python:3.12-slim

# opencv-python (usado pelo DeepFace para MFA facial) precisa de libs nativas que
# a imagem slim não traz por padrão. Sem isso o container derruba na primeira
# requisição de biometria com "ImportError: libGL.so.1: cannot open shared object
# file: No such file or directory" ao importar cv2.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 \
        libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Opcional: baixar os pesos do DeepFace (Facenet + anti-spoofing, ~100MB) durante o
# BUILD da imagem, em vez de na primeira requisição em runtime. Deixa o container
# pronto para uso offline depois de buildado, e evita que o primeiro usuário pague
# esse tempo de download. Descomente se o ambiente de build tiver internet liberada
# para github.com / release-assets.githubusercontent.com:
# RUN python -c "from deepface import DeepFace; \
#     DeepFace.build_model('Facenet', task='facial_recognition'); \
#     DeepFace.build_model('Fasnet', task='spoofing')"

COPY app ./app

EXPOSE 8000

# Em Azure Container Apps / App Service, a porta costuma vir na variável $PORT.
# Aqui mantemos 8000 fixo por simplicidade para a entrega de sexta.
#
# Sem o RUN comentado acima, o primeiro POST /usuarios ou /pagamentos/transferir
# feito ao container vai demorar mais (baixa os pesos do modelo na hora) -- as
# chamadas seguintes usam o cache em /root/.deepface e ficam no tempo normal (~3-6s).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
