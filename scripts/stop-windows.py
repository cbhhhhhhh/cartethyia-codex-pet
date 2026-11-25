"""Only terminate processes running our exact installed GUI binary."""

from pathlib import Path
import os
import signal
import subprocess
import sys
import time

target = str(Path.home() / "Applications/Codex Pet Plus.app/Contents/MacOS/Companion")
rows = subprocess.check_output(["ps", "-axo", "pid=,comm="], text=True)
pids = []
for row in rows.splitlines():
    pid, name = row.strip().split(None, 1)
    if name == target:
        try:
            os.kill(int(pid), signal.SIGTERM)
            pids.append(int(pid))
        except ProcessLookupError:
            pass
for pid in pids:
    for _ in range(50):
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            break
        time.sleep(0.05)
    else:
        sys.exit("伙伴尚未退出，请从菜单栏退出后重试。")
