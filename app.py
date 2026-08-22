# Leemos tanto de JSON (si llega) como de parámetros GET en la URL
    data = request.get_json(force=True, silent=True) or {}
    
    urls = request.args.get("url") or data.get("urls") or data.get("url")
    if isinstance(urls, str):
        urls = [urls]
    
    job_id = request.args.get("job_id") or data.get("job_id") or uuid.uuid4().hex[:8]
