"""Exercise asynchronous start/end billing in the real broker with a local account fixture."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import uuid


@unittest.skipIf(os.name == "nt", "The macOS broker uses Unix datagrams; windows/qa_ownership.py covers the Windows client.")
class TurnBilling(unittest.TestCase):
    def test_official_deltas_and_a_turn_without_a_baseline(self):
        source = Path(__file__).resolve().parents[1] / "src"
        with tempfile.TemporaryDirectory(dir="/tmp") as temp:
            base = Path(temp)
            codex = base / "codex"
            day = codex / "sessions" / datetime.now().strftime("%Y/%m/%d")
            day.mkdir(parents=True)
            thread = str(uuid.uuid4())
            rollout = day / f"rollout-{thread}.jsonl"
            fixture = base / "official.json"

            def append(kind, **payload):
                stamp = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
                with rollout.open("a") as out:
                    out.write(json.dumps(dict(timestamp=stamp, type=kind, payload=payload)) + "\n")

            def account_snapshot(credits, dollars):
                usage = None if credits is None else dict(threadId=thread, estimatedUsageCreditsMicros=credits,
                                                         estimatedUsageUsdMicros=dollars, nativeUsageUsdMicros=0)
                pending = fixture.with_suffix(".tmp")
                pending.write_text(json.dumps(dict(threadUsage=usage)))
                pending.replace(fixture)

            append("session_meta", id=thread, timestamp=datetime.now(timezone.utc).isoformat(), source="cli")
            account_snapshot(900_000, 9_000)
            bridge = """
import os, json
from pathlib import Path
import broker
def account(method, **params):
    assert method == "account/usage/read" and params == {"threadId": os.environ["FIXTURE_THREAD"]}
    return json.loads(Path(os.environ["FIXTURE_PATH"]).read_text())
broker.account = account
broker.run()
"""
            env = dict(os.environ, PET_PLUS_HOME=str(base / "pet"), CODEX_HOME=str(codex),
                       PYTHONPATH=str(source), FIXTURE_PATH=str(fixture), FIXTURE_THREAD=thread)
            proc = subprocess.Popen([sys.executable, "-B", "-c", bridge], text=True, env=env,
                                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            events = queue.Queue()
            def read():
                for line in proc.stdout:
                    events.put(json.loads(line))
            reader = threading.Thread(target=read, daemon=True)
            reader.start()
            def send(op, **params):
                proc.stdin.write(json.dumps(dict(op=op, **params)) + "\n")
                proc.stdin.flush()
            def wait_for(kind, phrase=""):
                deadline = time.monotonic() + 8
                while time.monotonic() < deadline:
                    try:
                        event = events.get(timeout=.3)
                    except queue.Empty:
                        continue
                    if event.get("type") == kind and phrase in event.get("text", ""):
                        return event
                self.fail(f"Missing {kind} event containing {phrase!r}")

            try:
                wait_for("history")
                send("config", config=dict(trackCost=True, muted=True))
                send("usage", selected="", refresh=False)
                wait_for("usage")
                first = str(uuid.uuid4())
                append("event_msg", type="task_started", turn_id=first)
                wait_for("usage", "整条主会话累计 · 估算积分 0.9")
                account_snapshot(1_200_000, 11_000)
                append("event_msg", type="task_complete", turn_id=first)
                done = wait_for("usage", "本轮主会话估算增量 · 估算积分 0.3 / 原生美元用量 $0 / 估算美元 $0.002")
                self.assertEqual(done["selected"], f"{thread}/{first}")

                account_snapshot(None, None)
                second = str(uuid.uuid4())
                append("event_msg", type="task_started", turn_id=second)
                wait_for("turn-start")
                send("usage", selected=f"{thread}/{second}", refresh=False)
                wait_for("usage", "本轮积分与金额 · 暂不可拆分")
                append("event_msg", type="task_complete", turn_id=second)
                missing = wait_for("usage", "本次请求 · 已结束")
                self.assertIn("本轮积分与金额 · 暂不可拆分", missing["text"])
                self.assertNotIn("本轮主会话估算增量", missing["text"])
            finally:
                proc.stdin.close()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
                reader.join(1)
                proc.stdout.close()
                err = proc.stderr.read()
                proc.stderr.close()
                self.assertEqual(proc.returncode, 0, err)
