"""Sample the installed GUI/broker for the specified duration. Never read conversation contents."""

import argparse
import json
import os
import subprocess
import time
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("duration", type=int, nargs="?", default=3600)
parser.add_argument(
    "--output",
    type=Path,
    default=Path(__file__).resolve().parents[1] / "docs/soak.json",
)
args = parser.parse_args()
binary = str(Path.home() / "Applications/Codex Pet Plus.app/Contents/MacOS/Companion")
status = (
    Path.home() / "Library/Application Support/CodexPetPlus/profiles/main/status.json"
)
started = time.monotonic()
records = []
identity = None
while True:
    rows = [
        row.strip().split(None, 4)
        for row in subprocess.check_output(
            ["ps", "-axo", "pid=,ppid=,rss=,%cpu=,comm="], text=True
        ).splitlines()
    ]
    guis = [r for r in rows if len(r) == 5 and r[4] == binary]
    group = (
        []
        if not guis
        else [guis[0]] + [r for r in rows if r[1] == guis[0][0] and "ython" in r[4]]
    )
    if identity is None:
        if len(group) < 2 and time.monotonic() - started < 15:
            time.sleep(0.2)
            continue
        identity = [r[0] for r in group]
        started = time.monotonic()
    elapsed = round(time.monotonic() - started, 2)
    alive = len(group) == 2 and [r[0] for r in group] == identity
    try:
        state = json.loads(status.read_text())["state"]
    except (OSError, ValueError, KeyError):
        state = "unknown"
    records.append(
        dict(
            t=elapsed,
            rssMiB=round(sum(int(r[2]) for r in group) / 1024, 2),
            cpu=round(sum(float(r[3]) for r in group), 2),
            state=state,
            healthy=alive,
        )
    )
    report = dict(
        elapsed=elapsed,
        target=args.duration,
        complete=alive and elapsed >= args.duration,
        interrupted=not alive,
        samples=records,
    )
    tmp = args.output.with_suffix(".tmp")
    tmp.write_text(json.dumps(report, indent=2))
    os.replace(tmp, args.output)
    if not alive or elapsed >= args.duration:
        break
    time.sleep(min(30, args.duration - elapsed))
