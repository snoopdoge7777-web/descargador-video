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
            print(f"Error Discord: {e}")

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
    duracion_fragmento = 60

    if isinstance(urls, list):
        url = urls[0] if urls else None
    else:
        url = urls

    if not url:
        return jsonify({"error": "No URL provided"}), 400

    enviar_discord(f"⏳ Trabajo `{job_id}` — Extrayendo video en máxima calidad (vía Cobalt API)...")

    try:
        input_file = "video_original.mp4"
        if os.path.exists(input_file):
            os.remove(input_file)

        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        payload = {"url": url, "videoQuality": "max"}
        resp = requests.post("https://api.cobalt.tools/api/json", json=payload, headers=headers)

        if resp.status_code != 200 or "url" not in resp.json():
            enviar_discord("❌ Error: No se pudo obtener el stream directo.")
            return jsonify({"error": "Cobalt API failed"}), 500

        stream_url = resp.json()["url"]

        with requests.get(stream_url, stream=True) as r:
            r.raise_for_status()
            with open(input_file, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)

        duracion_total = obtener_duracion(input_file)
        if duracion_total <= 0:
            enviar_discord("❌ Error: No se pudo medir la duración del archivo.")
            return jsonify({"error": "Duration failed"}), 500

        clips_subidos = 0
        inicio = 0
        parte = 1

        while inicio < duracion_total:
            output_file = f"corte_{parte}.mp4"
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
                            data={"content": f"🎬 **Recorte {parte}** (Máxima Calidad | {int(inicio)}s a {int(fin)}s):"},
                            files={"file": f}
                        )
                clips_subidos += 1
                os.remove(output_file)

            inicio += duracion_fragmento
            parte += 1
            if parte > 20:
                break

        enviar_discord(f"🏁 Trabajo `{job_id}` finalizado — {clips_subidos} recortes subidos a Discord.")
        return jsonify({"ok": True, "partes": clips_subidos})

    except Exception as e:
        enviar_discord(f"❌ Error interno: {str(e)}")
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
