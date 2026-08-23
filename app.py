"""
app.py

Microservicio completo de recorte automático de YouTube con soporte de Cookies para Render.
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
GOOGLE_DRIVE_FOLDER_ID = os.environ.get("GOOGLE_DRIVE_FOLDER_ID")

TMP_DIR = Path("/tmp/clips")
TMP_DIR.mkdir(parents=True, exist_ok=True)

LIMITE_DISCORD_MB = 25


# ----------------------------------------------------------------------
# Discord
# ----------------------------------------------------------------------

def enviar_a_discord(mensaje: str):
    if not DISCORD_WEBHOOK_URL:
        return
    try:
        requests.post(DISCORD_WEBHOOK_URL, json={"content": mensaje[:1900]}, timeout=15)
    except Exception:
        pass


def enviar_archivo_a_discord(ruta: Path, mensaje: str) -> str:
    if not DISCORD_WEBHOOK_URL:
        raise RuntimeError("Falta configurar DISCORD_WEBHOOK_URL en el servidor.")
    with open(ruta, "rb") as f:
        resp = requests.post(
            DISCORD_WEBHOOK_URL + "?wait=true",
            data={"content": mensaje[:1900]},
            files={"file": (ruta.name, f, "video/mp4")},
            timeout=120,
        )
    if resp.status_code not in (200, 201):
        raise RuntimeError(f"Falló la subida a Discord: {resp.status_code} {resp.text}")
    return resp.json()["attachments"][0]["url"]


# ----------------------------------------------------------------------
# Descarga: yt-dlp primero (con cookies), pytubefix como respaldo
# ----------------------------------------------------------------------

def validar_url(url: str):
    patron = re.compile(
        r"^(https?://)?(www\.)?(youtube\.com/watch\?v=|youtu\.be/)[\w-]+"
    )
    if not patron.match(url):
        raise ValueError(f"La URL no parece ser un link válido de YouTube: '{url}'")


def descargar_video(url: str, destino: Path):
    cookies_content = os.environ.get("COOKIES_CONTENT")
    cookies_path = None
    
    if cookies_content:
        cookies_path = TMP_DIR / "cookies.txt"
        with open(cookies_path, "w", encoding="utf-8") as f:
            f.write(cookies_content)

    comando = [
        "yt-dlp",
        "-f", "bv*[height<=720][ext=mp4]+ba[ext=m4a]/b[ext=mp4]/b",
        "--no-playlist",
        "-o", str(destino),
    ]

    if cookies_path and cookies_path.exists():
        comando.extend(["--cookies", str(cookies_path)])

    comando.append(url)

    resultado = subprocess.run(comando, capture_output=True, text=True)
    
    if cookies_path and cookies_path.exists():
        try:
            cookies_path.unlink()
        except Exception:
            pass

    if resultado.returncode == 0 and destino.exists():
        return

    try:
        from pytubefix import YouTube
        yt = YouTube(url)
        stream = yt.streams.get_highest_resolution()
        stream.download(output_path=str(destino.parent), filename=destino.name)
    except Exception as e:
        raise RuntimeError(
            f"Falló la descarga con yt-dlp y con pytubefix. "
            f"yt-dlp: {resultado.stderr.strip()[:300]} | pytubefix: {e}"
        )

    if not destino.exists():
        raise RuntimeError("No se pudo descargar el video con ningún método.")


def obtener_duracion(ruta_video: Path) -> float:
    comando = [
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(ruta_video),
    ]
    resultado = subprocess.run(comando, capture_output=True, text=True)
    try:
        return float(resultado.stdout.strip())
    except ValueError:
        raise RuntimeError("No se pudo determinar la duración del video descargado.")


# ----------------------------------------------------------------------
# Detección automática de segmentos + recorte
# ----------------------------------------------------------------------

def formatear_tiempo(segundos: float) -> str:
    segundos = max(0, int(segundos))
    h, resto = divmod(segundos, 3600)
    m, s = divmod(resto, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def detectar_segmentos_habla(
    ruta_video: Path,
    duracion_total: float,
    silencio_db: int = -30,
    silencio_min_dur: float = 1.0,
    clip_min_dur: float = 5.0,
):
    comando = [
        "ffmpeg", "-i", str(ruta_video),
        "-af", f"silencedetect=noise={silencio_db}dB:d={silencio_min_dur}",
        "-f", "null", "-",
    ]
    resultado = subprocess.run(comando, capture_output=True, text=True)
    salida = resultado.stderr

    silence_starts = [float(x) for x in re.findall(r"silence_start:\s*([\d.]+)", salida)]
    silence_ends = [float(x) for x in re.findall(r"silence_end:\s*([\d.]+)", salida)]

    if len(silence_ends) < len(silence_starts):
        silence_ends.append(duracion_total)

    pares_silencio = list(zip(silence_starts, silence_ends))

    segmentos = []
    cursor = 0.0
    for s_inicio, s_fin in pares_silencio:
        if s_inicio - cursor >= clip_min_dur:
            segmentos.append((cursor, s_inicio))
        cursor = s_fin

    if duracion_total - cursor >= clip_min_dur:
        segmentos.append((cursor, duracion_total))

    return segmentos


def recortar_video(origen: Path, destino: Path, inicio_seg: float, fin_seg: float):
    comando = [
        "ffmpeg", "-y",
        "-ss", str(inicio_seg), "-to", str(fin_seg),
        "-i", str(origen),
        "-c", "copy",
        str(destino),
    ]
    resultado = subprocess.run(comando, capture_output=True, text=True)
    if resultado.returncode != 0:
        raise RuntimeError(f"Falló el recorte: {resultado.stderr.strip()}")


def comprimir_si_hace_falta(ruta: Path) -> Path:
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


# ----------------------------------------------------------------------
# Endpoint principal
# ----------------------------------------------------------------------

@app.route("/", methods=["GET", "POST"])
def procesar():
    if request.method == "GET":
        return jsonify({"status": "ok", "servicio": "recorte-youtube-automatico"})

    auth = request.headers.get("Authorization", "")
    if API_TOKEN and auth != f"Bearer {API_TOKEN}":
        return jsonify({"error": "No autorizado"}), 401

    data = request.get_json(force=True, silent=True) or {}
    job_id = data.get("job_id") or uuid.uuid4().hex[:8]
    titulo_base = data.get("titulo_base", "Short")

    urls = data.get("urls")
    if not urls:
        url_unico = data.get("url")
        urls = [url_unico] if url_unico else []
    if not urls:
        return jsonify({"error": "No se proporcionó ninguna URL"}), 400

    max_clips = int(data.get("max_clips", 8))
    silencio_db = int(data.get("silencio_db", -30))
    silencio_min_dur = float(data.get("silencio_min_dur", 1.0))
    clip_min_dur = float(data.get("clip_min_dur", 5.0))

    subir_youtube = all([
        os.environ.get("YOUTUBE_CLIENT_ID"),
        os.environ.get("YOUTUBE_CLIENT_SECRET"),
        os.environ.get("YOUTUBE_REFRESH_TOKEN"),
    ])
    subir_drive = subir_youtube and bool(GOOGLE_DRIVE_FOLDER_ID)

    enviar_a_discord(
        f"⏳ Trabajo `{job_id}` iniciado — {len(urls)} link(s). "
        f"YouTube: {'activado' if subir_youtube else 'desactivado'} | "
        f"Drive: {'activado' if subir_drive else 'desactivado'}"
    )

    resultados_totales = []
    errores_totales = []
    contador_global = 1

    for idx, url in enumerate(urls):
        ruta_full = TMP_DIR / f"{job_id}_{idx}_full.mp4"
        clips_temporales = []

        try:
            validar_url(url)
            enviar_a_discord(f"⬇️ Trabajo `{job_id}` — descargando link {idx + 1}/{len(urls)}: {url}")
            descargar_video(url, ruta_full)

            duracion = obtener_duracion(ruta_full)
            segmentos = detectar_segmentos_habla(
                ruta_full, duracion, silencio_db, silencio_min_dur, clip_min_dur
            )

            if not segmentos:
                mensaje_error = f"No se detectaron cortes en {url}"
                errores_totales.append({"url": url, "error": mensaje_error})
                enviar_a_discord(f"⚠️ Trabajo `{job_id}` — {mensaje_error}")
                continue

            if len(segmentos) > max_clips:
                segmentos = sorted(segmentos, key=lambda s: s[1] - s[0], reverse=True)[:max_clips]
                segmentos.sort(key=lambda s: s[0])

            for inicio_seg, fin_seg in segmentos:
                numero = f"{contador_global:02d}"
                titulo_clip = f"{titulo_base} {numero}"

                ruta_clip = TMP_DIR / f"{job_id}_clip{numero}.mp4"
                clips_temporales.append(ruta_clip)
                recortar_video(ruta_full, ruta_clip, inicio_seg, fin_seg)
                ruta_final = comprimir_si_hace_falta(ruta_clip)
                clips_temporales.append(ruta_final)

                resultado_clip = {
                    "numero": numero,
                    "titulo": titulo_clip,
                    "url_original": url,
                    "inicio": formatear_tiempo(inicio_seg),
                    "fin": formatear_tiempo(fin_seg),
                }

                mensaje = (
                    f"✅ `{titulo_clip}` (de {url}, "
                    f"{formatear_tiempo(inicio_seg)}-{formatear_tiempo(fin_seg)}) — pendiente de revisión"
                )
                resultado_clip["link_discord"] = enviar_archivo_a_discord(ruta_final, mensaje)

                if subir_youtube:
                    try:
                        from youtube_uploader import subir_a_youtube
                        link_yt = subir_a_youtube(
                            ruta_final, titulo_clip,
                            descripcion=f"Recortado automáticamente de {url}",
                        )
                        resultado_clip["link_youtube_pendiente"] = link_yt
                        enviar_a_discord(f"📤 `{titulo_clip}` subido a YouTube como privado (pendiente): {link_yt}")
                    except Exception as e:
                        enviar_a_discord(f"⚠️ `{titulo_clip}` no se pudo subir a YouTube: {e}")

                if subir_drive:
                    try:
                        from youtube_uploader import subir_a_drive
                        link_drive = subir_a_drive(ruta_final, f"{titulo_clip}.mp4", GOOGLE_DRIVE_FOLDER_ID)
                        resultado_clip["link_drive"] = link_drive
                    except Exception as e:
                        enviar_a_discord(f"⚠️ `{titulo_clip}` no se pudo respaldar en Drive: {e}")

                resultados_totales.append(resultado_clip)
                contador_global += 1

        except Exception as e:
            errores_totales.append({"url": url, "error": str(e)})
            enviar_a_discord(f"❌ Trabajo `{job_id}` — error con {url}: {e}")

        finally:
            if ruta_full.exists():
                ruta_full.unlink()
            for p in clips_temporales:
                if p.exists():
                    p.unlink()

    enviar_a_discord(
        f"🏁 Trabajo `{job_id}` finalizado — {len(resultados_totales)} clip(s) generados. "
        f"Revisalos y publicá los que quieras."
    )

    return jsonify({
        "ok": True,
        "job_id": job_id,
        "clips": resultados_totales,
        "errores": errores_totales,
    })


# ----------------------------------------------------------------------
# Chequeo de salud / configuración
# ----------------------------------------------------------------------

@app.route("/health", methods=["GET"])
def health():
    estado = {
        "servicio": "ok",
        "hosting": "Render",
        "herramientas": ["yt-dlp", "pytubefix", "ffmpeg"],
        "discord_configurado": bool(DISCORD_WEBHOOK_URL),
        "cookies_configuradas": bool(os.environ.get("COOKIES_CONTENT")),
    }

    youtube_configurado = all([
        os.environ.get("YOUTUBE_CLIENT_ID"),
        os.environ.get("YOUTUBE_CLIENT_SECRET"),
        os.environ.get("YOUTUBE_REFRESH_TOKEN"),
    ])
    estado["youtube_configurado"] = youtube_configurado

    if youtube_configurado:
        try:
            from youtube_uploader import obtener_credenciales
            obtener_credenciales()
            estado["youtube_token_valido"] = True
        except Exception as e:
            estado["youtube_token_valido"] = False
            estado["youtube_error"] = str(e)

    estado["drive_configurado"] = bool(GOOGLE_DRIVE_FOLDER_ID)

    return jsonify(estado)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
