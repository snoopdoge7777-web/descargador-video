"""
app.py

Microservicio que recibe {url, inicio, fin} por HTTP, descarga el video con
yt-dlp, lo recorta con ffmpeg, y sube el resultado a un canal de Discord
via webhook (que actúa como almacenamiento/CDN gratuito).

Pensado para desplegarse gratis en Render.com (o Railway/Fly.io) usando
el Dockerfile incluido.

Variables de entorno requeridas:
- DISCORD_WEBHOOK_URL: la URL del webhook del canal de Discord donde se
  van a subir los clips.
- API_TOKEN: un token simple para que no cualquiera pueda usar tu servicio
  público (se manda como header "Authorization: Bearer <token>").
"""

import os
import re
import subprocess
import uuid
from pathlib import Path

import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
API_TOKEN = os.environ.get("API_TOKEN", "")
TMP_DIR = Path("/tmp/clips")
TMP_DIR.mkdir(parents=True, exist_ok=True)

# Límite de Discord para webhooks sin boost de servidor: 25 MB
LIMITE_DISCORD_MB = 25


def tiempo_a_segundos(tiempo_str: str) -> int:
    partes = tiempo_str.strip().split(":")
    if len(partes) == 3:
        h, m, s = partes
    elif len(partes) == 2:
        h, m, s = 0, *partes
    else:
        raise ValueError(f"Formato de tiempo inválido: '{tiempo_str}'")
    h, m, s = int(h), int(m), int(s)
    if m >= 60 or s >= 60 or h < 0 or m < 0 or s < 0:
        raise ValueError(f"Tiempo inválido: '{tiempo_str}'")
    return h * 3600 + m * 60 + s


def validar_url(url: str):
    patron = re.compile(
        r"^(https?://)?(www\.)?(youtube\.com/watch\?v=|youtu\.be/)[\w-]+"
    )
    if not patron.match(url):
        raise ValueError(f"La URL no parece ser un link válido de YouTube: '{url}'")


def obtener_duracion(url: str) -> float:
    import json
    resultado = subprocess.run(
        ["yt-dlp", "--dump-json", "--no-playlist", url],
        capture_output=True, text=True,
    )
    if resultado.returncode != 0:
        raise RuntimeError(f"No se pudo leer el video: {resultado.stderr.strip()}")
    info = json.loads(resultado.stdout)
    return float(info.get("duration", 0))


def descargar_video(url: str, destino: Path):
    comando = [
        "yt-dlp",
        "-f", "bv*[height<=720][ext=mp4]+ba[ext=m4a]/b[ext=mp4]/b",
        "--no-playlist",
        "-o", str(destino),
        url,
    ]
    resultado = subprocess.run(comando, capture_output=True, text=True)
    if resultado.returncode != 0:
        raise RuntimeError(f"Falló la descarga: {resultado.stderr.strip()}")


def recortar_video(origen: Path, destino: Path, inicio: str, fin: str):
    comando = [
        "ffmpeg", "-y",
        "-ss", inicio, "-to", fin,
        "-i", str(origen),
        "-c", "copy",
        str(destino),
    ]
    resultado = subprocess.run(comando, capture_output=True, text=True)
    if resultado.returncode != 0:
        raise RuntimeError(f"Falló el recorte: {resultado.stderr.strip()}")


def comprimir_si_hace_falta(ruta: Path) -> Path:
    """Si el clip supera el límite de Discord, lo recomprime bajando el bitrate."""
    tamano_mb = ruta.stat().st_size / (1024 * 1024)
    if tamano_mb <= LIMITE_DISCORD_MB:
        return ruta

    comprimido = ruta.with_name(ruta.stem + "_comp.mp4")
    comando = [
        "ffmpeg", "-y", "-i", str(ruta),
        "-b:v", "800k", "-b:a", "96k",
        str(comprimido),
    ]
    subprocess.run(comando, capture_output=True, text=True)
    return comprimido


def subir_a_discord(ruta: Path) -> str:
    if not DISCORD_WEBHOOK_URL:
        raise RuntimeError("Falta configurar DISCORD_WEBHOOK_URL en el servidor.")

    with open(ruta, "rb") as f:
        archivos = {"file": (ruta.name, f, "video/mp4")}
        resp = requests.post(DISCORD_WEBHOOK_URL + "?wait=true", files=archivos)

    if resp.status_code not in (200, 201):
        raise RuntimeError(f"Falló la subida a Discord: {resp.status_code} {resp.text}")

    data = resp.json()
    return data["attachments"][0]["url"]


@app.route("/recortar", methods=["POST"])
def recortar():
    # Autenticación simple
    auth = request.headers.get("Authorization", "")
    if API_TOKEN and auth != f"Bearer {API_TOKEN}":
        return jsonify({"error": "No autorizado"}), 401

    body = request.get_json(force=True, silent=True) or {}
    url = body.get("url", "")
    inicio = body.get("inicio", "")
    fin = body.get("fin", "")

    id_trabajo = uuid.uuid4().hex[:8]
    ruta_full = TMP_DIR / f"{id_trabajo}_full.mp4"
    ruta_clip = TMP_DIR / f"{id_trabajo}_clip.mp4"

    try:
        validar_url(url)
        duracion = obtener_duracion(url)

        inicio_seg = tiempo_a_segundos(inicio)
        fin_seg = tiempo_a_segundos(fin)
        if inicio_seg >= fin_seg:
            raise ValueError("El inicio debe ser menor al fin.")
        if fin_seg > duracion:
            raise ValueError(
                f"El fin ({fin}) supera la duración del video ({int(duracion)}s)."
            )

        descargar_video(url, ruta_full)
        recortar_video(ruta_full, ruta_clip, inicio, fin)
        ruta_final = comprimir_si_hace_falta(ruta_clip)

        link_discord = subir_a_discord(ruta_final)

        return jsonify({
            "ok": True,
            "link_discord": link_discord,
            "titulo_original": url,
        })

    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    except RuntimeError as e:
        return jsonify({"ok": False, "error": str(e)}), 500
    finally:
        for p in (ruta_full, ruta_clip, ruta_clip.with_name(ruta_clip.stem + "_comp.mp4")):
            if p.exists():
                p.unlink()


@app.route("/", methods=["GET"])
def home():
    return jsonify({"status": "ok", "servicio": "recorte-youtube"})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
