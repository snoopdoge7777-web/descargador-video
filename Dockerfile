FROM python:3.11-slim

# Instalar ffmpeg y git obligatorios para yt-dlp
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir --upgrade yt-dlp gunicorn

COPY . .

CMD ["python", "-m", "gunicorn", "app:app", "--bind", "0.0.0.0:10000", "--workers", "1", "--threads", "8", "--timeout", "120"]
