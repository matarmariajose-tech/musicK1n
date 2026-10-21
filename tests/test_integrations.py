import concurrent.futures, json, os, sys, tempfile, threading, time, unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "core"))
import engine, integrations, oauth


class Integrations(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        engine.DATA = Path(self.temp.name)
        self.db = engine.database()
        self.env = patch.dict(
            os.environ,
            {
                "GOOGLE_CLIENT_ID": "test-client",
                "GOOGLE_CLIENT_SECRET": "test-secret",
                "TOKEN_ENCRYPTION_KEY": "test-encryption-key-32-characters-long",
                "PUBLIC_URL": "https://test.example",
                "YOUTUBE_CHANNEL_ID": "UCtest",
            },
        )
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.db.close()
        self.temp.cleanup()

    def test_oauth_state_and_encrypted_refresh(self):
        from urllib.parse import urlparse, parse_qs

        with self.db:
            r = oauth.start(self.db)
        state = parse_qs(urlparse(r["url"]).query)["state"][0]
        with self.assertRaises(ValueError):
            oauth.finish(self.db, {"state": "wrong", "code": "test"})
        replies = [
            {"access_token": "access", "refresh_token": "refresh-secret"},
            {"items": [{"id": "UCtest"}]},
        ]
        with patch.object(oauth, "http", side_effect=replies):
            result = oauth.finish(self.db, {"state": state, "code": "test"})
        self.assertTrue(result["connected"])
        stored = self.db.execute(
            'SELECT value FROM settings WHERE key="google_refresh"'
        ).fetchone()[0]
        self.assertNotIn("refresh-secret", stored)
        self.assertEqual(oauth.stored_refresh(), "refresh-secret")
        with self.assertRaises(ValueError):
            oauth.finish(self.db, {"state": state, "code": "test"})

    def test_expired_state_does_not_exchange_tokens(self):
        with self.db:
            result = oauth.start(self.db)
        from urllib.parse import urlparse, parse_qs

        state = parse_qs(urlparse(result["url"]).query)["state"][0]
        with (
            patch.object(oauth.time, "time", return_value=time.time() + 601),
            patch.object(oauth, "http") as request,
        ):
            with self.assertRaises(ValueError):
                oauth.finish(self.db, {"state": state, "code": "test"})
        request.assert_not_called()

    def test_simultaneous_callbacks_exchange_tokens_only_once(self):
        from urllib.parse import urlparse, parse_qs

        with self.db:
            result = oauth.start(self.db)
        state = parse_qs(urlparse(result["url"]).query)["state"][0]
        barrier = threading.Barrier(2)
        compare = oauth.secrets.compare_digest

        def synchronized_compare(left, right):
            valid = compare(left, right)
            barrier.wait(timeout=5)
            return valid

        def finish():
            db = engine.database()
            try:
                return oauth.finish(db, {"state": state, "code": "test"})
            except ValueError:
                return {"connected": False}
            finally:
                db.close()

        replies = [
            {"access_token": "access", "refresh_token": "refresh-secret"},
            {"items": [{"id": "UCtest"}]},
        ]
        with (
            patch.object(
                oauth.secrets, "compare_digest", side_effect=synchronized_compare
            ),
            patch.object(oauth, "http", side_effect=replies) as request,
        ):
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(lambda _: finish(), range(2)))
        self.assertEqual(sum(r["connected"] for r in results), 1)
        self.assertEqual(request.call_count, 2)
        self.assertIsNone(
            self.db.execute(
                'SELECT 1 FROM settings WHERE key="google_oauth_state"'
            ).fetchone()
        )

    def test_failed_exchange_cannot_reuse_consumed_state(self):
        from urllib.parse import urlparse, parse_qs

        with self.db:
            result = oauth.start(self.db)
        state = parse_qs(urlparse(result["url"]).query)["state"][0]
        with patch.object(
            oauth, "http", side_effect=ValueError("API unavailable")
        ) as request:
            with self.assertRaises(ValueError):
                oauth.finish(self.db, {"state": state, "code": "test"})
            with self.assertRaises(ValueError):
                oauth.finish(self.db, {"state": state, "code": "test"})
        self.assertEqual(request.call_count, 1)

    def test_wrong_youtube_channel_does_not_import(self):
        with (
            patch.object(integrations, "google_token", return_value="test"),
            patch.object(
                integrations, "http", return_value={"items": [{"id": "UCwrong"}]}
            ),
        ):
            with self.assertRaises(ValueError):
                integrations.sync_youtube(
                    self.db, {"start": "2026-10-01", "end": "2026-10-08"}
                )
        self.assertEqual(
            self.db.execute("SELECT COUNT(*) FROM metrics").fetchone()[0], 0
        )

    def test_upload_recovers_existing_session_without_new_insert(self):
        ident = "a" * 32
        clips = engine.DATA / "clips"
        clips.mkdir()
        (clips / (ident + ".mp4")).write_bytes(b"test-file")
        with self.db:
            self.db.execute(
                "INSERT INTO tracks(id,title) VALUES(?,?)", ("track", "Test")
            )
            self.db.execute(
                "INSERT INTO experiments(id,track_id,status,title,caption,destination) VALUES(?,?,?,?,?,?)",
                (
                    ident,
                    "track",
                    "approved",
                    "Test",
                    "",
                    "https://www.youtube.com/watch?v=my4E2FRFuH8",
                ),
            )
            self.db.execute(
                "INSERT INTO settings VALUES(?,?)",
                (
                    "upload:" + ident,
                    "https://www.googleapis.com/upload/youtube/v3/videos?upload_id=test",
                ),
            )
        e = self.db.execute("SELECT * FROM experiments WHERE id=?", (ident,)).fetchone()
        with (
            patch.object(integrations, "google_token", return_value="token"),
            patch.object(
                integrations,
                "http",
                side_effect=[
                    {"items": [{"id": "UCtest"}]},
                    (201, {}, json.dumps({"id": "abcdefghijk"}).encode()),
                ],
            ) as call,
        ):
            result = integrations.upload_private(self.db, e)
        self.assertEqual(result["privacy"], "private")
        self.assertEqual(call.call_count, 2)
        self.assertEqual(
            self.db.execute(
                "SELECT status FROM experiments WHERE id=?", (ident,)
            ).fetchone()[0],
            "uploaded-private",
        )


if __name__ == "__main__":
    unittest.main()
