FROM python:3.11-slim

# Instalar ffmpeg, nodejs y ca-certificates
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    nodejs \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copiar requerimientos e instalar
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el proyecto completo
COPY . .

ENV PORT=10000
EXPOSE 10000

CMD ["python", "app.py"]
