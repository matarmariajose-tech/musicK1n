import subprocess

from assets import asset_path
from storage import event


def render(db, job, data):
    e = db.execute(
        "SELECT * FROM experiments WHERE id=?", (job["experiment_id"],)
    ).fetchone()
    t = db.execute("SELECT * FROM tracks WHERE id=?", (e["track_id"],)).fetchone()
    audio = asset_path(data, t["audio"], "audio")
    clips = data / "clips"
    clips.mkdir(exist_ok=True)
    out = clips / (e["id"] + ".mp4")
    tmp = clips / (e["id"] + ".tmp.mp4")
    duration = e["end"] - e["start"]
    if e["style"] == "cover":
        if not e["cover_id"]:
            raise ValueError(
                "Seleccioná una portada para este experimento antes de renderizar"
            )
        args = [
            "-loop",
            "1",
            "-i",
            str(asset_path(data, e["cover_id"], "cover")),
            "-ss",
            str(e["start"]),
            "-i",
            str(audio),
            "-vf",
            "scale=720:1280:force_original_aspect_ratio=decrease,pad=720:1280:(ow-iw)/2:(oh-ih)/2:color=0x101017,setsar=1",
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
        ]
    else:
        args = [
            "-ss",
            str(e["start"]),
            "-i",
            str(audio),
            "-filter_complex",
            "[0:a]asplit[a][w];[w]showwaves=s=720x1280:mode=line:colors=0xa78bfa:rate=30,format=yuv420p[v]",
            "-map",
            "[v]",
            "-map",
            "[a]",
        ]
    cmd = [
        "ffmpeg",
        "-nostdin",
        "-v",
        "error",
        "-y",
        *args,
        "-t",
        str(duration),
        "-r",
        "30",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-threads",
        "2",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        str(tmp),
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if r.returncode:
            raise ValueError("FFmpeg no pudo generar el clip")
        tmp.replace(out)
        with db:
            db.execute(
                'UPDATE experiments SET status="rendered",clip=? WHERE id=?',
                (str(out), e["id"]),
            )
            event(db, "render.completed", {"id": e["id"]})
    finally:
        tmp.unlink(missing_ok=True)
