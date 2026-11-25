"""Measure GUI+broker CPU time deltas during complete, observed idle intervals."""

import sys
import json
import os
from pathlib import Path
import subprocess
import time

root = Path(__file__).resolve().parents[1]
home = Path.home()
record = home / "Library/Application Support/CodexPetPlus/profiles/main/status.json"
exe = str(home / "Applications/Codex Pet Plus.app/Contents/MacOS/Companion")


def sample():
    rows = [
        s.strip().split(None, 3)
        for s in subprocess.check_output(
            ["ps", "-axo", "pid=,ppid=,time=,comm="], text=True
        ).splitlines()
    ]
    gui = next(r for r in rows if r[3] == exe)
    broker = next(r for r in rows if r[1] == gui[0] and "ython" in r[3])

    def seconds(raw):
        total = 0
        for val in raw.split(":"):
            total = 60 * total + float(val)
        return total

    state = json.loads(record.read_text())["state"]
    return (
        time.monotonic(),
        sum(seconds(r[2]) for r in (gui, broker)),
        record.stat().st_mtime_ns if state == "idle" else None,
    )


source=Path(sys.argv[1]) if len(sys.argv)>1 else root/"docs/certified-soak.json"
prefix = source.name.removesuffix("soak.json") if source.name.endswith("-soak.json") else ""
values = []
last = sample()
while True:
    run = json.loads(source.read_text())
    if run["complete"] or run["interrupted"]:
        break
    time.sleep(30)
    cur = sample()
    if cur[2] is not None and last[2] == cur[2]:
        values.append((cur[0] - last[0], cur[1] - last[1]))
        rates = [100 * c / t for t, c in values]
        d = dict(
            method="aggregate GUI + event broker CPU seconds / wall seconds, unchanged idle snapshot at both ends",
            observed_idle_seconds=round(sum(t for t, c in values), 2),
            weighted_mean_percent=round(
                100 * sum(c for t, c in values) / sum(t for t, c in values), 3
            ),
            p95_30s_percent=round(sorted(rates)[int((len(rates) - 1) * 0.95)], 3),
            max_30s_percent=round(max(rates), 3),
            intervals=len(values),
        )
        f = root / "docs" / (prefix+"idle-cpu.json")
        tmp = f.with_suffix(".tmp")
        tmp.write_text(json.dumps(d, indent=2))
        os.replace(tmp, f)
    last = cur
