FROM python:3.11-slim

# Instalar ffmpeg, git y nodejs necesarios para yt-dlp
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg git nodejs \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Forzar la última versión de yt-dlp
RUN pip install --no-cache-dir --upgrade yt-dlp

COPY app.py .
COPY youtube_uploader.py .

# Comando seguro para Gunicorn con el puerto dinámico de Render
CMD gunicorn app:app --bind 0.0.0.0:${PORT:-10000} --workers 1 --threads 8 --timeout 120
