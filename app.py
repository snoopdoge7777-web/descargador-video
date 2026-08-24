import os
from flask import Flask, request, jsonify

app = Flask(__name__)

@app.route('/', methods=['POST'])
def process_video():
    data = request.get_json() or {}
    video_url = data.get('url')
    video_title = data.get('title', 'Video_Sin_Titulo')

    if not video_url:
        return jsonify({"status": "error", "message": "Falta el campo 'url'"}), 400

    try:
        # Aquí va la lógica de descarga/edición con yt-dlp o pytubefix
        print(f"Procesando URL: {video_url} con título: {video_title}")
        
        # Ejemplo de respuesta exitosa para n8n
        return jsonify({
            "status": "success",
            "message": "Video recibido y procesado correctamente",
            "url": video_url,
            "title": video_title
        }), 200

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
