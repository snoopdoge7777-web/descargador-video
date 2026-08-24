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
def procesar_videos():
    data = request.get_json()
    if not data:
        return jsonify({"ok": False, "error": "No se proporcionaron datos"}), 400

    # Acepta tanto una sola url ("url") como una lista de URLs ("urls")
    urls = []
    if "urls" in data and isinstance(data["urls"], list):
        urls = data["urls"]
    elif "url" in data:
        urls = [data["url"]]
    
    if not urls:
        return jsonify({"ok": False, "error": "No se proporcionó ninguna URL o lista de URLs"}), 400

    videos_procesados = []

    try:
        for index, video_url in enumerate(urls):
            raw_video = f"downloaded_{index}.mp4"
            output_filename = f"video_cortado_{index}.mp4"

            # 1. Descargar el video usando yt-dlp con cookies y el motor de JavaScript de Node.js
            ydl_command = [
                "yt-dlp",
                "--cookies", COOKIES_PATH,
                "--js-runtimes", "node",
                "-f", "best[ext=mp4]/best",
                "-o", raw_video,
                video_url
            ]
            
            result = subprocess.run(ydl_command, capture_output=True, text=True)
            if result.returncode != 0:
                return jsonify({
                    "ok": False, 
                    "error": f"Falla en la descarga del video {index+1} con yt-dlp: {result.stderr}"
                }), 500

            # 2. Cortar/procesar el video usando FFmpeg (aquí puedes ajustar los filtros si deseas)
            process_command = [
                "ffmpeg", "-y", "-i", raw_video,
                "-vf", "silenceremove=stop_periods=-1:stop_duration=1:stop_threshold=-30dB",
                output_filename
            ]
            
            proc_result = subprocess.run(process_command, capture_output=True, text=True)
            if proc_result.returncode != 0:
                return jsonify({
                    "ok": False, 
                    "error": f"Falla al procesar el video {index+1} con FFmpeg: {proc_result.stderr}"
                }), 500

            # Guardar el nombre del archivo exitoso en la lista
            videos_procesados.append(output_filename)

            # Limpiar el archivo crudo temporal para ahorrar espacio
            if os.path.exists(raw_video):
                os.remove(raw_video)

        return jsonify({
            "ok": True,
            "message": f"Se procesaron y cortaron {len(videos_procesados)} videos con éxito",
            "archivos": videos_procesados
        })

    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
