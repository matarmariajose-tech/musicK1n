"""Persistent K1N workflow. CLI RPC uses JSON stdin; no shell interpolation."""

import csv
import io
import json
import os
import re
import sqlite3
import sys
import time
import uuid
from pathlib import Path

from assets import asset_path as resolve_asset
from assets import register_asset as inspect_asset
from experiments import create_experiment, queue_render, record_publication
from storage import connect, event, rows
from validation import text, url
from worker import run as run_worker
from worker import worker_once as process_job

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("K1N_DATA_DIR", str(ROOT / "data"))).resolve()


def database():
    return connect(DATA)


def asset_path(identifier, kind=None):
    return resolve_asset(DATA, identifier, kind)


def register_asset(db, payload):
    return inspect_asset(DATA, db, payload)


def worker_once():
    return process_job(DATA)


def dispatch(db, action, p):
    if action == "click":
        platform = p.get("platform")
        if platform not in ("youtube", "spotify"):
            raise ValueError("Destino inválido")
        from datetime import datetime, timezone

        day = datetime.now(timezone.utc).date().isoformat()
        db.execute(
            "INSERT INTO clicks VALUES(?,?,1) ON CONFLICT(day,platform) DO UPDATE SET count=count+1",
            (day, platform),
        )
        return {"saved": True}
    if action == "campaign":
        return json.loads((ROOT / "campaign.json").read_text())
    if action == "overview":
        return {
            "tracks": rows(db, "SELECT * FROM tracks ORDER BY created DESC"),
            "assets": rows(db, "SELECT id,name,kind,duration FROM assets"),
            "experiments": rows(
                db,
                "SELECT e.*,t.title AS track_title FROM experiments e JOIN tracks t ON t.id=e.track_id ORDER BY e.created DESC",
            ),
            "jobs": rows(db, "SELECT * FROM jobs ORDER BY created DESC LIMIT 50"),
            "metrics": rows(db, "SELECT * FROM metrics"),
            "contacts": rows(db, "SELECT * FROM contacts"),
            "clicks": rows(db, "SELECT * FROM clicks ORDER BY day DESC"),
            "ephemeral": os.environ.get("K1N_EPHEMERAL") == "1",
            "catalog": json.loads((ROOT / "catalog.json").read_text()),
            "connections": {
                "google": bool(
                    os.environ.get("GOOGLE_REFRESH_TOKEN")
                    or db.execute(
                        'SELECT 1 FROM settings WHERE key="google_refresh"'
                    ).fetchone()
                ),
                "spotify": bool(
                    os.environ.get("SPOTIFY_CLIENT_ID")
                    and os.environ.get("SPOTIFY_CLIENT_SECRET")
                ),
                "model": bool(os.environ.get("AI_GATEWAY_API_KEY")),
            },
        }
    if action == "oauth-start":
        from oauth import start

        return start(db)
    if action == "oauth-finish":
        from oauth import finish

        return finish(db, p)
    if action == "asset":
        return register_asset(db, p)
    if action == "track":
        aid = text(p["audio"])
        asset_path(aid, "audio")
        a = db.execute("SELECT duration FROM assets WHERE id=?", (aid,)).fetchone()
        ident = uuid.uuid4().hex
        destination = p.get("spotify_url", "")
        if destination:
            url(destination)
        db.execute(
            "INSERT INTO tracks VALUES(?,?,?,?,?,?,?,?)",
            (
                ident,
                text(p["title"]),
                aid,
                a["duration"],
                destination,
                p.get("lyrics", "")[:10000],
                p.get("story", "")[:10000],
                time.time(),
            ),
        )
        event(db, "track.created", {"id": ident})
        return {"id": ident}
    if action == "experiment":
        return create_experiment(db, p)
    if action == "render":
        return queue_render(db, p)
    if action == "upload-private":
        e = db.execute("SELECT * FROM experiments WHERE id=?", (p["id"],)).fetchone()
        if not e or e["status"] != "approved":
            raise ValueError("Se necesita aprobación previa")
        if p.get("confirm") != "UPLOAD_PRIVATE":
            raise ValueError("Confirmación de subida requerida")
        from integrations import required

        for key in ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "YOUTUBE_CHANNEL_ID"):
            required(key)
        ident = uuid.uuid4().hex
        try:
            db.execute(
                "INSERT INTO jobs(id,experiment_id,kind,status,created) VALUES(?,?,?,?,?)",
                (ident, e["id"], "upload", "queued", time.time()),
            )
        except sqlite3.IntegrityError:
            return {"queued": False, "reason": "Ya está en cola"}
        event(db, "youtube.upload.authorized", {"id": e["id"], "privacy": "private"})
        return {"job_id": ident}
    if action == "approve":
        e = db.execute("SELECT * FROM experiments WHERE id=?", (p["id"],)).fetchone()
        if not e or e["status"] != "rendered":
            raise ValueError("Primero renderizá y revisá el clip")
        if db.execute(
            'SELECT 1 FROM jobs WHERE experiment_id=? AND status IN ("queued","running")',
            (e["id"],),
        ).fetchone():
            raise ValueError("Esperá a que termine el render")
        db.execute('UPDATE experiments SET status="approved" WHERE id=?', (e["id"],))
        event(db, "experiment.approved", {"id": e["id"]})
        return {"approved": True}
    if action == "published":
        return record_publication(db, p)
    if action == "metrics":
        parsed = list(csv.DictReader(io.StringIO(p["csv"])))
        if len(parsed) > 10000:
            raise ValueError("Máximo 10000 filas")
        for r in parsed:
            if r["platform"] not in ("youtube", "spotify"):
                raise ValueError("Plataforma inválida")
            from datetime import date

            if date.fromisoformat(r["window_start"]) > date.fromisoformat(
                r["window_end"]
            ):
                raise ValueError("Fechas invertidas")
            v, w, s = (
                int(r["views"]),
                float(r["watch_seconds"]),
                int(r["subscribers"]),
            )
            if v < 0 or w < 0 or (not __import__("math").isfinite(w)):
                raise ValueError("Métricas inválidas")
            db.execute(
                "INSERT INTO metrics VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(experiment_id,platform,window_start,window_end) DO UPDATE SET views=excluded.views,watch_seconds=excluded.watch_seconds,subscribers=excluded.subscribers,source=excluded.source,updated=excluded.updated",
                (
                    r["experiment_id"],
                    r["platform"],
                    r["window_start"],
                    r["window_end"],
                    v,
                    w,
                    s,
                    "csv",
                    time.time(),
                ),
            )
        event(db, "metrics.imported", {"rows": len(parsed)})
        return {"imported": len(parsed)}
    if action == "report":
        data = rows(
            db,
            "SELECT m.*,e.track_id,e.style,e.start,e.end FROM metrics m JOIN experiments e ON e.id=m.experiment_id",
        )
        for r in data:
            r["avg_watch_seconds"] = (
                r["watch_seconds"] / r["views"] if r["views"] else None
            )
            r["evidence"] = (
                "muestra pequeña"
                if r["views"] < 100
                else "comparar solo misma plataforma y ventana"
            )
        return {
            "results": data,
            "note": "No atribuir escuchas Spotify a un clip sin evidencia. Comparar ventanas iguales. Ningún gasto automático.",
        }
    if action == "contact":
        source = text(p["url"], 1000)
        if not source.startswith("https://"):
            raise ValueError("Contacto requiere fuente pública HTTPS")
        email = text(p["email"])
        if not re.fullmatch("[^\\s@]+@[^\\s@]+\\.[^\\s@]+", email):
            raise ValueError("Correo inválido")
        ident = uuid.uuid4().hex
        db.execute(
            "INSERT INTO contacts(id,name,url,email,reason,draft) VALUES(?,?,?,?,?,?)",
            (
                ident,
                text(p["name"]),
                source,
                email.lower(),
                text(p["reason"], 2000),
                p.get("draft", "")[:5000],
            ),
        )
        return {"id": ident}
    if action in ("spotify-sync", "youtube-sync"):
        from integrations import sync_spotify, sync_youtube

        return sync_spotify(db) if action == "spotify-sync" else sync_youtube(db, p)
    raise ValueError("Acción desconocida")


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "worker":
        run_worker(DATA)
    else:
        db = database()
        try:
            req = json.load(sys.stdin)
            with db:
                result = dispatch(db, req["action"], req.get("payload", {}))
            print(json.dumps(result, ensure_ascii=False, allow_nan=False))
        except Exception as exc:
            print(json.dumps({"error": str(exc)[:300]}, ensure_ascii=False))
            sys.exit(1)
        finally:
            db.close()


if __name__ == "__main__":
    main()
