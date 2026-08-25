import os
from flask import Flask, request, send_file
import yt_dlp

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

    # Detectar el archivo de cookies local si existe en el repositorio
    cookie_path = os.path.join(os.path.dirname(__file__), 'www.youtube.com_cookies.txt')

    ydl_opts = {
        'format': 'best',
        'outtmpl': output_path,
        'extractor_args': {
            'youtube': ['player_client=mweb,ios,web']
        },
        'quiet': True
    }

    if os.path.exists(cookie_path):
        ydl_opts['cookiefile'] = cookie_path

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        
        return send_file(output_path, as_attachment=True, download_name="video.mp4", mimetype="video/mp4")
    except Exception as e:
        return {"status": "error", "message": f"Error de proceso: {str(e)}"}, 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
