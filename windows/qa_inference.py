"""Measure the two installed llama.cpp engines in isolation from the resident GUI."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time

parser = argparse.ArgumentParser()
parser.add_argument("install", type=Path)
parser.add_argument("out", type=Path)
parser.add_argument("--backend", choices=("cpu", "auto"))
args = parser.parse_args()
app = args.install.resolve()
runtime = Path(os.environ["LOCALAPPDATA"]) / "CartethyiaPet/runtime"

if args.backend:
    sys.path[:0] = [str(app / "windows"), str(app / "src")]
    from chat import generate
    from model_store import TEXT

    updates = []
    answer = generate(
        runtime,
        TEXT,
        "你是合成测试角色。",
        [],
        "用一句中文说说小纸船。",
        threading.Event(),
        updates.append,
        backend=args.backend,
    )
    assert answer["text"].strip() and updates
    print(json.dumps({"stream_updates": len(updates)}))
else:
    import psutil

    data = {}
    for backend in ("cpu", "auto"):
        with tempfile.TemporaryDirectory(prefix="cart-inference-") as local:
            env = dict(os.environ, CODEX_HOME=str(Path(local) / "codex"))
            with subprocess.Popen(
                [
                    app / "runtime/python.exe",
                    "-X",
                    "utf8",
                    "-B",
                    __file__,
                    str(app),
                    str(args.out),
                    "--backend",
                    backend,
                ],
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=subprocess.CREATE_NO_WINDOW,
            ) as process:
                parent = psutil.Process(process.pid)
                observed = {}
                while process.poll() is None:
                    for child in parent.children(recursive=True):
                        try:
                            if child.name().lower() == "llama-server.exe":
                                mem = child.memory_info()
                                key = (child.pid, child.create_time())
                                row = observed.setdefault(
                                    key, {"engine": Path(child.exe()).parent.name, "peak_wset_mib": 0}
                                )
                                row["peak_wset_mib"] = max(
                                    row["peak_wset_mib"], round(mem.peak_wset / 1048576, 2)
                                )
                        except psutil.NoSuchProcess:
                            pass
                    time.sleep(0.025)
                stdout, stderr = process.communicate()
                assert process.returncode == 0, stderr.decode("utf8", errors="replace")[-400:]
            assert len(observed) == 1
            key, row = next(iter(observed.items()))
            assert not psutil.pid_exists(key[0]) or psutil.Process(key[0]).create_time() != key[1]
            assert row["engine"].endswith("cpu" if backend == "cpu" else "vulkan")
            data[backend] = dict(**row, **json.loads(stdout), exited_after_reply=True)
    args.out.write_text(json.dumps(data, indent=2), encoding="utf8")
    print(json.dumps(data))
