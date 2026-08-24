FROM python:3.11-slim

# Instalar dependencias del sistema incluyendo Node.js y ffmpeg
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg git nodejs \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Forzar la última versión de yt-dlp
RUN pip install --no-cache-dir --upgrade yt-dlp

COPY app.py .
COPY youtube_uploader.py .

# Comando de inicio con Gunicorn y el puerto dinámico de Render
CMD sh -c "gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --threads 8 --timeout 120"
