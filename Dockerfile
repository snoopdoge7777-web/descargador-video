FROM python:3.11-slim

# Instalar ffmpeg, git y nodejs (necesario para que yt-dlp resuelva los desafíos de JavaScript de YouTube)
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg git nodejs \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Forzar siempre la última versión de yt-dlp
RUN pip install --no-cache-dir --upgrade yt-dlp

COPY app.py .
COPY youtube_uploader.py .

# Render inyecta la variable PORT automáticamente y Gunicorn levanta la app de producción
CMD sh -c "gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --threads 8 --timeout 120"
