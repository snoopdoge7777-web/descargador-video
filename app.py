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
        # Extraemos la URL directa del video usando yt-dlp sin restricciones complejas
        ydl_opts = {
            'format': 'best[ext=mp4]/best',
            'noplaylist': True,
            'skip_download': True, # Solo extraemos el enlace de descarga directa
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=False)
            download_url = info.get('url')
            
            # Si viene fragmentado, buscamos un formato alternativo directo
            if not download_url and 'formats' in info:
                for f in info['formats']:
                    if f.get('ext') == 'mp4' and f.get('url'):
                        download_url = f.get('url')
                        break

        if not download_url:
            raise Exception("No se pudo obtener el enlace directo de descarga.")

        # Descargamos el video usando requests de forma limpia y directa
        if os.path.exists("video.mp4"):
            os.remove("video.mp4")

        print(f"Descargando desde: {download_url}")
        r = requests.get(download_url, stream=True, timeout=60)
        with open("video.mp4", "wb") as f:
            for chunk in r.iter_content(chunk_size=1024*1024):
                if chunk:
                    f.write(chunk)

        if os.path.exists("video.mp4") and os.path.getsize("video.mp4") > 0:
            enviar_archivo_a_discord("video.mp4", f"✅ Video procesado con éxito para el trabajo `{job_id}`")
            os.remove("video.mp4")
            return jsonify({"status": "success"})
        else:
            raise Exception("El archivo descargado está vacío o no se generó.")

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
