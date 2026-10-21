import json
import sqlite3
import time


def connect(data):
    data.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(data / "k1n.sqlite", timeout=20)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA foreign_keys=ON")
    db.executescript("""
 CREATE TABLE IF NOT EXISTS tracks(id TEXT PRIMARY KEY,title TEXT NOT NULL,audio TEXT,duration REAL,spotify_url TEXT,lyrics TEXT DEFAULT '',story TEXT DEFAULT '',created REAL);
 CREATE TABLE IF NOT EXISTS assets(id TEXT PRIMARY KEY,name TEXT,kind TEXT,path TEXT UNIQUE,duration REAL);
 CREATE TABLE IF NOT EXISTS experiments(id TEXT PRIMARY KEY,track_id TEXT REFERENCES tracks(id),start REAL,end REAL,style TEXT,title TEXT,caption TEXT,destination TEXT,status TEXT DEFAULT 'draft',clip TEXT,video_id TEXT,created REAL,UNIQUE(track_id,start,end,style));
 CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,experiment_id TEXT REFERENCES experiments(id),kind TEXT,status TEXT,error TEXT,created REAL,started REAL,finished REAL);
 CREATE UNIQUE INDEX IF NOT EXISTS active_job ON jobs(experiment_id,kind) WHERE status IN ('queued','running');
 CREATE TABLE IF NOT EXISTS metrics(experiment_id TEXT REFERENCES experiments(id),platform TEXT,window_start TEXT,window_end TEXT,views INTEGER,watch_seconds REAL,subscribers INTEGER,source TEXT,updated REAL,PRIMARY KEY(experiment_id,platform,window_start,window_end));
 CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY,event TEXT,detail TEXT,created REAL);
 CREATE TABLE IF NOT EXISTS contacts(id TEXT PRIMARY KEY,name TEXT,url TEXT,email TEXT,reason TEXT,draft TEXT,status TEXT DEFAULT 'draft',UNIQUE(email));
 CREATE TABLE IF NOT EXISTS clicks(day TEXT,platform TEXT,count INTEGER,PRIMARY KEY(day,platform));
 CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT);
 """)
    with db:
        db.execute("BEGIN IMMEDIATE")
        columns = {row["name"] for row in db.execute("PRAGMA table_info(experiments)")}
        if "cover_id" not in columns:
            db.execute(
                "ALTER TABLE experiments ADD COLUMN cover_id TEXT REFERENCES assets(id)"
            )
    return db


def event(db, name, detail):
    db.execute(
        "INSERT INTO audit(event,detail,created) VALUES(?,?,?)",
        (name, json.dumps(detail, ensure_ascii=False), time.time()),
    )


def rows(db, q, args=()):
    return [dict(r) for r in db.execute(q, args)]
