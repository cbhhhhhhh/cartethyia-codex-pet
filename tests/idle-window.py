"""Measure a visible companion with no Codex sessions or inference in its isolated profile."""

import json
import os
import subprocess
import tempfile
import time
from pathlib import Path

root = Path(__file__).resolve().parents[1]
actual = Path.home() / "Library/Application Support/CodexPetPlus"
binary = Path.home() / "Applications/Codex Pet Plus.app/Contents/MacOS/Companion"


def cpu(text):
    total = 0.0
    for part in text.split(":"):
        total = total * 60 + float(part)
    return total


def sample(pid):
    rows = [
        s.strip().split(None, 4)
        for s in subprocess.check_output(
            ["ps", "-axo", "pid=,ppid=,time=,rss=,comm="], text=True
        ).splitlines()
    ]
    gui = next(x for x in rows if int(x[0]) == pid)
    broker = next(x for x in rows if int(x[1]) == pid and "ython" in x[4])
    return (
        time.monotonic(),
        sum(cpu(r[2]) for r in (gui, broker)),
        sum(int(r[3]) for r in (gui, broker)) / 1024,
    )


with tempfile.TemporaryDirectory(dir="/tmp") as d:
    base = Path(d)
    op = base / "profiles/measure"
    op.mkdir(parents=True)
    (base / "appearance").symlink_to(actual / "appearance")
    cfg = json.loads((root / "examples/config.json").read_text())
    cfg.update(x=40, y=90, notifications=False)
    (op / "config.json").write_text(json.dumps(cfg))
    p = subprocess.Popen(
        [str(binary), "--profile", "measure"],
        env=dict(os.environ, PET_PLUS_HOME=d, CODEX_HOME=str(base / "no-sessions")),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        time.sleep(8)
        first = sample(p.pid)
        prev = first
        rates = []
        rss = []
        for _ in range(12):
            time.sleep(12)
            cur = sample(p.pid)
            assert json.loads((op / "status.json").read_text())["state"] == "idle"
            rates.append(100 * (cur[1] - prev[1]) / (cur[0] - prev[0]))
            rss.append(cur[2])
            prev = cur
        result = dict(
            seconds=round(cur[0] - first[0], 2),
            gui_and_broker_mean_cpu_percent=round(
                100 * (cur[1] - first[1]) / (cur[0] - first[0]), 3
            ),
            peak_12s_cpu_percent=round(max(rates), 3),
            RSS_max_MiB=round(max(rss), 2),
            automatic_character_animations=cfg["randomActions"],
            window_requested_visible=True,
        )
        (root / "docs/v2-isolated-idle.json").write_text(json.dumps(result, indent=2))
        print(result)
    finally:
        p.terminate()
        p.wait(timeout=8)
