import os
import subprocess
from flask import Flask, request, jsonify

app = Flask(__name__)

# Cargar cookies dinámicamente si están en las variables de entorno de Render
COOKIES_PATH = "www.youtube.com_cookies.txt"
cookies_env = os.environ.get("COOKIES_CONTENT")
if cookies_env:
    with open(COOKIES_PATH, "w", encoding="utf-8") as f:
        f.write(cookies_env)

@app.route("/", methods=["POST"])
def procesar_video():
    data = request.get_json()
    if not data or "url" not in data:
        return jsonify({"ok": False, "error": "No se proporcionó ninguna URL"}), 400

    video_url = data["url"]
    output_filename = "video_final_editado.mp4"
    raw_video = "downloaded.mp4"

    try:
        # 1. Descargar el video de YouTube usando yt-dlp y las cookies configuradas
        ydl_command = [
            "yt-dlp",
            "--cookies", COOKIES_PATH,
            "-f", "best[ext=mp4]/best",
            "-o", raw_video,
            video_url
        ]
        
        result = subprocess.run(ydl_command, capture_output=True, text=True)
        if result.returncode != 0:
            return jsonify({"ok": False, "error": f"Falla en la descarga con yt-dlp: {result.stderr}"}), 500

        # 2. Procesar y recortar partes usando FFmpeg (ejemplo de optimización de corte o silencio)
        # Aquí puedes ajustar los filtros de FFmpeg o dejarlo preparado para unir partes
        process_command = [
            "ffmpeg", "-y", "-i", raw_video,
            "-vf", "silenceremove=stop_periods=-1:stop_duration=1:stop_threshold=-30dB",
            output_filename
        ]
        
        proc_result = subprocess.run(process_command, capture_output=True, text=True)
        if proc_result.returncode != 0:
            return jsonify({"ok": False, "error": f"Falla al procesar video con FFmpeg: {proc_result.stderr}"}), 500

        return jsonify({
            "ok": True,
            "message": "Video descargado, recortado y unificado con éxito",
            "archivo": output_filename
        })

    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
