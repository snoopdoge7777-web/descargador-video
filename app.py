import os
import requests
from flask import Flask, request, jsonify
import yt_dlp

app = Flask(__name__)

# Configuración del Webhook de Discord
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")

def send_discord_log(message):
    """Envía mensajes de estado o error al canal de Discord."""
    if DISCORD_WEBHOOK_URL:
        try:
            requests.post(DISCORD_WEBHOOK_URL, json={"content": message})
        except Exception as e:
            print(f"Error enviando log a Discord: {e}")

@app.route('/', methods=['POST'])
def download_video():
    data = request.get_json() or {}
    urls = data.get('urls', [])
    job_id = data.get('job_id', 'N/A')

    if not urls:
        return jsonify({"error": "No se proporcionaron URLs"}), 400

    url = urls[0] if isinstance(urls, list) else urls
    send_discord_log(f"⏳ Trabajo `{job_id}` — Descargando video en máxima calidad original...")

    # Opciones de yt-dlp optimizadas para evitar el Error 429 y requerimientos JS
    ydl_opts = {
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'outtmpl': '/tmp/%(id)s.%(ext)s',
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

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)

        send_discord_log(f"✅ Trabajo `{job_id}` — Video descargado con éxito.")
        return jsonify({
            "status": "success",
            "job_id": job_id,
            "file_path": filename,
            "title": info.get('title', '')
        }), 200

    except Exception as e:
        error_msg = f"❌ Error al descargar con yt-dlp: {str(e)}"
        send_discord_log(f"Trabajo `{job_id}` — {error_msg}")
        return jsonify({"error": "Download failed", "details": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
