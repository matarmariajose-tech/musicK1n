import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "core"))

import engine
from storage import connect


class Experiments(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.data = Path(self.directory.name)
        self.location = patch.object(engine, "DATA", self.data)
        self.location.start()
        self.db = engine.database()
        uploads = self.data / "uploads"
        uploads.mkdir()
        self.cover = "b" * 32
        self.other_cover = "c" * 32
        self.audio = "a" * 32
        with self.db:
            for identifier, kind in ((self.audio, "audio"), (self.cover, "cover")):
                self.db.execute(
                    "INSERT INTO assets VALUES (?, ?, ?, ?, ?)",
                    (identifier, identifier, kind, str(uploads / identifier), 8),
                )
            self.db.execute(
                "INSERT INTO tracks (id, title, audio, duration) VALUES (?, ?, ?, ?)",
                ("track", "Test", self.audio, 8),
            )

    def tearDown(self):
        self.db.close()
        self.location.stop()
        self.directory.cleanup()

    def create(self, style="waveform", **changes):
        payload = {
            "track_id": "track",
            "start": 0,
            "end": 6,
            "style": style,
            "title": "Test",
            "destination": "https://youtu.be/abcdefghijk",
        }
        payload.update(changes)
        with self.db:
            return engine.dispatch(self.db, "experiment", payload)["id"]

    def test_cover_requires_explicit_valid_selection(self):
        for cover in (None, "missing", self.audio):
            with self.subTest(cover=cover), self.assertRaises(ValueError):
                self.create("cover", cover_id=cover)
        self.assertEqual(
            self.db.execute("SELECT COUNT(*) FROM experiments").fetchone()[0], 0
        )

    def test_cover_deduplication_does_not_silently_replace_selection(self):
        identifier = self.create("cover", cover_id=self.cover)
        self.assertEqual(identifier, self.create("cover", cover_id=self.cover))
        with self.db:
            self.db.execute(
                "INSERT INTO assets VALUES (?, ?, ?, ?, ?)",
                (
                    self.other_cover,
                    "Other",
                    "cover",
                    str(self.data / self.other_cover),
                    0,
                ),
            )
        with self.assertRaisesRegex(ValueError, "otra portada"):
            self.create("cover", cover_id=self.other_cover)
        self.assertEqual(
            self.db.execute(
                "SELECT cover_id FROM experiments WHERE id = ?", (identifier,)
            ).fetchone()[0],
            self.cover,
        )

    def test_render_uses_selected_cover_after_another_upload(self):
        uploads = self.data / "uploads"
        subprocess.run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-f",
                "lavfi",
                "-i",
                "sine=frequency=440:duration=8",
                "-f",
                "wav",
                str(uploads / self.audio),
            ],
            check=True,
        )
        (uploads / self.cover).write_bytes(
            b"P6\n16 16\n255\n" + bytes([255, 0, 0]) * 256
        )
        identifier = self.create("cover", cover_id=self.cover)
        (uploads / self.other_cover).write_bytes(
            b"P6\n16 16\n255\n" + bytes([0, 0, 255]) * 256
        )
        with self.db:
            engine.dispatch(
                self.db,
                "asset",
                {
                    "id": self.other_cover,
                    "name": "Later blue cover",
                    "kind": "cover",
                },
            )
            engine.dispatch(self.db, "render", {"id": identifier})
        self.assertTrue(engine.worker_once())
        experiment = self.db.execute(
            "SELECT * FROM experiments WHERE id = ?", (identifier,)
        ).fetchone()
        self.assertEqual(experiment["status"], "rendered")
        pixel = subprocess.check_output(
            [
                "ffmpeg",
                "-v",
                "error",
                "-i",
                experiment["clip"],
                "-frames:v",
                "1",
                "-vf",
                "crop=2:2:360:640,scale=1:1",
                "-f",
                "rawvideo",
                "-pix_fmt",
                "rgb24",
                "pipe:1",
            ]
        )
        self.assertGreater(pixel[0], 200)
        self.assertLess(pixel[2], 40)

    def test_private_upload_can_be_marked_published_once_with_same_video(self):
        identifier = self.create()
        with self.db:
            self.db.execute(
                "UPDATE experiments SET status = 'uploaded-private', video_id = ? WHERE id = ?",
                ("abcdefghijk", identifier),
            )
        with self.assertRaisesRegex(ValueError, "no coincide"):
            with self.db:
                engine.dispatch(
                    self.db, "published", {"id": identifier, "video_id": "12345678901"}
                )
        with self.db:
            result = engine.dispatch(
                self.db, "published", {"id": identifier, "video_id": "abcdefghijk"}
            )
            replay = engine.dispatch(
                self.db, "published", {"id": identifier, "video_id": "abcdefghijk"}
            )
        self.assertTrue(result["saved"])
        self.assertTrue(replay["existing"])
        self.assertEqual(
            self.db.execute(
                "SELECT status FROM experiments WHERE id = ?", (identifier,)
            ).fetchone()[0],
            "published",
        )
        self.assertEqual(
            self.db.execute(
                "SELECT COUNT(*) FROM audit WHERE event = 'experiment.published.manual'"
            ).fetchone()[0],
            1,
        )

    def test_publication_cannot_race_an_active_upload(self):
        identifier = self.create()
        with self.db:
            self.db.execute(
                "UPDATE experiments SET status = 'approved' WHERE id = ?", (identifier,)
            )
            self.db.execute(
                "INSERT INTO jobs (id, experiment_id, kind, status) VALUES ('upload', ?, 'upload', 'running')",
                (identifier,),
            )
        with self.assertRaisesRegex(ValueError, "termine el trabajo"):
            with self.db:
                engine.dispatch(
                    self.db, "published", {"id": identifier, "video_id": "abcdefghijk"}
                )
        self.assertEqual(
            self.db.execute(
                "SELECT status FROM experiments WHERE id = ?", (identifier,)
            ).fetchone()[0],
            "approved",
        )

    def test_legacy_database_migrates_without_choosing_a_cover(self):
        identifier = self.create("cover", cover_id=self.cover)
        self.db.close()
        legacy = sqlite3.connect(self.data / "k1n.sqlite")
        with legacy:
            legacy.execute("ALTER TABLE experiments DROP COLUMN cover_id")
        legacy.close()
        self.db = connect(self.data)
        reopened = connect(self.data)
        reopened.close()
        self.assertIsNone(
            self.db.execute(
                "SELECT cover_id FROM experiments WHERE id = ?", (identifier,)
            ).fetchone()[0]
        )
        with self.assertRaises(ValueError):
            with self.db:
                engine.dispatch(self.db, "render", {"id": identifier})
        with self.db:
            engine.dispatch(
                self.db, "render", {"id": identifier, "cover_id": self.cover}
            )
        self.assertEqual(
            self.db.execute(
                "SELECT cover_id FROM experiments WHERE id = ?", (identifier,)
            ).fetchone()[0],
            self.cover,
        )
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM jobs").fetchone()[0], 1)
