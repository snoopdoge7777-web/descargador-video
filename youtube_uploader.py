"""
youtube_uploader.py

Maneja la autenticación OAuth2 con Google (usando un refresh_token ya
obtenido de antemano, ver obtener_refresh_token.py) y la subida de
videos a YouTube (como PRIVADO, o sea pendiente de revisión/publicación)
y opcionalmente a una carpeta de Google Drive como backup.

Todo esto usa exclusivamente APIs gratuitas de Google. La única
limitación real es la cuota diaria gratuita de YouTube Data API
(10.000 unidades/día; cada subida de video cuesta 1.600, así que da
para unos ~6 videos por día sin costo).
"""

import os
from pathlib import Path

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/drive.file",
]


def obtener_credenciales() -> Credentials:
    """Reconstruye las credenciales OAuth2 a partir del refresh_token guardado
    en variables de entorno, y las refresca para tener un access_token válido."""
    client_id = os.environ.get("YOUTUBE_CLIENT_ID")
    client_secret = os.environ.get("YOUTUBE_CLIENT_SECRET")
    refresh_token = os.environ.get("YOUTUBE_REFRESH_TOKEN")

    if not (client_id and client_secret and refresh_token):
        raise RuntimeError(
            "Faltan YOUTUBE_CLIENT_ID / YOUTUBE_CLIENT_SECRET / YOUTUBE_REFRESH_TOKEN "
            "en las variables de entorno. Corré obtener_refresh_token.py una vez "
            "en tu computadora para conseguirlos."
        )

    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret,
        scopes=SCOPES,
    )
    creds.refresh(Request())
    return creds


def subir_a_youtube(ruta_video: Path, titulo: str, descripcion: str) -> str:
    """Sube el video a YouTube como PRIVADO (pendiente de revisión/publicación).
    Devuelve el link del video."""
    creds = obtener_credenciales()
    youtube = build("youtube", "v3", credentials=creds)

    body = {
        "snippet": {
            "title": titulo[:100],
            "description": descripcion[:5000],
            "categoryId": "22",
        },
        "status": {
            # "private" = solo vos lo ves hasta que decidas publicarlo.
            # Esto ES el "pendiente" que pediste.
            "privacyStatus": "private",
            "selfDeclaredMadeForKids": False,
        },
    }

    media = MediaFileUpload(str(ruta_video), chunksize=-1, resumable=True, mimetype="video/mp4")
    solicitud = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
    respuesta = solicitud.execute()
    video_id = respuesta["id"]
    return f"https://youtube.com/watch?v={video_id}"


def subir_a_drive(ruta_video: Path, nombre_archivo: str, carpeta_id: str) -> str:
    """Sube una copia del video a una carpeta de Google Drive. Devuelve el link para verlo."""
    creds = obtener_credenciales()
    drive = build("drive", "v3", credentials=creds)

    metadata = {"name": nombre_archivo, "parents": [carpeta_id]}
    media = MediaFileUpload(str(ruta_video), mimetype="video/mp4", resumable=True)
    archivo = drive.files().create(
        body=metadata, media_body=media, fields="id, webViewLink"
    ).execute()
    return archivo.get("webViewLink")
