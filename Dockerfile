FROM python:3.10-slim

# Instalar ffmpeg y dependencias del sistemañ
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copiar requerimientos e instalar
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el resto del código
COPY . .

ENV PORT=10000
EXPOSE 10000

CMD ["python", "app.py"]
