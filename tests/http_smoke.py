"""Run against an isolated local server only; never against production."""

import base64, json, os, urllib.request, urllib.error, urllib.parse, subprocess, time

base = os.environ.get("K1N_TEST_URL", "http://127.0.0.1:3108")
if urllib.parse.urlsplit(base).hostname not in ("127.0.0.1", "localhost", "::1"):
    raise ValueError("La prueba solo admite un servidor local")
auth = "Basic " + base64.b64encode(b"test-operator:local-test-password").decode()


def req(path, data=None, headers=None):
    h = {"Authorization": auth}
    h.update(headers or {})
    r = urllib.request.urlopen(
        urllib.request.Request(base + path, data=data, headers=h), timeout=10
    )
    return r.status, r.read()


assert req("/eve/v1/health")[0] == 200
try:
    urllib.request.urlopen(base + "/")
except urllib.error.HTTPError as e:
    assert e.code == 401
else:
    raise AssertionError("unauthorized access")
assert b"Growth Studio" in req("/")[1]
for route in ("/api/overview", "/api/campaign"):
    try:
        urllib.request.urlopen(base + route)
    except urllib.error.HTTPError as error:
        assert error.code == 401
    else:
        raise AssertionError("API sin autenticación")
assert urllib.request.urlopen(base + "/listen").status == 200
assert b"B.R.I.S.T.O.L" in urllib.request.urlopen(base + "/listen").read()
reply = json.loads(
    req("/api/ask", b'{"message":"Que publico"}', {"Content-Type": "application/json"})[
        1
    ]
)
assert reply["mode"] == "rules" and "B.R.I.S.T.O.L" in reply["reply"]
assert len(json.loads(req("/api/campaign")[1])["posts"]) == 3
try:
    req(
        "/api/action",
        b'{"action":"report"}',
        {"Content-Type": "application/json", "Origin": "https://evil.example"},
    )
except urllib.error.HTTPError as e:
    assert e.code == 403
else:
    raise AssertionError("cross origin accepted")
audio = subprocess.check_output(
    [
        "ffmpeg",
        "-v",
        "error",
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=440:duration=7",
        "-f",
        "wav",
        "pipe:1",
    ]
)
asset = json.loads(
    req("/api/upload", audio, {"X-Asset-Kind": "audio", "X-File-Name": "test.wav"})[1]
)


def action(name, payload):
    return json.loads(
        req(
            "/api/action",
            json.dumps({"action": name, "payload": payload}).encode(),
            {"Content-Type": "application/json"},
        )[1]
    )


for body in (b"not-json", b'{"action":"unknown"}'):
    try:
        req("/api/action", body, {"Content-Type": "application/json"})
    except urllib.error.HTTPError as error:
        assert error.code == 400
    else:
        raise AssertionError("Entrada inválida aceptada")
t = action("track", {"title": "HTTP test", "audio": asset["id"]})
e = action(
    "experiment",
    {
        "track_id": t["id"],
        "start": 0,
        "end": 6,
        "style": "waveform",
        "title": "HTTP clip",
        "destination": "https://www.youtube.com/watch?v=my4E2FRFuH8",
    },
)
action("render", {"id": e["id"]})
for _ in range(30):
    overview = json.loads(req("/api/overview")[1])
    exp = next(x for x in overview["experiments"] if x["id"] == e["id"])
    if exp["status"] == "rendered":
        break
    time.sleep(0.3)
assert exp["status"] == "rendered", overview["jobs"]
assert req("/media/" + e["id"])[0] == 200
action("approve", {"id": e["id"]})
try:
    action("upload-private", {"id": e["id"], "confirm": "UPLOAD_PRIVATE"})
except urllib.error.HTTPError as x:
    assert x.code == 400
else:
    raise AssertionError("upload without credentials accepted")
action("published", {"id": e["id"], "video_id": "abcdefghijk"})
assert action("published", {"id": e["id"], "video_id": "abcdefghijk"})["existing"]
try:
    action("published", {"id": e["id"], "video_id": "12345678901"})
except urllib.error.HTTPError as error:
    assert error.code == 400
else:
    raise AssertionError("Se reemplazó el video publicado")
print(
    "PASS: health, auth, dashboard, CSRF, upload, experiment, background render, video, approval, credential gate"
)
