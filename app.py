import os
import subprocess
from flask import Flask, request, jsonify
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials

app = Flask(__name__)

# ID de la carpeta 'videos' en tu Google Drive (sacado de tu URL de Drive)
DRIVE_FOLDER_ID = "1buXOFhZx-SVgx_3cqUAGJ51ueRc8ighL"

def get_drive_service():
    # Asegúrate de configurar tus credenciales de Google API aquí o por variable de entorno
    creds = Credentials.from_authorized_user_file('token.json', ['https://www.googleapis.com/auth/drive.file'])
    return build('drive', 'v3', credentials=creds)

@app.route('/', methods=['POST'])
def process_video():
    data = request.get_json() or {}
    video_url = data.get('url')
    video_title = data.get('title', 'Video_YouTube')

    if not video_url:
        return jsonify({"status": "error", "message": "Falta la URL"}), 400

    output_filename = f"{video_title}.mp4"

    try:
        # 1. Descargar el video usando yt-dlp
        command = [
            "yt-dlp",
            "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/mp4",
            "--cookies", "www.youtube.com_cookies.txt",
            "-o", output_filename,
            video_url
        ]
        subprocess.run(command, check=True)

        # 2. Subir el video real a Google Drive
        service = get_drive_service()
        file_metadata = {
            'name': output_filename,
            'parents': [DRIVE_FOLDER_ID]
        }
        media = MediaFileUpload(output_filename, mimetype='video/mp4', resumable=True)
        uploaded_file = service.files().create(body=file_metadata, media_body=media, fields='id').execute()

        # 3. Limpiar el archivo local temporal
        if os.path.exists(output_filename):
            os.remove(output_filename)

        return jsonify({
            "status": "success",
            "message": "Video descargado y subido con éxito a Google Drive",
            "file_id": uploaded_file.get('id')
        }), 200

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
