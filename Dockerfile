FROM python:3.11-slim

# ffmpeg no viene con Python, se instala del sistema.
# git también hace falta porque requirements.txt instala pytubefix
# directamente desde GitHub (git+https://...).
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .
COPY youtube_uploader.py .

# Render/Railway inyectan la variable PORT automáticamente
CMD ["python", "app.py"]
