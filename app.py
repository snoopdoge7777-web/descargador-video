def descargar_video(url: str, destino: Path):
    # 1. Verificar si existe la variable COOKIES_CONTENT y crear el archivo temporal
    cookies_content = os.environ.get("COOKIES_CONTENT")
    cookies_path = None
    
    if cookies_content:
        cookies_path = TMP_DIR / "cookies.txt"
        with open(cookies_path, "w", encoding="utf-8") as f:
            f.write(cookies_content)

    # 2. Armar el comando para yt-dlp
    comando = [
        "yt-dlp",
        "-f", "bv*[height<=720][ext=mp4]+ba[ext=m4a]/b[ext=mp4]/b",
        "--no-playlist",
        "-o", str(destino),
    ]

    # Si tenemos el archivo de cookies, se lo pasamos a yt-dlp
    if cookies_path and cookies_path.exists():
        comando.extend(["--cookies", str(cookies_path)])

    comando.append(url)

    # 3. Ejecutar descarga con yt-dlp
    resultado = subprocess.run(comando, capture_output=True, text=True)
    
    # Limpiar el archivo de cookies temporal por seguridad
    if cookies_path and cookies_path.exists():
        try:
            cookies_path.unlink()
        except Exception:
            pass

    if resultado.returncode == 0 and destino.exists():
        return

    # Fallback con pytubefix si yt-dlp falla
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
