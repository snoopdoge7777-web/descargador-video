FROM python:3.11-slim

# Instalar ffmpeg, git y Node.js (necesario para resolver los desafíos de JavaScript de YouTube)
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg git nodejs \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Forzar siempre la última versión de yt-dlp
RUN pip install --no-cache-dir --upgrade yt-dlp

COPY app.py .
COPY youtube_uploader.py .

# Render/Railway inyectan la variable PORT automáticamente
CMD ["python", "app.py"]
