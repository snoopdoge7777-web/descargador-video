# Usamos Python 3.11 sobre Debian Bookworm
FROM python:3.11-slim-bookworm

# Evitamos buffering de logs en consola
ENV PYTHONUNBUFFERED=1

# Instalamos ffmpeg y nodejs (necesario para las firmas de yt-dlp)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    nodejs \
    ca-certificates \
    && rm -rf /var/lib/apt-get/lists/*

# Establecemos el directorio de trabajo
WORKDIR /app

# Copiamos primero el archivo de requerimientos e instalamos dependencias
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiamos el resto del código del proyecto
COPY . .

# Exponemos el puerto estándar de Render
EXPOSE 10000

# Comando para iniciar la aplicación con Gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:10000", "app:app"]
