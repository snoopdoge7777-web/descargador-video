import os
import re
import math
import requests
import subprocess
from flask import Flask, request, jsonify
import yt_dlp

app = Flask(__name__)

# Configuración del Webhook de Discord
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")

def send_discord_log(message):
    """Envía un mensaje de estado o error al canal de Discord."""
    if DISCORD_WEBHOOK_URL:
        try:
            requests.post(DISCORD_WEBHOOK_URL, json={"content": message})
        except Exception as e:
            print(f"Error enviando log a Discord: {e}")

def send_discord_file(file_path, caption=""):
    """Sube un archivo de video al canal de Discord."""
    if DISCORD_WEBHOOK_URL and os.path.exists(file_path):
        try:
            with open(file_path, 'rb') as f:
                requests.post(
                    DISCORD_WEBHOOK_URL,
                    data={"content": caption},
                    files={"file": (os.path.basename(file_path), f)}
                )
        except Exception as e:
            print(f"Error subiendo archivo a Discord: {e}")

def get_video_duration(file_path):
    """Obtiene la duración total del video descargado usando ffprobe."""
    cmd = [
        'ffprobe', '-v', 'error',
        '-show_entries', 'format=duration',
        '-of', 'default=noprint_wrappers=1:nokey=1',
        file_path
    ]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return float(result.stdout.strip())

@app.route('/', methods=['POST'])
def process_videos():
    data = request.get_json() or {}
    raw_urls = data.get('urls', '')
    job_id = data.get('job_id', 'N/A')
    
    # Duración de cada fragmento (por defecto 40 segundos)
    segment_duration = int(data.get('segment_duration', 40))

    # Limpieza de la URL recibida desde n8n
    match = re.search(r'https?://[^\s\'"\}]+', str(raw_urls))
    if not match:
        send_discord_log(f"❌ Trabajo `{job_id}` — No se encontró una URL válida.")
        return jsonify({"error": "No valid URL found"}), 400

    url = match.group(0).rstrip('}]",\'')
    send_discord_log(f"⏳ Trabajo `{job_id}` — Descargando video completo para dividirlo en partes de {segment_duration}s...")

    downloaded_file = f"/tmp/downloaded_{job_id}.mp4"

    # Opciones de yt-dlp usando clientes compatibles para evitar bloqueos de IP
    ydl_opts = {
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'outtmpl': downloaded_file,
        'extractor_args': {
            'youtube': {
                'player_client': ['tv_embedded', 'ios', 'android'],
                'player_skip': ['webpage', 'configs'],
            }
        },
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
        },
        'quiet': True,
        'no_warnings': True,
    }

    try:
        # 1. Descargar video original completo
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        if not os.path.exists(downloaded_file):
            raise Exception("No se pudo descargar el archivo inicial de video.")

        # 2. Calcular cuántas partes de 40s salen según la duración total
        total_duration = get_video_duration(downloaded_file)
        num_segments = math.ceil(total_duration / segment_duration)
        
        send_discord_log(f"✂️ Trabajo `{job_id}` — Duración total: {int(total_duration)}s. Se generarán **{num_segments} partes** de {segment_duration}s cada una.")

        # 3. Recortar y subir secuencialmente cada parte de 40 segundos
        for i in range(num_segments):
            start_sec = i * segment_duration
            part_number = i + 1
            segment_file = f"/tmp/part_{job_id}_{part_number}.mp4"

            # Comando de recorte FFmpeg de alta velocidad
            ffmpeg_cmd = [
                'ffmpeg', '-y',
                '-ss', str(start_sec),
                '-t', str(segment_duration),
                '-i', downloaded_file,
                '-c', 'copy',
                segment_file
            ]
            
            subprocess.run(ffmpeg_cmd, check=True)

            # Subir la parte generada a Discord
            caption = f"🎬 **Trabajo {job_id}** — Parte {part_number}/{num_segments} ({start_sec}s - {start_sec + segment_duration}s)"
            send_discord_file(segment_file, caption=caption)

            # Borrar la parte enviada para liberar memoria
            if os.path.exists(segment_file):
                os.remove(segment_file)

        # 4. Limpiar el video original descargado
        if os.path.exists(downloaded_file):
            os.remove(downloaded_file)

        send_discord_log(f"✅ Trabajo `{job_id}` — ¡Proceso finalizado! Todas las {num_segments} partes fueron enviadas.")

        return jsonify({
            "status": "success",
            "job_id": job_id,
            "total_segments": num_segments
        }), 200

    except Exception as e:
        error_msg = f"❌ Trabajo `{job_id}` — Error en la división de video: {str(e)}"
        send_discord_log(error_msg)
        
        if os.path.exists(downloaded_file):
            os.remove(downloaded_file)
            
        return jsonify({"error": "Processing failed", "details": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
