import os
import re
import requests
import subprocess
from flask import Flask, request, jsonify

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

def download_via_cobalt(url, download_path):
    """Descarga el video utilizando la API pública de Cobalt sin bloqueos de IP."""
    api_url = "https://api.cobalt.tools/api/json"
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json"
    }
    payload = {
        "url": url,
        "videoQuality": "720"
    }
    
    response = requests.post(api_url, json=payload, headers=headers, timeout=30)
    data = response.json()
    
    stream_url = data.get("url")
    if not stream_url:
        raise Exception(f"Cobalt error: {data.get('text', 'No se obtuvo enlace de video')}")
        
    with requests.get(stream_url, stream=True, timeout=60) as r:
        r.raise_for_status()
        with open(download_path, 'wb') as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)

@app.route('/', methods=['POST'])
def process_videos():
    data = request.get_json() or {}
    raw_urls = data.get('urls', '')
    job_id = data.get('job_id', 'N/A')
    start_time = data.get('start_time', None)
    end_time = data.get('end_time', None)

    match = re.search(r'https?://[^\s\'"\}]+', str(raw_urls))
    if not match:
        send_discord_log(f"❌ Trabajo `{job_id}` — No se encontró una URL válida.")
        return jsonify({"error": "No valid URL found"}), 400

    url = match.group(0).rstrip('}]",\'')
    send_discord_log(f"⏳ Trabajo `{job_id}` — Procesando URL vía Cobalt API: {url}")

    downloaded_file = f"/tmp/downloaded_{job_id}.mp4"

    try:
        # 1. Descarga vía Cobalt
        download_via_cobalt(url, downloaded_file)
        output_file = downloaded_file

        # 2. Recorte con FFmpeg (si hay tiempos)
        if start_time is not None and end_time is not None and int(end_time) > int(start_time):
            trimmed_file = f"/tmp/cut_{job_id}.mp4"
            send_discord_log(f"✂️ Trabajo `{job_id}` — Recortando ({start_time}s a {end_time}s)...")
            
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

        # 3. Envío a Discord
        caption = f"🎬 **Trabajo {job_id}** — Recorte/Descarga completada con éxito."
        send_discord_file(output_file, caption=caption)

        if os.path.exists(output_file):
            os.remove(output_file)

        return jsonify({"status": "success", "job_id": job_id}), 200

    except Exception as e:
        error_msg = f"❌ Trabajo `{job_id}` — Error: {str(e)}"
        send_discord_log(error_msg)
        if os.path.exists(downloaded_file):
            os.remove(downloaded_file)
        return jsonify({"error": "Processing failed", "details": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
