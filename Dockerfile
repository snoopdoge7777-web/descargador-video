FROM python:3.11-slim

# 1. Instalar dependencias del sistema requeridas por yt-dlp y ffmpeg
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    git \
    nodejs \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 2. Copiar e instalar dependencias de Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 3. Forzar actualización de paquetes críticos
RUN pip install --no-cache-dir --upgrade yt-dlp gunicorn

# 4. Copiar todo el código de la aplicación
COPY . .

# 5. Comando de inicio usando módulo Python (evita errores de PATH en Linux)
CMD ["python", "-m", "gunicorn", "app:app", "--bind", "0.0.0.0:10000", "--workers", "1", "--threads", "8", "--timeout", "120"]
