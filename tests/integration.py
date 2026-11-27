"""Exercise installed hook -> datagram -> reducer -> UI pipe, local inference, restart and cancel."""

import sys
import os
import time
import json
import subprocess
import tempfile
import uuid
import threading
import queue
from pathlib import Path

P = Path(__file__).resolve().parents[1]
src = P / "src"
sys.path.insert(0, str(src))
from chat import generate
import socket

home = Path.home() / "Library/Application Support/CodexPetPlus"


def offline_chat():
    updates = []
    cancel = threading.Event()

    def gen(history, question):
        return generate(
            P / ".runtime",
            "qwen2.5-1.5b-instruct-q4_k_m.gguf",
            "你叫露米。回答只用中文。",
            history,
            question,
            cancel,
            updates.append,
        )

    first = gen([], "请记住我的猫叫雪团。你叫什么名字？")
    second = gen(
        [{"user": "请记住我的猫叫雪团。", "assistant": first["text"]}],
        "我的猫叫什么？只回答名字。",
    )
    assert "雪团" in second["text"], second
    assert "露米" in first["text"], first
    assert len(updates) > 2

    def interrupt():
        try:
            gen([], "给我讲一个长故事。")
        except (OSError, RuntimeError, ValueError):
            pass

    t = threading.Thread(target=interrupt)
    t.start()
    time.sleep(0.25)
    begin = time.monotonic()
    cancel.set()
    t.join(4)
    assert not t.is_alive()
    return {
        "first": first,
        "second": second,
        "stream_updates": len(updates),
        "cancel_ms": round((time.monotonic() - begin) * 1000),
    }


def wire():
    cfg = {"model": "unused", "persona": "测试", "chat": False, "whispers": False}
    with tempfile.TemporaryDirectory() as d:
        base = Path(d)
        events = queue.Queue()
        env = dict(os.environ, PET_PLUS_HOME=d, CODEX_HOME=str(base / "codex"))
        thread = str(uuid.uuid4())
        from datetime import datetime, timezone
        bucket = base/"codex/sessions"/datetime.now().strftime("%Y/%m/%d")
        bucket.mkdir(parents=True)
        stamp = datetime.now(timezone.utc).isoformat()
        (bucket/("rollout-"+thread+".jsonl")).write_text(json.dumps(dict(timestamp=stamp,type="session_meta",
              payload=dict(id=thread,source="cli",timestamp=stamp)))+"\n")
        p = subprocess.Popen(
            ["/usr/bin/python3", "-B", "-u", str(src / "broker.py")],
            env=env,
            text=True,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        threading.Thread(
            target=lambda: [events.put(json.loads(l)) for l in p.stdout], daemon=True
        ).start()
        turn = str(uuid.uuid4())

        def wait(state):
            end = time.monotonic() + 2
            while time.monotonic() < end:
                try:
                    m = events.get(timeout=0.2)
                except queue.Empty:
                    continue
                if m.get("type") == "status" and m.get("state") == state:
                    return
            raise AssertionError(state)

        wait("idle")
        # Launch actual native sender with fake HOME disabled by NSHomeDirectory;
        # use authenticated wire in isolated instance, benchmark installed binary separately.
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        results = {}

        def event(k, state):
            e = dict(
                v=1,
                thread=thread,
                turn=turn,
                kind=k,
                source="hook",
                tool="QA",
                call="x",
                token=(base / "token").read_text(),
            )
            b = time.monotonic()
            sock.sendto(json.dumps(e).encode(), str(base / "events.sock"))
            wait(state)
            results[k] = round((time.monotonic() - b) * 1000, 2)

        try:
            event("start", "thinking")
            event("tool", "working")
            event("approval", "waiting-for-approval")
            event("result", "thinking")
            event("review", "review")
            event("end", "success")
            b = time.monotonic()
            wait("idle")
            results["success_to_idle"] = round((time.monotonic() - b) * 1000)
            turn = str(uuid.uuid4())
            event("start", "thinking")
            event("abort", "idle")
            turn = str(uuid.uuid4())
            event("start", "thinking")
            event("error", "error")
            wait("idle")
        finally:
            p.stdin.close()
            p.wait(timeout=4)
        return results


if __name__ == "__main__":
    r = dict(wire_ms=wire(), chat=offline_chat())
    print(json.dumps(r, ensure_ascii=False, indent=2))
    output = P / ".build/v23/integration.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(r, ensure_ascii=False, indent=2)
    )
