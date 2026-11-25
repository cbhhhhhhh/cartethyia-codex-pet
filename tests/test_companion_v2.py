import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from local_api import LocalStage
import archive
import reminders


class ArchiveTests(unittest.TestCase):
    def test_zero_context_keeps_archive_and_ids(self):
        old = [
            {"user": "first", "assistant": "reply"},
            {"user": "second", "assistant": "ok"},
        ]
        archive_items = archive.normalize(old)
        self.assertEqual(archive.context(archive_items, 0), [])
        self.assertEqual(archive.context(archive_items, 1), archive_items[-1:])
        self.assertEqual(archive.normalize(archive_items), archive_items)
        self.assertEqual(len({i["id"] for i in archive_items}), 2)

    def test_images_deduplicated(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            img = p / "a.png"
            img.write_bytes(b"\x89PNG\r\n\x1a\nabc")
            self.assertEqual(archive.keep_image(p, img), archive.keep_image(p, img))
            self.assertEqual(len(list((p / "images").iterdir())), 1)

    def test_due_cadence_and_toggle(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            deferred = reminders.add(base, {"text": "无期限"})["id"]
            with patch("reminders.time.time", return_value=1800000000):
                from datetime import datetime, timezone

                due = datetime.fromtimestamp(1800002000, timezone.utc).isoformat()
                task = reminders.add(base, dict(text="检查结果", due=due))["id"]
                self.assertEqual(len(reminders.pending(base)), 1)
                self.assertEqual(reminders.pending(base), [])
            with patch("reminders.time.time", return_value=1800002001):
                self.assertIn("已到期", reminders.pending(base)[0]["text"])
            reminders.toggle(base, task)
            self.assertTrue(reminders.items(base)[-1]["done"])
            reminders.delete(base, deferred)
            self.assertEqual(len(reminders.items(base)), 1)


class StageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.commands = []
        self.stage = LocalStage(
            Path(self.tmp.name),
            self.commands.append,
            lambda: {"state": "idle", "pack": "cartethyia"},
        )

    def tearDown(self):
        self.stage.close()
        self.tmp.cleanup()

    def api(self, path, m=None, auth=True, extra=None):
        headers = {"Authorization": "Bearer " + self.stage.token} if auth else {}
        headers.update(extra or {})
        q = Request(
            self.stage.origin + path,
            data=json.dumps(m).encode() if m else None,
            headers=headers,
        )
        with urlopen(q, timeout=2) as r:
            return r.read()

    def test_loopback_assets_token_and_origins(self):
        self.assertIn(b"stage.js", self.api("/", auth=False))
        self.assertEqual(json.loads(self.api("/v1/state"))["state"], "idle")
        for args in [
            dict(auth=False),
            dict(extra={"Origin": "https://example.invalid"}),
            dict(extra={"Host": "example.invalid"}),
        ]:
            with self.assertRaises(HTTPError) as r:
                self.api("/v1/state", **args)
            self.assertEqual(r.exception.code, 403)
        self.assertEqual(self.stage.credentials.stat().st_mode & 0o777, 0o600)
        self.assertGreater(len(self.api("/v1/sprite")), 100)

    def test_lease_user_takeover_menus(self):
        c = lambda **m: json.loads(self.api("/v1/control", m))
        k = c(op="lock")["lock"]
        with self.assertRaises(HTTPError):
            c(op="throw", x=500, y=150)
        self.assertTrue(c(op="throw", lock=k, x=500, y=150)["ok"])
        self.stage.revoke()
        with self.assertRaises(HTTPError):
            c(op="say", lock=k, text="stale")
        c(op="menu-add", id="demo", label="演示")
        self.stage.click("demo")
        self.assertEqual(json.loads(self.api("/v1/state"))["events"][-1]["id"], "demo")
        c(op="menu-remove", id="demo")
        with self.assertRaises(HTTPError):
            c(op="open-shell")
