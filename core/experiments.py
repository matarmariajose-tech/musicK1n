import re
import sqlite3
import time
import uuid

from storage import event
from validation import text, url


def validate_cover(db, identifier):
    identifier = text(identifier)
    asset = db.execute(
        "SELECT id FROM assets WHERE id = ? AND kind = 'cover'", (identifier,)
    ).fetchone()
    if asset is None:
        raise ValueError("Seleccioná una portada cargada para este experimento")
    return identifier


def create_experiment(db, payload):
    track = db.execute(
        "SELECT * FROM tracks WHERE id = ?", (payload["track_id"],)
    ).fetchone()
    if track is None:
        raise ValueError("Canción no encontrada")
    start, end = float(payload["start"]), float(payload["end"])
    if not 0 <= start < end <= track["duration"] or not 5 <= end - start <= 60:
        raise ValueError("Corte debe durar 5–60 segundos dentro del audio")
    style = payload["style"]
    if style not in ("cover", "waveform"):
        raise ValueError("Formato inválido")
    cover_id = validate_cover(db, payload.get("cover_id")) if style == "cover" else None
    identifier = uuid.uuid4().hex
    try:
        db.execute(
            "INSERT INTO experiments "
            "(id, track_id, start, end, style, title, caption, destination, created, cover_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                identifier,
                track["id"],
                start,
                end,
                style,
                text(payload.get("title", track["title"]), 100),
                payload.get("caption", "")[:5000],
                url(payload["destination"]),
                time.time(),
                cover_id,
            ),
        )
    except sqlite3.IntegrityError:
        existing = db.execute(
            "SELECT id, cover_id FROM experiments "
            "WHERE track_id = ? AND start = ? AND end = ? AND style = ?",
            (track["id"], start, end, style),
        ).fetchone()
        if existing is None:
            raise
        if existing["cover_id"] != cover_id:
            raise ValueError(
                "Ya existe este corte y formato con otra portada"
            ) from None
        return {"id": existing["id"], "existing": True}
    event(db, "experiment.created", {"id": identifier})
    return {"id": identifier}


def queue_render(db, payload):
    experiment = db.execute(
        "SELECT * FROM experiments WHERE id = ?", (payload["id"],)
    ).fetchone()
    if experiment is None:
        raise ValueError("Experimento no encontrado")
    if experiment["status"] not in ("draft", "rendered"):
        raise ValueError("No se puede renderizar en este estado")
    if experiment["style"] == "cover" and not experiment["cover_id"]:
        cover_id = validate_cover(db, payload.get("cover_id"))
        db.execute(
            "UPDATE experiments SET cover_id = ? WHERE id = ?",
            (cover_id, experiment["id"]),
        )
        event(
            db,
            "experiment.cover.selected",
            {"id": experiment["id"], "cover_id": cover_id},
        )
    identifier = uuid.uuid4().hex
    try:
        db.execute(
            "INSERT INTO jobs (id, experiment_id, kind, status, created) "
            "VALUES (?, ?, 'render', 'queued', ?)",
            (identifier, experiment["id"], time.time()),
        )
    except sqlite3.IntegrityError:
        return {"queued": False, "reason": "Ya está en cola"}
    event(db, "render.queued", {"id": experiment["id"]})
    return {"job_id": identifier}


def record_publication(db, payload):
    experiment = db.execute(
        "SELECT * FROM experiments WHERE id = ?", (payload["id"],)
    ).fetchone()
    if experiment is None or experiment["status"] not in (
        "approved",
        "uploaded-private",
        "published",
    ):
        raise ValueError("Primero aprobá el clip")
    video_id = text(payload["video_id"], 20)
    if not re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id):
        raise ValueError("Id YouTube inválido")
    if experiment["video_id"] and experiment["video_id"] != video_id:
        raise ValueError("El video no coincide con el ya vinculado al experimento")
    if experiment["status"] == "published":
        return {"saved": True, "existing": True}
    if db.execute(
        "SELECT 1 FROM jobs WHERE experiment_id = ? AND status IN ('queued', 'running')",
        (experiment["id"],),
    ).fetchone():
        raise ValueError(
            "Esperá a que termine el trabajo antes de registrar la publicación"
        )
    updated = db.execute(
        "UPDATE experiments SET status = 'published', video_id = ? "
        "WHERE id = ? AND status = ? AND video_id IS ?",
        (video_id, experiment["id"], experiment["status"], experiment["video_id"]),
    )
    if updated.rowcount != 1:
        raise ValueError("El experimento cambió; actualizá el panel antes de continuar")
    event(
        db,
        "experiment.published.manual",
        {"id": experiment["id"], "video_id": video_id},
    )
    return {"saved": True}
