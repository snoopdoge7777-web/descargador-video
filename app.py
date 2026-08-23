import os
import subprocess
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
    urls = data.get("urls") or data.get("url")
    job_id = data.get("job_id", "desconocido")
    
    duracion_fragmento = 60  # Cortar cada 1 minuto

    if isinstance(urls, str):
        urls = [urls]
    if not urls:
        return jsonify({"error": "No URL provided"}), 400

    url = urls[0] if isinstance(urls, list) else urls
    enviar_discord(f"⏳ Trabajo `{job_id}` iniciado — Procesando video en partes de 1 min.")

    try:
        input_file = "video_original.mp4"
        if os.path.exists(input_file):
            os.remove(input_file)

        # Descargar video
        cmd_dl = ["yt-dlp", "--extractor-args", "youtube:player_client=default", "-f", "best[ext=mp4]/best", "-o", input_file, url]
        resultado = subprocess.run(cmd_dl, capture_output=True, text=True)

        if resultado.returncode != 0:
            enviar_discord(f"❌ Error descargando video.")
            return jsonify({"error": "Download failed"}), 500

        duracion_total = obtener_duracion(input_file)
        if duracion_total <= 0:
            return jsonify({"error": "Duration failed"}), 500

        clips_subidos = 0
        inicio = 0
        parte = 1

        # Cortar en bucle cada 60 segundos
        while inicio < duracion_total:
            output_file = f"parte_{parte}.mp4"
            if os.path.exists(output_file):
                os.remove(output_file)

            fin = min(inicio + duracion_fragmento, duracion_total)

            cmd_cut = [
                "ffmpeg", "-y", "-i", input_file,
                "-ss", str(inicio),
                "-to", str(fin),
                "-c:v", "copy", "-c:a", "copy",
                output_file
            ]
            subprocess.run(cmd_cut, capture_output=True, text=True)

            if os.path.exists(output_file) and os.path.getsize(output_file) > 0:
                with open(output_file, "rb") as f:
                    if DISCORD_WEBHOOK_URL:
                        requests.post(
                            DISCORD_WEBHOOK_URL,
                            data={"content": f"🎬 **Parte {parte}** (Minuto {int(inicio//60)}):"},
                            files={"file": f}
                        )
                clips_subidos += 1
                os.remove(output_file)

            inicio += duracion_fragmento
            parte += 1
            if parte > 20:  # Límite de seguridad para evitar bucles infinitos en videos muy largos
                break

        enviar_discord(f"🏁 Trabajo `{job_id}` finalizado — {clips_subidos} partes enviadas.")
        return jsonify({"ok": True, "partes": clips_subidos})

    except Exception as e:
        enviar_discord(f"❌ Error interno: {str(e)}")
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
