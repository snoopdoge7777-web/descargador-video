import os
import re
import requests
import subprocess
from flask import Flask, request, jsonify
import yt_dlp

app = Flask(__name__)

DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")

def send_discord_log(message):
    if DISCORD_WEBHOOK_URL:
        try:
            requests.post(DISCORD_WEBHOOK_URL, json={"content": message})
        except Exception as e:
            print(f"Error log: {e}")

def send_discord_file(file_path, caption=""):
    if DISCORD_WEBHOOK_URL and os.path.exists(file_path):
        try:
            with open(file_path, 'rb') as f:
                requests.post(
                    DISCORD_WEBHOOK_URL,
                    data={"content": caption},
                    files={"file": (os.path.basename(file_path), f)}
                )
        except Exception as e:
            print(f"Error file: {e}")

@app.route('/', methods=['POST'])
def process_videos():
    data = request.get_json() or {}
    raw_urls = data.get('urls', '')
    job_id = data.get('job_id', 'N/A')
    start_time = data.get('start_time', None)
    end_time = data.get('end_time', None)

    match = re.search(r'https?://[^\s\'"\}]+', str(raw_urls))

    if not match:
        send_discord_log(f"❌ Trabajo `{job_id}` — No se encontró una URL válida en: `{raw_urls}`")
        return jsonify({"error": "No valid URL found"}), 400

    url = match.group(0).rstrip('}]",\'')
    send_discord_log(f"⏳ Trabajo `{job_id}` — Procesando URL: {url}")

    # Configuración anti-bloqueo avanzada para yt-dlp
    ydl_opts = {
        'format': 'best',
        'outtmpl': '/tmp/downloaded_%(id)s.%(ext)s',
        'extractor_args': {
            'youtube': {
                'player_client': ['android', 'ios'],
                'player_skip': ['webpage', 'configs'],
            }
        },
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept-Language': 'en-US,en;q=0.9',
        },
        'nocheckcertificate': True,
        'ignoreerrors': False,
        'quiet': True,
        'no_warnings': True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            downloaded_file = ydl.prepare_filename(info)

        output_file = downloaded_file

        if start_time is not None and end_time is not None:
            trimmed_file = f"/tmp/cut_{job_id}.mp4"
            send_discord_log(f"✂️ Trabajo `{job_id}` — Recortando video ({start_time}s a {end_time}s)...")
            
            ffmpeg_cmd = [
                'ffmpeg', '-y',
                '-ss', str(start_time),
                '-to', str(end_time),
                '-i', downloaded_file,
                '-c', 'copy',
                trimmed_file
            ]
            
            subprocess.run(ffmpeg_cmd, check=True)

            if os.path.exists(downloaded_file):
                os.remove(downloaded_file)

            output_file = trimmed_file

        caption = f"🎬 **Trabajo {job_id}** — Video procesado y enviado."
        send_discord_file(output_file, caption=caption)

        if os.path.exists(output_file):
            os.remove(output_file)

        return jsonify({"status": "success", "job_id": job_id}), 200

    except Exception as e:
        error_msg = f"❌ Trabajo `{job_id}` — Error en la descarga: {str(e)}"
        send_discord_log(error_msg)
        return jsonify({"error": "Processing failed", "details": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
