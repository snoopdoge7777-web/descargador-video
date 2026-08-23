import os
import subprocess
import requests
from flask import Flask, request, jsonify

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
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return float(res.stdout.strip())
    except Exception:
        return 0.0

@app.route("/", methods=["POST"])
def procesar_video():
    data = request.get_json() or {}
    urls = data.get("urls") or data.get("url")
    job_id = data.get("job_id", "desconocido")
    duracion_fragmento = 60  # Duración de cada recorte (en segundos)

    if isinstance(urls, list):
        url = urls[0] if urls else None
    else:
        url = urls

    if not url:
        return jsonify({"error": "No URL provided"}), 400

    enviar_discord(f"⏳ Trabajo `{job_id}` — Descargando video en máxima calidad original...")

    try:
        input_file = "video_original.mp4"
        if os.path.exists(input_file):
            os.remove(input_file)

        # Configuración de yt-dlp usando cookies si existen
        cmd_dl = [
            "yt-dlp",
            "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
            "-o", input_file,
            "--no-check-certificates"
        ]

        if os.path.exists("cookies.txt"):
            cmd_dl.extend(["--cookies", "cookies.txt"])

        cmd_dl.append(url)

        res_dl = subprocess.run(cmd_dl, capture_output=True, text=True)

        if res_dl.returncode != 0 or not os.path.exists(input_file):
            enviar_discord(f"❌ Error al descargar con yt-dlp: {res_dl.stderr[:250]}")
            return jsonify({"error": "Download failed", "details": res_dl.stderr[:200]}), 500

        duracion_total = obtener_duracion(input_file)
        if duracion_total <= 0:
            enviar_discord("❌ Error: No se pudo medir la duración del video descargado.")
            return jsonify({"error": "Duration failed"}), 500

        clips_subidos = 0
        inicio = 0
        parte = 1

        # Generar recortes preservando la calidad original exacta (-c copy)
        while inicio < duracion_total:
            output_file = f"recorte_{parte}.mp4"
            if os.path.exists(output_file):
                os.remove(output_file)

            fin = min(inicio + duracion_fragmento, duracion_total)

            cmd_cut = [
                "ffmpeg", "-y", "-i", input_file,
                "-ss", str(inicio), "-to", str(fin),
                "-c:v", "copy", "-c:a", "copy",
                output_file
            ]
            subprocess.run(cmd_cut, capture_output=True, text=True)

            if os.path.exists(output_file) and os.path.getsize(output_file) > 0:
                with open(output_file, "rb") as f:
                    if DISCORD_WEBHOOK_URL:
                        requests.post(
                            DISCORD_WEBHOOK_URL,
                            data={"content": f"🎬 **Recorte {parte}** (Máxima resolución | {int(inicio)}s a {int(fin)}s):"},
                            files={"file": f}
                        )
                clips_subidos += 1
                os.remove(output_file)

            inicio += duracion_fragmento
            parte += 1
            if parte > 20:  # Límite máximo de partes por seguridad
                break

        enviar_discord(f"🏁 Trabajo `{job_id}` finalizado — {clips_subidos} recortes subidos a Discord.")
        return jsonify({"ok": True, "partes": clips_subidos})

    except Exception as e:
        enviar_discord(f"❌ Error interno: {str(e)}")
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
