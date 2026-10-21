import re


def text(v, limit=500):
    if not isinstance(v, str) or not v.strip() or len(v) > limit:
        raise ValueError("Texto vacío o demasiado largo")
    return v.strip()


def url(v):
    if not isinstance(v, str) or not re.match(
        r"^https://(www\.)?(youtube\.com|youtu\.be|open\.spotify\.com)/", v
    ):
        raise ValueError("Destino debe ser YouTube o Spotify HTTPS")
    return v
