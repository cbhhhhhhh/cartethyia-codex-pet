"""Isolated production broker + real local model. Optional six-minute whisper run."""

import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import tempfile
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
DEFAULT = json.loads((ROOT / "examples/config.json").read_text())


class Broker:
    def __init__(self, base, profile="main"):
        self.events = queue.Queue()
        self.p = subprocess.Popen(
            ["/usr/bin/python3", "-u", "-B", str(ROOT / "src/broker.py"), profile],
            env=dict(
                os.environ, CODEX_HOME=str(base / "empty"), PET_PLUS_HOME=str(base)
            ),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
        )
        threading.Thread(
            target=lambda: [self.events.put(json.loads(l)) for l in self.p.stdout],
            daemon=True,
        ).start()

    def send(self, op, **values):
        self.p.stdin.write(json.dumps(dict(op=op, **values)) + "\n")
        self.p.stdin.flush()

    def until(self, kind, seconds=45):
        deadline = time.monotonic() + seconds
        seen = []
        while time.monotonic() < deadline:
            try:
                item = self.events.get(timeout=max(0, deadline - time.monotonic()))
            except queue.Empty:
                break
            seen.append(item)
            if item["type"] == kind:
                return item, seen
        raise AssertionError("No " + kind)

    def close(self):
        self.p.stdin.close()
        self.p.wait(timeout=6)
        self.p.stdout.close()


def chat(base):
    cfg = dict(DEFAULT, persona="你叫露米。用中文回答。", rounds=2)
    p = Broker(base)
    try:
        p.until("history")
        p.send("config", config=cfg)
        p.send("chat", text="我家猫叫雪团。你叫什么？")
        one, events = p.until("reply")
        assert "露米" in one["text"] and any(x["type"] == "partial" for x in events)
        p.send("chat", text="我家猫的名字是什么？只回答名字。")
        two, _ = p.until("reply")
        assert "雪团" in two["text"]
        p.send("chat", text="请写一个很长的故事。")
        p.until("partial")
        p.send("cancel")
        time.sleep(0.3)
    finally:
        p.close()
    other = Broker(base, "second")
    try:
        assert other.until("history")[0]["pairs"] == []
    finally:
        other.close()
    p = Broker(base)
    try:
        history = p.until("history")[0]["pairs"]
        assert len(history) == 2 and "雪团" in history[-1]["assistant"]
        p.send("clear")
        assert p.until("history")[0]["pairs"] == []
    finally:
        p.close()
    return dict(
        persona=True,
        stream=True,
        multi_turn=True,
        memory_after_restart=True,
        profile_isolation=True,
        cancel_during_stream=True,
        cancelled_turn_excluded=True,
        cleared_memory=True,
    )


def whispers(base):
    p = Broker(base)
    cfg = dict(DEFAULT, whispers=True, quietStart=0, quietEnd=0, minutes=5, muted=True)
    received = []
    try:
        p.until("history")
        p.send("config", config=cfg)
        begin = time.monotonic()

        def observe(seconds):
            deadline = time.monotonic() + seconds
            while time.monotonic() < deadline:
                try:
                    msg = p.events.get(timeout=max(0, deadline - time.monotonic()))
                except queue.Empty:
                    break
                if msg["type"] == "whisper":
                    received.append(msg)

        observe(302)
        assert not received
        p.send("config", config=dict(cfg, muted=False, focus=True))
        observe(5)
        assert not received
        p.send("config", config=dict(cfg, muted=False))
        msg, _ = p.until("whisper", 45)
        received.append(msg)
        assert msg["emotion"] and msg["action"] and msg["text"]
        observe(30)
        assert len(received) == 1
        return dict(
            seconds=round(time.monotonic() - begin, 1),
            muted_at_due=True,
            focus_at_due=True,
            delivered=1,
            immediate_repeat=False,
        )
    finally:
        p.close()


if __name__ == "__main__":
    with tempfile.TemporaryDirectory(dir="/tmp") as td:
        base = Path(td)
        (base / "runtime").symlink_to(ROOT / ".runtime", target_is_directory=True)
        if "--whisper" in sys.argv:
            name = "whisper"
            result = whispers(base)
        else:
            name = "conversation"
            result = chat(base)
        (ROOT / "docs" / f"{name}-qa.json").write_text(json.dumps(result, indent=2))
        print(result)
