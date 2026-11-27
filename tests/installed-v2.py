"""Exercise two real packaged macOS companions with isolated stores and the installed GGUF."""

import argparse
import http.client
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
from urllib.parse import urlsplit

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--binary", type=Path, default=Path.home() / "Applications/Codex Pet Plus.app/Contents/MacOS/Companion")
parser.add_argument("--output", type=Path, default=root / ".build/v23/two-pets.json")
args = parser.parse_args()
app = args.binary.resolve()
runtime = Path.home() / "Library/Application Support/CodexPetPlus/runtime"
out = {}


def wait(fn, seconds=7):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            value = fn()
            if value:
                return value
        except (FileNotFoundError, ConnectionError, KeyError):
            pass
        time.sleep(0.05)
    raise AssertionError("timed out at " + repr(fn))


def request(folder, data=None, path=None):
    secret = json.loads((folder / "api.json").read_text())
    dest = urlsplit(secret["origin"])
    assert dest.hostname == "127.0.0.1"
    c = http.client.HTTPConnection(dest.hostname, dest.port, timeout=3)
    try:
        c.request(
            "POST" if data else "GET",
            path or ("/v1/control" if data else "/v1/state"),
            json.dumps(data) if data else None,
            {
                "Authorization": "Bearer " + secret["token"],
                "Content-Type": "application/json",
            },
        )
        r = c.getresponse()
        assert r.status == 200, r.status
        return json.loads(r.read())
    finally:
        c.close()


with tempfile.TemporaryDirectory(dir="/tmp") as temp:
    base = Path(temp)
    (base / "runtime").symlink_to(runtime)
    (base / "appearance").symlink_to(runtime.parent / "appearance")
    processes = []
    try:
        for profile in ("main", "second"):
            f = base / "profiles" / profile
            f.mkdir(parents=True)
            cfg = json.loads((root / "examples/config.json").read_text())
            cfg.update(
                x=260 if profile == "main" else 465,
                y=265,
                notifications=False,
                randomActions=False,
            )
            (f / "config.json").write_text(json.dumps(cfg))
            processes.append(
                subprocess.Popen(
                    [str(app), "--profile", profile, "--api"],
                    env=dict(
                        os.environ, PET_PLUS_HOME=temp, CODEX_HOME=str(base / "empty")
                    ),
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            )
            wait(lambda: request(f).get("state") == "idle")
        first = base / "profiles/main"
        second = base / "profiles/second"

        def xy(f):
            return [int(i) for i in request(f)["pose"].split(",")]

        a = wait(lambda: xy(first))
        b = wait(lambda: xy(second))
        time.sleep(2.2)
        request(first, dict(op="throw", x=1100, y=130))
        hit = wait(lambda: (xy(second) if xy(second)[0] > b[0] + 8 else None))
        out["separate_app_processes"] = processes[0].pid != processes[1].pid
        out["real_second_window_displacement_points"] = hit[0] - b[0]

        library = request(first, path="/v1/clips")
        assert len(library) == 109
        assert library["牵着线放风筝"]["frames"] == 24
        request(first, dict(op="play", action="clip:牵着线放风筝"))
        wait(lambda: request(first).get("action") == "clip:牵着线放风筝")
        out["selectable_baked_clips"] = len(library)
        lock = request(first, dict(op="lock"))["lock"]
        playback = request(
            first,
            dict(
                op="sequence",
                lock=lock,
                steps=[
                    dict(action="骑士礼", seconds=0.35),
                    dict(action="祈愿水环", seconds=0.35),
                ],
            ),
        )["id"]
        wait(
            lambda: request(first, path="/v1/playback/" + playback)["status"]
            == "completed"
        )
        request(first, dict(op="release", lock=lock))
        out["leased_two_step_sequence"] = True
        request(first, dict(op="say", text="窗口已就绪"))
        wait(lambda: request(first).get("bubble") == "窗口已就绪")
        out["authenticated_bubble"] = True
        request(first, dict(op="chat", text="请用一句话问好。"))
        pairs = wait(lambda: request(first, path="/v1/history"), 65)
        wait(lambda: request(first).get("bubble") == pairs[-1]["assistant"])
        out["production_gguf_to_visible_bubble"] = True
        out["response_characters"] = len(pairs[-1]["assistant"])
        assert not request(second, path="/v1/history")
        out["separate_histories"] = True
        assert all(p.poll() is None for p in processes)
    finally:
        for p in processes:
            if p.poll() is None:
                p.terminate()
        for p in processes:
            p.wait(timeout=6)
args.output.parent.mkdir(parents=True, exist_ok=True)
args.output.write_text(json.dumps(out, indent=2) + "\n")
print(out)
