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
    send_discord_log(f"⏳ Trabajo `{job_id}` — Descargando con yt-dlp + Deno + Cookies para recortar en partes de {segment_duration}s...")

    downloaded_file = f"/tmp/downloaded_{job_id}.mp4"

    # Buscar archivos de cookies disponibles en la carpeta raíz
    possible_cookies = [
        os.path.join(os.path.dirname(__file__), "www.youtube.com_cookies.txt"),
        os.path.join(os.path.dirname(__file__), "cookies.txt")
    ]
    cookie_path = next((p for p in possible_cookies if os.path.exists(p)), None)

    try:
        ytdlp_cmd = [
            'yt-dlp',
            '-f', 'b[ext=mp4]/best[ext=mp4]/best',
            '-o', downloaded_file,
            '--no-playlist'
        ]

        if cookie_path:
            ytdlp_cmd.extend(['--cookies', cookie_path])
            send_discord_log(f"🍪 Usando cookies: `{os.path.basename(cookie_path)}`")

        ytdlp_cmd.append(url)

        result = subprocess.run(ytdlp_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

        if result.returncode != 0 or not os.path.exists(downloaded_file):
            raise Exception(f"yt-dlp falló: {result.stderr}")

        total_duration = get_video_duration(downloaded_file)
        num_segments = math.ceil(total_duration / segment_duration)

        send_discord_log(f"✂️ Trabajo `{job_id}` — Duración total: {int(total_duration)}s. Generando **{num_segments} partes** de {segment_duration}s...")

        # Recortar en partes de 40s y enviar
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

        send_discord_log(f"✅ Trabajo `{job_id}` — ¡Proceso completado exitosamente!")

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
