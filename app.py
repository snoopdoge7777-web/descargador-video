import os
import requests
from flask import Flask, request, send_file

app = Flask(__name__)

@app.route('/download', methods=['POST'])
def download_video():
    data = request.get_json()
    url = data.get('url')
    
    if not url:
        return {"status": "error", "message": "Falta la URL"}, 400

    output_path = '/tmp/video.mp4'
    if os.path.exists(output_path):
        os.remove(output_path)

    # API de procesado directo de video
    cobalt_api = "https://api.cobalt.tools/api/json"
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json"
    }
    payload = {
        "url": url,
        "vCodec": "h264",
        "videoQuality": "720"
    }

    try:
        # Solicitar enlace de descarga directo
        res = requests.post(cobalt_api, json=payload, headers=headers)
        res_data = res.json()
        
        if res_data.get("status") == "error":
            return {"status": "error", "message": res_data.get("text")}, 500

        video_url = res_data.get("url")
        if not video_url:
            return {"status": "error", "message": "No se pudo obtener la URL de descarga"}, 500

        # Descargar el archivo binario
        video_stream = requests.get(video_url, stream=True)
        with open(output_path, 'wb') as f:
            for chunk in video_stream.iter_content(chunk_size=8192):
                f.write(chunk)
        
        return send_file(output_path, as_attachment=True, download_name="video.mp4", mimetype="video/mp4")

    except Exception as e:
        return {"status": "error", "message": f"Error de proceso: {str(e)}"}, 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
