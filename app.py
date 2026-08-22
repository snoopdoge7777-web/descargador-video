import os
import requests
from flask import Flask, request, jsonify
import yt_dlp

app = Flask(__name__)

DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")

@app.route("/", methods=["POST"])
def descargar_video():
    data = request.json
    video_url = data.get("url")
    job_id = data.get("job_id", "desconocido")

    if not video_url:
        return jsonify({"error": "No URL provided"}), 400

    enviar_a_discord(f"⏳ Iniciando procesamiento automático del trabajo `{job_id}` ...")

    try:
        # Configuración de yt-dlp con soporte actualizado para evitar bloqueos
        ydl_opts = {
            'format': 'best',
            'outtmpl': 'video.mp4',
            'extractor_args': {'youtube': {'player_client': ['default']}},
        }
        
        # Si subiste tu archivo de cookies a GitHub, descomenta la siguiente línea:
        # ydl_opts['cookiefile'] = 'youtube.com_cookies.txt'

        if os.path.exists("video.mp4"):
            os.remove("video.mp4")

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([video_url])

        if os.path.exists("video.mp4"):
            enviar_archivo_a_discord("video.mp4", f"✅ Video procesado con éxito para el trabajo `{job_id}`")
            os.remove("video.mp4")
            return jsonify({"status": "success"})
        else:
            raise Exception("No se pudo generar el archivo de video.")

    except Exception as e:
        error_msg = str(e)
        enviar_a_discord(f"❌ Error crítico en trabajo `{job_id}`: {error_msg}")
        return jsonify({"error": error_msg}), 500

def enviar_a_discord(mensaje):
    if DISCORD_WEBHOOK_URL:
        requests.post(DISCORD_WEBHOOK_URL, json={"content": mensaje})

def enviar_archivo_a_discord(filepath, mensaje):
    if DISCORD_WEBHOOK_URL:
        with open(filepath, "rb") as f:
            requests.post(
                DISCORD_WEBHOOK_URL,
                data={"content": mensaje},
                files={"file": f}
            )

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
