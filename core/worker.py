import fcntl
import time

from rendering import render
from storage import connect


def worker_once(data):
    db = connect(data)
    db.execute("BEGIN IMMEDIATE")
    job = db.execute(
        'SELECT * FROM jobs WHERE status="queued" ORDER BY created LIMIT 1'
    ).fetchone()
    if not job:
        db.commit()
        db.close()
        return False
    db.execute(
        'UPDATE jobs SET status="running",started=? WHERE id=?',
        (time.time(), job["id"]),
    )
    db.commit()
    try:
        if job["kind"] == "render":
            render(db, job, data)
        elif job["kind"] == "upload":
            from integrations import upload_private

            upload_private(
                db,
                db.execute(
                    "SELECT * FROM experiments WHERE id=?", (job["experiment_id"],)
                ).fetchone(),
            )
        else:
            raise ValueError("Tipo de trabajo inválido")
        with db:
            db.execute(
                'UPDATE jobs SET status="done",finished=? WHERE id=?',
                (time.time(), job["id"]),
            )
    except Exception as exc:
        with db:
            db.execute(
                'UPDATE jobs SET status="failed",error=?,finished=? WHERE id=?',
                (str(exc)[:300], time.time(), job["id"]),
            )
    finally:
        db.close()
    return True


def run(data):
    data.mkdir(parents=True, exist_ok=True)
    with (data / "worker.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        db = connect(data)
        try:
            with db:
                db.execute(
                    'UPDATE jobs SET status="failed",error="Proceso interrumpido; revisar el trabajo antes de reintentarlo" WHERE status="running"'
                )
        finally:
            db.close()
        while True:
            if not worker_once(data):
                time.sleep(2)
