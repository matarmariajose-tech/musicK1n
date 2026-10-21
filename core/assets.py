import json
import re
import subprocess
from pathlib import Path

from storage import connect
from validation import text


def asset_path(data, identifier, kind=None):
    if not re.fullmatch(r"[a-f0-9]{32}", identifier):
        raise ValueError("Id de archivo inválido")
    db = connect(data)
    a = db.execute("SELECT * FROM assets WHERE id=?", (identifier,)).fetchone()
    db.close()
    if not a or (kind and a["kind"] != kind):
        raise ValueError("Archivo no encontrado")
    p = Path(a["path"]).resolve()
    if not p.is_relative_to(data):
        raise ValueError("Archivo fuera de almacenamiento")
    return p


def register_asset(data, db, p):
    ident = p["id"]
    kind = p["kind"]
    if kind not in ("audio", "cover") or not re.fullmatch(r"[a-f0-9]{32}", ident):
        raise ValueError("Archivo inválido")
    path = data / "uploads" / ident
    if not path.is_file():
        raise ValueError("Archivo faltante")
    probe = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_format",
            "-show_streams",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        text=True,
        timeout=20,
    )
    if probe.returncode:
        raise ValueError("No se pudo leer el audio o imagen")
    meta = json.loads(probe.stdout)
    streams = meta.get("streams", [])
    duration = float(meta.get("format", {}).get("duration", 0))
    if kind == "audio" and (
        not any(s.get("codec_type") == "audio" for s in streams)
        or not 0 < duration <= 7200
    ):
        raise ValueError("Se necesita audio de hasta 2 horas")
    if kind == "cover" and not any(
        s.get("codec_type") == "video"
        and 0 < s.get("width", 0) <= 8192
        and 0 < s.get("height", 0) <= 8192
        for s in streams
    ):
        raise ValueError("Portada inválida")
    db.execute(
        "INSERT INTO assets VALUES(?,?,?,?,?)",
        (ident, text(p["name"]), kind, str(path), duration),
    )
    return {"id": ident, "duration": duration}
