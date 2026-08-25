FROM python:3.11-slim

# Instalar Node.js para resolver los desafíos de JS de YouTube
RUN apt-get update && apt-get install -y --no-install-recommends \
    nodejs \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 10000

CMD ["gunicorn", "--bind", "0.0.0.0:10000", "app:app"]
