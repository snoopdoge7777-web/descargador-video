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

@app.route("/", methods=["POST"])
def procesar_video():
    data = request.get_json() or {}
    url = data.get("url") or data.get("urls")
    job_id = data.get("job_id", "desconocido")
    
    # Tiempos de corte por defecto (ej: desde el segundo 0 hasta el 60, o puedes recibirlos de n8n)
    start_time = data.get("start", "00:00:00")
    end_time = data.get("end", "00:01:00")

    if isinstance(url, list):
        url = url[0] if url else None

    if not url:
        return jsonify({"error": "No URL provided"}), 400

    enviar_discord(f"⏳ Trabajo `{job_id}` iniciado — Cortando de {start_time} a {end_time}.")

    try:
        input_file = "video_original.mp4"
        output_file = "clip_cortado.mp4"

        for f in [input_file, output_file]:
            if os.path.exists(f):
                os.remove(f)

        # 1. Descargar el video completo
        cmd_dl = ["yt-dlp", "-f", "best[ext=mp4]/best", "-o", input_file, url]
        resultado = subprocess.run(cmd_dl, capture_output=True, text=True)

        if resultado.returncode != 0:
            enviar_discord(f"❌ Error descargando `{url}`: {resultado.stderr[:200]}")
            return jsonify({"error": "Download failed"}), 500

        # 2. Cortar el video con ffmpeg usando los tiempos start y end
        cmd_cut = [
            "ffmpeg", "-i", input_file, 
            "-ss", str(start_time), 
            "-to", str(end_time), 
            "-c:v", "copy", "-c:a", "copy", 
            output_file
        ]
        res_cut = subprocess.run(cmd_cut, capture_output=True, text=True)

        if res_cut.returncode != 0:
            # Si falla el copy exacto, intentamos recodificar por seguridad
            cmd_cut_recode = [
                "ffmpeg", "-i", input_file, 
                "-ss", str(start_time), 
                "-to", str(end_time), 
                output_file
            ]
            subprocess.run(cmd_cut_recode, capture_output=True, text=True)

        # 3. Enviar el clip recortado a Discord
        if os.path.exists(output_file):
            with open(output_file, "rb") as f:
                if DISCORD_WEBHOOK_URL:
                    requests.post(
                        DISCORD_WEBHOOK_URL,
                        data={"content": f"🎬 **Clip listo** (Del {start_time} al {end_time}) para descargar:"},
                        files={"file": f}
                    )
            enviar_discord(f"🏁 Trabajo `{job_id}` finalizado — Clip enviado a Discord.")
            return jsonify({"ok": True, "job_id": job_id})
        else:
            enviar_discord(f"❌ No se pudo generar el archivo recortado.")
            return jsonify({"error": "Clipping failed"}), 500

    except Exception as e:
        enviar_discord(f"❌ Excepción: {str(e)}")
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
