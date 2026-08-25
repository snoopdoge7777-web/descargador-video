import os
import subprocess
from flask import Flask, request, send_file
import yt_dlp

app = Flask(__name__)

@app.route('/download', methods=['POST'])
def download_video():
    data = request.get_json()
    url = data.get('url')
    
    if not url:
        return {"status": "error", "message": "Falta la URL"}, 400

    raw_path = '/tmp/raw_video.mp4'
    trimmed_path = '/tmp/video.mp4'
    
    for path in [raw_path, trimmed_path]:
        if os.path.exists(path):
            os.remove(path)

    cookie_path = os.path.join(os.path.dirname(__file__), 'www.youtube.com_cookies.txt')

    ydl_opts = {
        'format': 'best',
        'outtmpl': raw_path,
        'quiet': True,
        'extractor_args': {
            'youtube': ['player_client=ios,android,web']
        }
    }

    if os.path.exists(cookie_path):
        ydl_opts['cookiefile'] = cookie_path

    try:
        # 1. Descargar video
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        # 2. Recortar silencios con ffmpeg (Filtro silenceremove)
        # Recorta silencios al inicio y entremedio menores a -30dB y duración mayor a 0.5s
        ffmpeg_cmd = [
            'ffmpeg', '-y', '-i', raw_path,
            '-af', 'silenceremove=start_periods=1:start_duration=0.5:start_threshold=-30dB:detection=peak,areverse,silenceremove=start_periods=1:start_duration=0.5:start_threshold=-30dB:detection=peak,areverse',
            '-c:v', 'copy',
            trimmed_path
        ]
        
        subprocess.run(ffmpeg_cmd, check=True)
        
        return send_file(trimmed_path, as_attachment=True, download_name="video.mp4", mimetype="video/mp4")
    except Exception as e:
        return {"status": "error", "message": f"Error de proceso: {str(e)}"}, 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
