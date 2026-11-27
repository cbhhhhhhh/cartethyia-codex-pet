"""Measure the installed or freshly compiled hook against an isolated Unix socket."""

import argparse
import json
import os
from pathlib import Path
import socket
import statistics
import subprocess
import tempfile
import time
import uuid

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--installed", action="store_true", help="benchmark the prewarmed release executable")
parser.add_argument("--output", type=Path, default=root / ".build/hook-benchmark.json")
args = parser.parse_args()
with tempfile.TemporaryDirectory(dir="/tmp") as td:
    base = Path(td)
    if args.installed:
        exe = Path.home() / "Applications/Codex Pet Plus.app/Contents/MacOS/pet-hook"
    else:
        exe = base / "pet-hook"
        subprocess.run(
            ["clang", "-Os", "-fobjc-arc", "-Wno-incompatible-pointer-types",
             "-framework", "Foundation", str(root / "src/hook.m"), "-o", str(exe)],
            check=True,
        )
    (base / "token").write_text("isolated-fixture")
    with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as receiver:
        receiver.bind(str(base / "events.sock"))
        receiver.settimeout(1)
        ident = str(uuid.uuid4())
        timings = []
        for event in ["UserPromptSubmit"] + ["PreToolUse"] * 61 + ["Interrupt"]:
            payload = json.dumps(
                dict(
                    hook_event_name=event,
                    session_id=ident,
                    turn_id=ident,
                    tool_name="demo",
                    tool_use_id="demo",
                )
            )
            begin = time.monotonic()
            p = subprocess.run(
                [str(exe)],
                input=payload,
                text=True,
                capture_output=True,
                env=dict(os.environ, PET_PLUS_HOME=td),
                check=True,
            )
            timings.append((time.monotonic() - begin) * 1000)
            assert (
                json.loads(p.stdout) == {}
                and json.loads(receiver.recv(8192))["thread"] == ident
            )
    warm = timings[1:]
    output = dict(
        executable="installed" if args.installed else "newly_compiled",
        first_ms=round(timings[0], 3),
        samples=len(warm),
        median_ms=round(statistics.median(warm), 3),
        p95_ms=round(sorted(warm)[int(0.95 * (len(warm) - 1))], 3),
        max_ms=round(max(warm), 3),
    )
    print(json.dumps(output))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2) + "\n")
