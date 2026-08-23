import os
import requests
import subprocess
from flask import Flask, request, jsonify
import yt_dlp

app = Flask(__name__)

# Configuración del Webhook de Discord
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")

def send_discord_log(message):
    """Envía mensajes de texto de estado o error al canal de Discord."""
    if DISCORD_WEBHOOK_URL:
        try:
            requests.post(DISCORD_WEBHOOK_URL, json={"content": message})
        except Exception as e:
            print(f"Error enviando log a Discord: {e}")

def send_discord_file(file_path, caption=""):
    """Sube el archivo recortado directamente al canal de Discord."""
    if DISCORD_WEBHOOK_URL and os.path.exists(file_path):
        try:
            with open(file_path, 'rb') as f:
                requests.post(
                    DISCORD_WEBHOOK_URL,
                    data={"content": caption},
                    files={"file": (os.path.basename(file_path), f)}
                )
        except Exception as e:
            print(f"Error enviando archivo a Discord: {e}")

@app.route('/', methods=['POST'])
def process_videos():
    data = request.get_json() or {}
    urls = data.get('urls', [])
    job_id = data.get('job_id', 'N/A')
    
    # Tiempos de corte opcionales en segundos (ejemplo: start_time=10, end_time=40)
    start_time = data.get('start_time', None)
    end_time = data.get('end_time', None)

    if not urls:
        return jsonify({"error": "No se proporcionaron URLs"}), 400

    url_list = urls if isinstance(urls, list) else [urls]

    # Configuración de yt-dlp para evitar Error 429 y bloqueos de YouTube
    ydl_opts = {
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'outtmpl': '/tmp/downloaded_%(id)s.%(ext)s',
        'extractor_args': {
            'youtube': {
                'player_client': ['ios', 'mweb'],
                'player_skip': ['webpage', 'configs'],
            }
        },
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1',
        },
        'quiet': True,
        'no_warnings': True,
    }

    processed_files = []

    for idx, url in enumerate(url_list):
        send_discord_log(f"⏳ Trabajo `{job_id}` — Procesando video {idx + 1}/{len(url_list)}...")

        try:
            # 1. Descarga del video
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                downloaded_file = ydl.prepare_filename(info)

            output_file = downloaded_file

            # 2. Recorte del video con FFmpeg (si se definieron start_time / end_time)
            if start_time is not None and end_time is not None:
                trimmed_file = f"/tmp/cut_{job_id}_{idx}.mp4"
                send_discord_log(f"✂️ Trabajo `{job_id}` — Recortando video desde {start_time}s hasta {end_time}s...")
                
                ffmpeg_cmd = [
                    'ffmpeg', '-y',
                    '-ss', str(start_time),
                    '-to', str(end_time),
                    '-i', downloaded_file,
                    '-c', 'copy',
                    trimmed_file
                ]
                
                subprocess.run(ffmpeg_cmd, check=True)
                
                # Borramos el video original completo para liberar espacio
                if os.path.exists(downloaded_file):
                    os.remove(downloaded_file)
                
                output_file = trimmed_file

            # 3. Subir el video recortado a Discord
            caption = f"🎬 **Trabajo {job_id}** — Recorte completado con éxito."
            send_discord_file(output_file, caption=caption)
            
            processed_files.append(output_file)

            # Limpiar archivo temporal enviado
            if os.path.exists(output_file):
                os.remove(output_file)

        except Exception as e:
            error_msg = f"❌ Trabajo `{job_id}` — Error en el video {url}: {str(e)}"
            send_discord_log(error_msg)
            return jsonify({"error": "Processing failed", "details": str(e)}), 500

    return jsonify({
        "status": "success",
        "job_id": job_id,
        "processed_count": len(processed_files)
    }), 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
