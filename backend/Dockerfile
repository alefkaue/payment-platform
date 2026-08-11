FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

EXPOSE 8000

# Em Azure Container Apps / App Service, a porta costuma vir na variável $PORT.
# Aqui mantemos 8000 fixo por simplicidade para a entrega de sexta.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
