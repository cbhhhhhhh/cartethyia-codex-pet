"""Observe a real soak, exercise local Codex periodically, then run Apple's leaks tool."""

import json
import re
import statistics
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
source = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "docs/certified-soak.json"
prefix = source.name.removesuffix("soak.json") if source.name.endswith("-soak.json") else ""
checks = []


def write(path, data):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    tmp.replace(path)


def cli_probe():
    start = time.monotonic()
    try:
        p = subprocess.run(
            [
                "/usr/bin/python3",
                "-B",
                str(ROOT / "tests/local-codex.py"),
                "--isolated",
            ],
            capture_output=True,
            timeout=45,
        )
        return dict(
            ok=p.returncode == 0, wall_seconds=round(time.monotonic() - start, 3)
        )
    except subprocess.TimeoutExpired:
        return dict(ok=False, wall_seconds=45)


def leaks():
    exe = str(Path.home() / "Applications/Codex Pet Plus.app/Contents/MacOS/Companion")
    rows = [
        l.strip().split(None, 2)
        for l in subprocess.check_output(
            ["ps", "-axo", "pid=,ppid=,comm="], text=True
        ).splitlines()
    ]
    gui = next(r for r in rows if r[2] == exe)
    broker = next(r for r in rows if r[1] == gui[0] and "ython" in r[2])
    found = {}
    for name, record in [("gui", gui), ("broker", broker)]:
        proc = subprocess.run(
            ["/usr/bin/leaks", "-quiet", record[0]],
            capture_output=True,
            text=True,
            timeout=45,
        )
        m = re.search(
            r"(\d+) leaks? for (\d+) total leaked bytes", proc.stdout + proc.stderr
        )
        found[name] = dict(
            returncode=proc.returncode,
            count=int(m[1]) if m else None,
            bytes=int(m[2]) if m else None,
        )
    return found


if "--leaks-now" in sys.argv:
    result = leaks()
    write(source.parent / (prefix+"initial-leaks.json"), result)
    print(result)
    sys.exit()
target = json.loads(source.read_text())["target"]
thresholds = list(range(0, target, 900)) + [target]
while True:
    data = json.loads(source.read_text())
    if data.get("interrupted"):
        sys.exit("Soak process identity changed")
    if thresholds and data["elapsed"] >= thresholds[0]:
        thresholds.pop(0)
        checks.append(dict(t=data["elapsed"], **cli_probe()))
        write(source.parent / (prefix+"cli-probes.json"), checks)
    if data["complete"] and not thresholds:
        break
    time.sleep(15)
samples = data["samples"]
warm = [s for s in samples if s["t"] >= 60]
idle = [s for s in warm if s["state"] == "idle"]
measure = lambda numbers: dict(
    median=round(statistics.median(numbers), 2),
    p95=round(sorted(numbers)[int((len(numbers) - 1) * 0.95)], 2),
    max=max(numbers),
)
summary = dict(
    seconds=data["elapsed"],
    samples=len(samples),
    same_gui_and_broker=all(s["healthy"] for s in samples),
    idle_sample_count=len(idle),
    idle_cpu=measure([s["cpu"] for s in idle]) if idle else None,
    warm_resident_MiB=measure([s["rssMiB"] for s in warm]),
    first_10m_median_rss=round(
        statistics.median(s["rssMiB"] for s in warm if s["t"] <= 600), 2
    ),
    last_10m_median_rss=round(
        statistics.median(s["rssMiB"] for s in warm if s["t"] >= target - 600), 2
    ),
    codex_probe_count=len(checks),
    codex_probes_passed=sum(c["ok"] for c in checks),
    cli_seconds=measure([c["wall_seconds"] for c in checks]),
    final_leaks=leaks(),
)
write(source.parent / (prefix+"stability-summary.json"), summary)
print(json.dumps(summary, indent=2))
