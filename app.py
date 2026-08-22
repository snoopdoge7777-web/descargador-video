"""
app.py - Microservicio automático de recorte de YouTube.
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

LIMITE_DISCORD_MB = 25


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
    data = resp.json()
    return data["attachments"][0]["url"]


def validar_url(url: str):
    patron = re.compile(
        r"^(https?://)?(www\.)?(youtube\.com/watch\?v=|youtu\.be/)[\w-]+"
    )
    if not patron.match(url):
        raise ValueError(f"La URL no parece ser un link válido de YouTube: '{url}'")


def descargar_video(url: str, destino: Path):
    comando = [
        "yt-dlp",
        "-f", "best[height<=720]/best",
        "--no-playlist",
        "-o", str(destino),
        url,
    ]
    resultado = subprocess.run(comando, capture_output=True, text=True)
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


@app.route("/", methods=["GET", "POST"])
def procesar():
    auth = request.headers.get("Authorization", "")
    if API_TOKEN and auth != f"Bearer {API_TOKEN}":
        return jsonify({"error": "No autorizado"}), 401

    data = request.get_json(force=True, silent=True) or {}

    # Capturamos parámetros tanto si vienen por la URL (GET) como por JSON (POST)
    urls_param = request.args.get("url") or data.get("urls") or data.get("url")
    if isinstance(urls_param, str):
        urls = [urls_param]
    elif isinstance(urls_param, list):
        urls = urls_param
    else:
        urls = []

    job_id = request.args.get("job_id") or data.get("job_id") or uuid.uuid4().hex[:8]

    if not urls:
        return jsonify({"error": "No URL provided", "status": "ok"}), 400

    max_clips = int(request.args.get("max_clips", data.get("max_clips", 8)))
    silencio_db = int(request.args.get("silencio_db", data.get("silencio_db", -30)))
    silencio_min_dur = float(request.args.get("silencio_min_dur", data.get("silencio_min_dur", 1.0)))
    clip_min_dur = float(request.args.get("clip_min_dur", data.get("clip_min_dur", 5.0)))

    enviar_a_discord(f"⏳ Trabajo `{job_id}` iniciado — {len(urls)} link(s) para procesar.")

    resultados_totales = []

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
                enviar_a_discord(f"⚠️ Trabajo `{job_id}` — no se detectaron cortes en {url}")
                continue

            if len(segmentos) > max_clips:
                segmentos = sorted(segmentos, key=lambda s: s[1] - s[0], reverse=True)[:max_clips]
                segmentos.sort(key=lambda s: s[0])

            for i, (inicio_seg, fin_seg) in enumerate(segmentos):
                ruta_clip = TMP_DIR / f"{job_id}_{idx}_clip{i}.mp4"
                clips_temporales.append(ruta_clip)

                recortar_video(ruta_full, ruta_clip, inicio_seg, fin_seg)
                ruta_final = comprimir_si_hace_falta(ruta_clip)
                clips_temporales.append(ruta_final)

                mensaje = (
                    f"✅ Trabajo `{job_id}` — clip {i + 1}/{len(segmentos)} de {url} "
                    f"[{formatear_tiempo(inicio_seg)} - {formatear_tiempo(fin_seg)}] "
                    f"— PENDIENTE DE REVISIÓN para subir a YouTube"
                )
                link_discord = enviar_archivo_a_discord(ruta_final, mensaje)

                resultados_totales.append({
                    "url_original": url,
                    "clip": i + 1,
                    "inicio": formatear_tiempo(inicio_seg),
                    "fin": formatear_tiempo(fin_seg),
                    "link_discord": link_discord,
                })

        except Exception as e:
            enviar_a_discord(f"❌ Trabajo `{job_id}` — error con {url}: {e}")

        finally:
            if ruta_full.exists():
                ruta_full.unlink()
            for p in clips_temporales:
                if p.exists():
                    p.unlink()

    enviar_a_discord(
        f"🏁 Trabajo `{job_id}` finalizado — {len(resultados_totales)} clip(s) subidos a Discord, "
        f"pendientes de revisión y subida manual a YouTube."
    )

    return jsonify({"ok": True, "job_id": job_id, "clips": resultados_totales})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
