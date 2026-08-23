import os
import subprocess
import math
from flask import Flask, request, jsonify
import requests

app = Flask(__name__)

DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")

def enviar_discord(mensaje):
    if DISCORD_WEBHOOK_URL:
        try:
            requests.post(DISCORD_WEBHOOK_URL, json={"content": mensaje})
        except Exception as e:
            print(f"Error enviando a Discord: {e}")

def obtener_duracion(input_file):
    try:
        cmd = [
            "ffprobe", "-v", "error", "-show_entries",
            "format=duration", "-of",
            "default=noprint_wrappers=1:nokey=1", input_file
        ]
        resultado = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return float(resultado.stdout.strip())
    except Exception:
        return 0.0

@app.route("/", methods=["POST"])
def procesar_video():
    data = request.get_json() or {}
    url = data.get("url") or data.get("urls")
    job_id = data.get("job_id", "desconocido")
    
    # Duración de cada fragmento en segundos (por defecto 60 segundos = 1 minuto)
    duracion_fragmento = int(data.get("duracion", 60))

    if isinstance(url, list):
        url = url[0] if url else None

    if not url:
        return jsonify({"error": "No URL provided"}), 400

    enviar_discord(f"⏳ Trabajo `{job_id}` iniciado — Descargando y dividiendo en fragmentos de {duracion_fragmento}s.")

    try:
        input_file = "video_original.mp4"

        if os.path.exists(input_file):
            os.remove(input_file)

        # 1. Descargar el video
        cmd_dl = ["yt-dlp", "--extractor-args", "youtube:player_client=default", "-f", "best[ext=mp4]/best", "-o", input_file, url]
        resultado = subprocess.run(cmd_dl, capture_output=True, text=True)

        if resultado.returncode != 0:
            enviar_discord(f"❌ Error descargando `{url}`: {resultado.stderr[:200]}")
            return jsonify({"error": "Download failed"}), 500

        # 2. Obtener la duración total del video
        duracion_total = obtener_duracion(input_file)
        if duracion_total <= 0:
            enviar_discord(f"❌ No se pudo determinar la duración del video.")
            return jsonify({"error": "Duration failed"}), 500

        clips_subidos = 0
        inicio = 0
        parte = 1

        # 3. Bucle para cortar el video en partes de X segundos hasta que termine
        while inicio < duracion_total:
            output_file = f"parte_{parte}.mp4"
            if os.path.exists(output_file):
                os.remove(output_file)

            fin = min(inicio + duracion_fragmento, duracion_total)

            cmd_cut = [
                "ffmpeg", "-y", "-i", input_file,
                "-ss", str(inicio),
                "-to", str(fin),
                "-c:v", "libx264", "-c:a", "aac",
                output_file
            ]
            res_cut = subprocess.run(cmd_cut, capture_output=True, text=True)

            if res_cut.returncode == 0 and os.path.exists(output_file):
                with open(output_file, "rb") as f:
                    if DISCORD_WEBHOOK_URL:
                        requests.post(
                            DISCORD_WEBHOOK_URL,
                            data={"content": f"🎬 **Parte {parte}** (Desde {int(inicio)}s hasta {int(fin)}s):"},
                            files={"file": f}
                        )
                clips_subidos += 1
                os.remove(output_file)

            inicio += duracion_fragmento
            parte += 1

        enviar_discord(f"🏁 Trabajo `{job_id}` finalizado — Se enviaron {clips_subidos} partes a Discord.")
        return jsonify({"ok": True, "job_id": job_id, "partes": clips_subidos})

    except Exception as e:
        enviar_discord(f"❌ Excepción: {str(e)}")
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
