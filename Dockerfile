FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg git nodejs \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN pip install --no-cache-dir --upgrade yt-dlp

COPY app.py .
COPY youtube_uploader.py .

CMD sh -c "gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --threads 8 --timeout 120"
