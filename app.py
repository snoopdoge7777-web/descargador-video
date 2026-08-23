import os
import re
import math
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

def download_video_robust(url, output_path):
    """Intenta descargar el video con múltiples clientes de yt-dlp para saltar bloqueos de 'Sign in to confirm'."""
    clients_to_try = [
        ['ios'],
        ['android_creator'],
        ['mweb'],
        ['tv_embedded', 'android']
    ]

    last_error = None

    for client in clients_to_try:
        ydl_opts = {
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            'outtmpl': output_path,
            'extractor_args': {
                'youtube': {
                    'player_client': client,
                    'player_skip': ['webpage', 'configs'],
                }
            },
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1',
                'Accept-Language': 'en-US,en;q=0.9',
            },
            'quiet': True,
            'no_warnings': True,
            'nocheckcertificate': True,
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                return  # Descarga exitosa
        except Exception as e:
            last_error = e
            continue

    raise Exception(f"Todos los intentos de descarga fallaron: {last_error}")

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
    send_discord_log(f"⏳ Trabajo `{job_id}` — Descargando video para dividirlo en partes de {segment_duration}s...")

    downloaded_file = f"/tmp/downloaded_{job_id}.mp4"

    try:
        # 1. Descargar video
        download_video_robust(url, downloaded_file)

        if not os.path.exists(downloaded_file):
            raise Exception("No se pudo obtener el archivo de video.")

        # 2. Calcular fragmentos de 40s
        total_duration = get_video_duration(downloaded_file)
        num_segments = math.ceil(total_duration / segment_duration)

        send_discord_log(f"✂️ Trabajo `{job_id}` — Duración: {int(total_duration)}s. Generando **{num_segments} partes** de {segment_duration}s...")

        # 3. Cortar y subir cada parte
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
        error_msg = f"❌ Trabajo `{job_id}` — Error en la división de video: {str(e)}"
        send_discord_log(error_msg)

        if os.path.exists(downloaded_file):
            os.remove(downloaded_file)

        return jsonify({"error": "Processing failed", "details": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
