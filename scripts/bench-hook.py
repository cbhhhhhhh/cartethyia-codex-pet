"""Measure a native hook in a temporary, isolated home. Leaves the user's pet alone."""

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
with tempfile.TemporaryDirectory(dir="/tmp") as td:
    base = Path(td)
    exe = base / "pet-hook"
    subprocess.run(
        [
            "clang",
            "-Os",
            "-DPET_PLUS_TEST",
            "-fobjc-arc",
            "-Wno-incompatible-pointer-types",
            "-framework",
            "Foundation",
            str(root / "src/hook.m"),
            "-o",
            str(exe),
        ],
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
        cold_ms=timings[0],
        samples=len(warm),
        median_ms=statistics.median(warm),
        p95_ms=sorted(warm)[int(0.95 * (len(warm) - 1))],
        max_ms=max(warm),
    )
    print(json.dumps(output))
    (root / "docs/hook-benchmark.json").write_text(json.dumps(output, indent=2))
