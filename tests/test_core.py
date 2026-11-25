import json
import unittest
import tempfile
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from state import Reducer, allow_whisper
from archive import context
from observe import Tail
from datetime import datetime, timezone
from chat import partial_text
from reminders import add, complete, pending

T = "10000000-0000-4000-8000-000000000001"
U = "10000000-0000-4000-8000-000000000002"


class Cases(unittest.TestCase):
    def setUp(self):
        self.r = Reducer()

    def ev(self, kind, t, **kw):
        self.r.event(dict(v=1, thread=T, turn=T, kind=kind, **kw), t)

    def test_deadline(self):
        self.ev("tool", 0, tool="build")
        self.assertEqual(self.r.snapshot(121)["state"], "idle")

    def test_end_race(self):
        self.ev("tool", 0, call="a")
        self.ev("end", 1)
        self.ev("result", 1.1, call="a")
        self.assertEqual(self.r.snapshot(1.2)["state"], "success")
        self.assertEqual(self.r.snapshot(1.6)["state"], "idle")

    def test_interrupt(self):
        self.ev("tool", 0)
        self.ev("abort", 0.01)
        self.assertEqual(self.r.snapshot(0.02)["state"], "idle")

    def test_concurrent(self):
        self.ev("tool", 0, call="a")
        self.ev("tool", 1, call="b")
        self.ev("result", 2, call="b")
        self.assertEqual(self.r.snapshot(2)["state"], "working")

    def test_approval(self):
        self.ev("approval", 0, tool="build", call="a")
        self.r.notice = None
        self.ev("tool", 0.2, call="a")
        self.ev("approval", 1, call="a")
        self.assertEqual(self.r.snapshot(1)["state"], "waiting-for-approval")
        self.assertIsNone(self.r.notice)
        self.ev("result", 2, call="a")
        self.assertEqual(self.r.snapshot(2)["state"], "thinking")

    def test_other_threads(self):
        self.ev("approval", 1)
        self.r.event(dict(v=1, thread=U, turn=U, kind="tool"), 2)
        self.ev("abort", 3)
        self.assertEqual(self.r.snapshot(3)["thread"], U)

    def test_failed(self):
        self.ev("error", 0)
        self.assertEqual(self.r.snapshot(0.1)["state"], "error")
        self.assertEqual(self.r.snapshot(0.8)["state"], "idle")

    def test_quiet(self):
        for h in [0, 4, 7, 22, 23]:
            self.assertFalse(allow_whisper(4000, 0, 45, h, 22, 8, True, False, False))
        self.assertTrue(allow_whisper(4000, 0, 45, 12, 22, 8, True, False, False))
        for a in [(60, False, False), (4000, True, False), (4000, False, True)]:
            self.assertFalse(allow_whisper(a[0], 0, 45, 12, 22, 8, True, *a[1:]))

    def test_memory(self):
        h = []
        for i in range(15):
            h = context(h + [{"user": str(i), "assistant": str(i)}], 10)
        self.assertEqual([p["user"] for p in h], list(map(str, range(5, 15))))

    def test_partial(self):
        self.assertEqual(partial_text('{"text":"你好'), "你好")
        self.assertEqual(partial_text('{"text":"你好","action":"'), "你好")

    def test_reminder(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)
            i = add(p, dict(text="test", due="2026-01-01T00:00:00+08:00"))["id"]
            self.assertEqual(len(pending(p)), 1)
            self.assertFalse(pending(p))
            complete(p, i)
            self.assertTrue(pending(p)[0]["completed"])

    def test_tail_partial_and_eof(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)
            d = p / datetime.now().strftime("%Y/%m/%d")
            d.mkdir(parents=True)
            f = d / ("rollout-" + T + ".jsonl")

            def line(kind):
                return json.dumps(
                    dict(
                        timestamp=datetime.now(timezone.utc).isoformat(),
                        type="event_msg",
                        payload=dict(type=kind, turn_id=T),
                    )
                ).encode()

            f.write_bytes(line("task_complete") + b"\n")
            tail = Tail(p)
            self.assertEqual(list(tail.poll()), [])
            with f.open("ab") as fp:
                fp.write(line("task_started"))
            self.assertEqual(list(tail.poll()), [])
            with f.open("ab") as fp:
                fp.write(b"\n")
            self.assertEqual([e["kind"] for e in tail.poll()], ["start"])

    def test_late_tool_cannot_revive_finished_approval(self):
        self.ev("approval", 0, call="a")
        self.ev("result", 1, call="a")
        self.ev("approval", 2, call="a")
        self.assertEqual(self.r.snapshot(2)["state"], "thinking")

    def test_concurrent_approval_survives_other_result(self):
        self.ev("tool", 0, call="a")
        self.ev("approval", 0.1, call="b")
        self.ev("result", 1, call="a")
        self.assertEqual(self.r.snapshot(1)["state"], "waiting-for-approval")

    def test_weather_stays_local_when_city_empty_and_caches(self):
        from weather import Weather
        from unittest.mock import patch

        w = Weather()
        answers = [
            {"results": [{"name": "测试城", "latitude": 1, "longitude": 2}]},
            {"current": {"temperature_2m": 18, "precipitation": 0}},
        ]
        with patch.object(w, "request", side_effect=answers) as remote:
            self.assertEqual(w.current(""), "")
            remote.assert_not_called()
            first = w.current("测试城")
            self.assertIn("18 °C", first)
            self.assertEqual(first, w.current("测试城"))
            self.assertEqual(remote.call_count, 2)

    def test_unsupported_event_or_version(self):
        for kind, version in [("unknown", 1), ("tool", 2)]:
            self.r.event(dict(v=version, thread=T, turn=T, kind=kind), 0)
        self.assertEqual(self.r.snapshot(1)["state"], "idle")

    def test_existing_turn_resumed_without_replaying_history(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            directory = base / datetime.now().strftime("%Y/%m/%d")
            directory.mkdir(parents=True)
            path = directory / ("rollout-" + T + ".jsonl")

            def row(group, p):
                return (
                    json.dumps(
                        dict(
                            timestamp=datetime.now(timezone.utc).isoformat(),
                            type=group,
                            payload=p,
                        )
                    )
                    + "\n"
                )

            path.write_text(row("turn_context", {"turn_id": U}))
            reader = Tail(base)
            self.assertEqual(list(reader.poll()), [])
            with path.open("a") as f:
                f.write(
                    row(
                        "response_item",
                        {"type": "function_call", "name": "demo", "call_id": "42"},
                    )
                )
            entries = list(reader.poll())
            self.assertEqual([(x["kind"], x["turn"]) for x in entries], [("tool", U)])

    def test_approval_without_call_id(self):
        self.ev("tool", 0, tool="Bash", call="42")
        self.ev("approval", 1, tool="Bash")
        self.assertEqual(self.r.snapshot(1)["state"], "waiting-for-approval")
        self.ev("result", 2, tool="Bash", call="42")
        self.assertEqual(self.r.snapshot(2)["state"], "thinking")
        self.ev("approval", 2.1, tool="Bash")
        self.assertEqual(self.r.snapshot(2.1)["state"], "thinking")

    def test_stop_can_continue_without_false_completion(self):
        self.ev("start", 1)
        self.ev("stop-attempt", 2)
        self.assertEqual(self.r.snapshot(2.1)["state"], "review")
        self.assertIsNone(self.r.notice)
        self.ev("tool", 2.2, tool="Bash", call="continuation")
        self.assertEqual(self.r.snapshot(2.5)["state"], "working")
        self.ev("end", 3)
        self.assertEqual(self.r.snapshot(3)["state"], "success")
        self.assertEqual(self.r.snapshot(4)["state"], "idle")

    def test_darwin_notifies_new_rollout_without_idle_tree_walk(self):
        import select
        from unittest.mock import patch

        if not hasattr(select, "kqueue"):
            self.skipTest("Darwin vnode monitor")
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            reader = Tail(root)
            try:
                self.assertIsNotNone(reader.watcher)
                with patch.object(
                    reader, "discover", side_effect=AssertionError("idle scan")
                ):
                    self.assertEqual(list(reader.poll()), [])
                    folder = root / datetime.now().strftime("%Y/%m/%d")
                    folder.mkdir(parents=True)
                    f = folder / ("rollout-" + T + ".jsonl")
                    f.write_text(
                        json.dumps(
                            {
                                "timestamp": datetime.now(timezone.utc).isoformat(),
                                "type": "event_msg",
                                "payload": {"type": "task_started", "turn_id": U},
                            }
                        )
                        + "\n"
                    )
                    self.assertEqual(
                        [(e["turn"], e["kind"]) for e in reader.poll()], [(U, "start")]
                    )
                    self.assertEqual(list(reader.poll()), [])
            finally:
                reader.close()
