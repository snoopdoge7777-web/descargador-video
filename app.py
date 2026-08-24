import os
import yt_dlp
from flask import Flask, request, jsonify
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials

app = Flask(__name__)

DRIVE_FOLDER_ID = "1buXOFhZx-SVgx_3cqUAGJ51ueRc8ighL"
COOKIES_PATH = "/tmp/youtube_cookies.txt"

def setup_cookies():
    cookies_content = os.environ.get("COOKIES_CONTENT")
    if cookies_content:
        with open(COOKIES_PATH, "w") as f:
            f.write(cookies_content)
        return True
    return False

def get_drive_service():
    creds = Credentials.from_authorized_user_file('token.json', ['https://www.googleapis.com/auth/drive.file'])
    return build('drive', 'v3', credentials=creds)

@app.route('/', methods=['POST'])
def process_video():
    data = request.get_json() or {}
    video_url = data.get('url')
    video_title = data.get('title', 'Video_YouTube')

    if not video_url:
        return jsonify({"status": "error", "message": "Falta la URL"}), 400

    output_filename = f"/tmp/{video_title}.mp4"

    # Configuración anti-bloqueos para YouTube
    ydl_opts = {
        'format': 'best',
        'outtmpl': output_filename,
        'quiet': True,
        'no_warnings': True,
        'extractor_args': {
            'youtube': {
                'player_client': ['ios', 'mweb']
            }
        }
    }

    if setup_cookies():
        ydl_opts['cookiefile'] = COOKIES_PATH

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([video_url])

        file_id = "Drive_No_Configurado"
        if os.path.exists('token.json'):
            service = get_drive_service()
            file_metadata = {
                'name': f"{video_title}.mp4",
                'parents': [DRIVE_FOLDER_ID]
            }
            media = MediaFileUpload(output_filename, mimetype='video/mp4', resumable=True)
            uploaded_file = service.files().create(body=file_metadata, media_body=media, fields='id').execute()
            file_id = uploaded_file.get('id')

        for temp_file in [output_filename, COOKIES_PATH]:
            if os.path.exists(temp_file):
                os.remove(temp_file)

        return jsonify({
            "status": "success",
            "message": "Video procesado con éxito",
            "file_id": file_id
        }), 200

    except Exception as e:
        for temp_file in [output_filename, COOKIES_PATH]:
            if os.path.exists(temp_file):
                os.remove(temp_file)
        return jsonify({"status": "error", "message": f"Error de proceso: {str(e)}"}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
