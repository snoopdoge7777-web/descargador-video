from flask import Flask, request, send_file
import yt_dlp
import osfrom flask import Flask, request, send_file
import yt_dlp
import os

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

    # Buscar el archivo de cookies subido en el repositorio
    cookie_path = os.path.join(os.path.dirname(__file__), 'www.youtube.com_cookies.txt')

    ydl_opts = {
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'outtmpl': output_path,
        'extractor_args': {
            'youtube': ['player_client=mweb,ios,web']
        },
        'quiet': True
    }

    # Si existe el archivo de cookies, agregarlo a la configuración
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

    ydl_opts = {
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'outtmpl': output_path,
        'extractor_args': {
            'youtube': ['player_client=mweb,ios,web']
        },
        'quiet': True
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        
        return send_file(output_path, as_attachment=True, download_name="video.mp4", mimetype="video/mp4")
    except Exception as e:
        return {"status": "error", "message": f"Error de proceso: {str(e)}"}, 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
