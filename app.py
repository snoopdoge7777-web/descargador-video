import os
import re
import math
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
            print(f"Error enviando archivo a Discord: {e}")

def get_video_duration(file_path):
    cmd = [
        'ffprobe', '-v', 'error',
        '-show_entries', 'format=duration',
        '-of', 'default=noprint_wrappers=1:nokey=1',
        file_path
    ]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return float(result.stdout.strip())

def download_via_cobalt(url, output_path):
    """Descarga el video usando la API pública de Cobalt para evitar bloqueos de IP de YouTube."""
    api_url = "https://api.cobalt.tools/"
    payload = {
        "url": url,
        "videoQuality": "720"
    }
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json"
    }

    response = requests.post(api_url, json=payload, headers=headers, timeout=20)
    data = response.json()

    if response.status_code != 200 or "url" not in data:
        raise Exception(f"Cobalt API error: {data.get('text', 'No se obtuvo enlace de descarga')}")

    download_url = data["url"]

    # Descargar el archivo de video generado
    with requests.get(download_url, stream=True, timeout=120) as r:
        r.raise_for_status()
        with open(output_path, 'wb') as f:
            for chunk in r.iter_content(chunk_size=16384):
                f.write(chunk)

@app.route('/', methods=['POST'])
def process_videos():
    data = request.get_json() or {}
    raw_urls = data.get('urls', '')
    job_id = data.get('job_id', 'N/A')
    segment_duration = int(data.get('segment_duration', 40))

    match = re.search(r'https?://[^\s\'"\}]+', str(raw_urls))
    if not match:
        send_discord_log(f"❌ Trabajo `{job_id}` — No se encontró una URL válida.")
        return jsonify({"error": "No valid URL found"}), 400

    url = match.group(0).rstrip('}]",\'')
    send_discord_log(f"⏳ Trabajo `{job_id}` — Descargando vía API externa para cortar en partes de {segment_duration}s...")

    downloaded_file = f"/tmp/downloaded_{job_id}.mp4"

    try:
        # 1. Descargar mediante la API de Cobalt
        download_via_cobalt(url, downloaded_file)

        if not os.path.exists(downloaded_file) or os.path.getsize(downloaded_file) == 0:
            raise Exception("El archivo descargado está vacío o no existe.")

        # 2. Calcular la duración total y dividir en partes de 40s
        total_duration = get_video_duration(downloaded_file)
        num_segments = math.ceil(total_duration / segment_duration)

        send_discord_log(f"✂️ Trabajo `{job_id}` — Duración: {int(total_duration)}s. Procesando **{num_segments} partes** de {segment_duration}s...")

        # 3. Cortar y subir secuencialmente a Discord
        for i in range(num_segments):
            start_sec = i * segment_duration
            part_number = i + 1
            segment_file = f"/tmp/part_{job_id}_{part_number}.mp4"

            ffmpeg_cmd = [
                'ffmpeg', '-y',
                '-ss', str(start_sec),
                '-t', str(segment_duration),
                '-i', downloaded_file,
                '-c', 'copy',
                segment_file
            ]

            subprocess.run(ffmpeg_cmd, check=True)

            caption = f"🎬 **Trabajo {job_id}** — Parte {part_number}/{num_segments} ({start_sec}s - {start_sec + segment_duration}s)"
            send_discord_file(segment_file, caption=caption)

            if os.path.exists(segment_file):
                os.remove(segment_file)

        if os.path.exists(downloaded_file):
            os.remove(downloaded_file)

        send_discord_log(f"✅ Trabajo `{job_id}` — ¡Proceso completado! Se enviaron las {num_segments} partes a Discord.")

        return jsonify({
            "status": "success",
            "job_id": job_id,
            "total_segments": num_segments
        }), 200

    except Exception as e:
        error_msg = f"❌ Trabajo `{job_id}` — Error: {str(e)}"
        send_discord_log(error_msg)

        if os.path.exists(downloaded_file):
            os.remove(downloaded_file)

        return jsonify({"error": "Processing failed", "details": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
