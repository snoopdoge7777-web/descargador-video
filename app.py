import os
import subprocess
from flask import Flask, request, jsonify
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials

app = Flask(__name__)

DRIVE_FOLDER_ID = "1buXOFhZx-SVgx_3cqUAGJ51ueRc8ighL"

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

    output_filename = f"{video_title}.mp4"

    try:
        # Comando flexible de yt-dlp
        command = [
            "yt-dlp",
            "-f", "b/bv*+ba",  # Elige la mejor calidad disponible y la convierte a mp4
            "--merge-output-format", "mp4",
            "-o", output_filename
        ]

        # Si el archivo de cookies existe, se incluye en el comando
        if os.path.exists("www.youtube.com_cookies.txt"):
            command.extend(["--cookies", "www.youtube.com_cookies.txt"])

        command.append(video_url)

        # Ejecutar descarga
        subprocess.run(command, check=True)

        # Subir a Google Drive (Si ya tienes configuradas las credenciales)
        if os.path.exists('token.json'):
            service = get_drive_service()
            file_metadata = {
                'name': output_filename,
                'parents': [DRIVE_FOLDER_ID]
            }
            media = MediaFileUpload(output_filename, mimetype='video/mp4', resumable=True)
            uploaded_file = service.files().create(body=file_metadata, media_body=media, fields='id').execute()
            file_id = uploaded_file.get('id')
        else:
            file_id = "Drive_No_Configurado"

        # Limpieza local
        if os.path.exists(output_filename):
            os.remove(output_filename)

        return jsonify({
            "status": "success",
            "message": "Video procesado con éxito",
            "file_id": file_id
        }), 200

    except subprocess.CalledProcessError as e:
        return jsonify({"status": "error", "message": f"Error descargando el video con yt-dlp: {str(e)}"}), 500
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
