"""
app.py

Microservicio 100% automático: recibe solo {url} de YouTube, descarga el
video con yt-dlp, detecta automáticamente los segmentos de "habla" del
video (separados por silencios / pausas) usando el filtro silencedetect
de ffmpeg, recorta cada segmento, y sube cada clip resultante a Discord
via webhook (que actúa como almacenamiento/CDN gratuito).

No hace falta indicar tiempos de inicio/fin: el propio análisis de audio
decide dónde cortar.

Variables de entorno requeridas:
- DISCORD_WEBHOOK_URL: URL del webhook del canal de Discord.
- API_TOKEN: token simple para proteger el endpoint público.

Parámetros opcionales en el body:
- max_clips (int, default 8): tope de clips a generar. Si se detectan más
  segmentos que este número, se conservan los más largos (los más
  "sustanciales") y se descartan pausas cortas irrelevantes.
- silencio_db (int, default -30): sensibilidad del detector de silencio,
  en dB. Más negativo = necesita más silencio real para cortar.
- silencio_min_dur (float, default 1.0): duración mínima de silencio (seg)
  para considerarlo un corte de escena.
- clip_min_dur (float, default 5.0): duración mínima de un clip para que
  valga la pena subirlo.
"""

import os
import re
import subprocess
import uuid
from pathlib import Path

import requests
from flask import Flask, jsonify, request

app = Flask(__name__)

DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
API_TOKEN = os.environ.get("API_TOKEN", "")
TMP_DIR = Path("/tmp/clips")
TMP_DIR.mkdir(parents=True, exist_ok=True)

LIMITE_DISCORD_MB = 25


# ----------------------------------------------------------------------
# Utilidades básicas
# ----------------------------------------------------------------------

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
      capture_output=True,
      text=True,
  )
  if resultado.returncode != 0:
    raise RuntimeError(f"No se pudo leer el video: {resultado.stderr.strip()}")
  info = json.loads(resultado.stdout)
  return float(info.get("duration", 0))


def descargar_video(url: str, destino: Path):
  comando = [
      "yt-dlp",
      "-f",
      "bv*[height<=720][ext=mp4]+ba[ext=m4a]/b[ext=mp4]/b",
      "--no-playlist",
      "-o",
      str(destino),
      url,
  ]
  resultado = subprocess.run(comando, capture_output=True, text=True)
  if resultado.returncode != 0:
    raise RuntimeError(f"Falló la descarga: {resultado.stderr.strip()}")


def formatear_tiempo(segundos: float) -> str:
  segundos = max(0, int(segundos))
  h, resto = divmod(segundos, 3600)
  m, s = divmod(resto, 60)
  return f"{h:02d}:{m:02d}:{s:02d}"


# ----------------------------------------------------------------------
# Detección automática de segmentos (silencio / cambio de escena)
# ----------------------------------------------------------------------

def detectar_segmentos_habla(
    ruta_video: Path,
    duracion_total: float,
    silencio_db: int = -30,
    silencio_min_dur: float = 1.0,
    clip_min_dur: float = 5.0,
):
  """Corre ffmpeg con el filtro silencedetect para encontrar los tramos de

  silencio, y de ahí deduce los tramos de "habla/acción" (lo que queda
  entre silencios). Cada tramo de habla es un clip candidato.
  """
  comando = [
      "ffmpeg",
      "-i",
      str(ruta_video),
      "-af",
      f"silencedetect=noise={silencio_db}dB:d={silencio_min_dur}",
      "-f",
      "null",
      "-",
  ]
  resultado = subprocess.run(comando, capture_output=True, text=True)
  salida = resultado.stderr

  silence_starts = [
      float(x) for x in re.findall(r"silence_start:\s*([\d.]+)", salida)
  ]
  silence_ends = [
      float(x) for x in re.findall(r"silence_end:\s*([\d.]+)", salida)
  ]

  # Si el video termina en silencio, ffmpeg puede no imprimir el
  # silence_end final: lo completamos con el final del video.
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
      "ffmpeg",
      "-y",
      "-ss",
      str(inicio_seg),
      "-to",
      str(fin_seg),
      "-i",
      str(origen),
      "-c",
      "copy",
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
      "ffmpeg",
      "-y",
      "-i",
      str(ruta),
      "-b:v",
      "800k",
      "-b:a",
      "96k",
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
    raise RuntimeError(
        f"Falló la subida a Discord: {resp.status_code} {resp.text}"
    )
  data = resp.json()
  return data["attachments"][0]["url"]


# ----------------------------------------------------------------------
# Endpoint principal
# ----------------------------------------------------------------------


@app.route("/auto-recortar", methods=["POST"])
def auto_recortar():
  auth = request.headers.get("Authorization", "")
  if API_TOKEN and auth != f"Bearer {API_TOKEN}":
    return jsonify({"error": "No autorizado"}), 401

  body = request.get_json(force=True, silent=True) or {}
  url = body.get("url", "")
  max_clips = int(body.get("max_clips", 8))
  silencio_db = int(body.get("silencio_db", -30))
  silencio_min_dur = float(body.get("silencio_min_dur", 1.0))
  clip_min_dur = float(body.get("clip_min_dur", 5.0))

  id_trabajo = uuid.uuid4().hex[:8]
  ruta_full = TMP_DIR / f"{id_trabajo}_full.mp4"
  clips_temporales = []

  try:
    validar_url(url)
    duracion = obtener_duracion(url)
    descargar_video(url, ruta_full)

    segmentos = detectar_segmentos_habla(
        ruta_full, duracion, silencio_db, silencio_min_dur, clip_min_dur
    )

    if not segmentos:
      raise RuntimeError(
          "No se detectaron cortes de silencio/escena en el video. Probá"
          " bajar 'silencio_min_dur' o subir 'silencio_db'."
      )

    # Si hay demasiados segmentos, nos quedamos con los más largos
    # (más sustanciales) y descartamos pausas cortas sin contenido.
    if len(segmentos) > max_clips:
      segmentos = sorted(
          segmentos, key=lambda s: s[1] - s[0], reverse=True
      )[:max_clips]
      segmentos.sort(key=lambda s: s[0])

    resultados = []
    for i, (inicio_seg, fin_seg) in enumerate(segmentos):
      ruta_clip = TMP_DIR / f"{id_trabajo}_clip{i}.mp4"
      clips_temporales.append(ruta_clip)

      recortar_video(ruta_full, ruta_clip, inicio_seg, fin_seg)
      ruta_final = comprimir_si_hace_falta(ruta_clip)
      clips_temporales.append(ruta_final)

      link = subir_a_discord(ruta_final)
      resultados.append({
          "inicio": formatear_tiempo(inicio_seg),
          "fin": formatear_tiempo(fin_seg),
          "link": link,
      })

    return jsonify(
        {"ok": True, "clips": resultados, "total_clips": len(resultados)}
    )

  except ValueError as e:
    return jsonify({"ok": False, "error": str(e)}), 400
  except RuntimeError as e:
    return jsonify({"ok": False, "error": str(e)}), 500
  finally:
    if ruta_full.exists():
      ruta_full.unlink()
    for p in clips_temporales:
      if p.exists():
        p.unlink()


@app.route("/", methods=["GET"])
def home():
  return jsonify({"status": "ok", "servicio": "recorte-youtube-automatico"})


if __name__ == "__main__":
  port = int(os.environ.get("PORT", 8080))
  app.run(host="0.0.0.0", port=port)
```[cite: 6]

Copia este contenido en tu archivo `app.py`, súbelo a GitHub y haz el *Manual Deploy* en Render para que quede perfectamente sincronizado con el JSON automático de n8n[cite: 8].
