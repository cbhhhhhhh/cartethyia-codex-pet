"""Use the installed launcher and an isolated profile to test Win32 mouse delivery."""

import ctypes
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import psutil
import win32con as C
import win32gui as G
import win32api as A
import win32process


def run_native(pid):
    ctypes.windll.user32.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4))
    found = []
    G.EnumWindows(
        lambda h, _: (
            found.append(h)
            if win32process.GetWindowThreadProcessId(h)[1] == pid and G.GetWindowText(h) == "Cartethyia"
            else None
        ),
        None,
    )
    h = found[0]
    l, t, r, b = G.GetWindowRect(h)

    def drag(path, pause):
        for i, point in enumerate(path):
            x, y = G.ScreenToClient(h, point)
            lp = x & 65535 | (y & 65535) << 16
            m = C.WM_LBUTTONDOWN if i == 0 else C.WM_MOUSEMOVE
            G.SendMessageTimeout(h, m, C.MK_LBUTTON, lp, C.SMTO_ABORTIFHUNG, 600)
            time.sleep(0.012)
        time.sleep(pause)
        x, y = G.ScreenToClient(h, path[-1])
        G.SendMessageTimeout(
            h, C.WM_LBUTTONUP, 0, x & 65535 | (y & 65535) << 16, C.SMTO_ABORTIFHUNG, 600
        )

    def drop(target):
        l, t, r, b = G.GetWindowRect(h)
        center = ((l + r) // 2, (t + b) // 2)
        path = [
            (
                int(center[0] + (target[0] - center[0]) * i / 35),
                int(center[1] + (target[1] - center[1]) * i / 35),
            )
            for i in range(36)
        ]
        drag(path, 0.3)
        rect = G.GetWindowRect(h)
        time.sleep(0.45)
        assert G.GetWindowRect(h) == rect
        return rect

    area = A.GetMonitorInfo(A.MonitorFromWindow(h))["Work"]
    center = ((area[0] + area[2]) // 2, (area[1] + area[3]) // 2)
    middle = drop(center)
    assert (
        abs((middle[0] + middle[2]) // 2 - center[0]) < 5
        and abs((middle[1] + middle[3]) // 2 - center[1]) < 5
    ), (center, middle)
    out = {"slow_drop_middle": middle, "delivery": "SendMessageTimeoutW to installed layered HWND"}
    for kind in ("circle", "shake"):
        l, t, r, b = drop(center)
        x, y = (l + r) // 2, (t + b) // 2
        if kind == "circle":
            path = [
                (
                    x + round(50 * (math.cos(i * math.tau / 28) - 1)),
                    y + round(50 * math.sin(i * math.tau / 28)),
                )
                for i in range(29)
            ]
        else:
            path = [(x + round(70 * math.sin(i * math.tau / 12)), y) for i in range(25)]
        drag(path, 0)
        xs = []
        for _ in range(120):
            xs.append(G.GetWindowRect(h)[0])
            time.sleep(0.025)
        out[kind] = dict(
            physical_pixel_span=max(xs) - min(xs),
            rebound=any(b - a > 4 for a, b in zip(xs, xs[1:]))
            and any(a - b > 4 for a, b in zip(xs, xs[1:])),
        )
        assert out[kind]["rebound"]

    return out


if __name__ == "__main__":
    app = Path(sys.argv[1]).resolve()
    with tempfile.TemporaryDirectory(prefix="cart-native-") as folder:
        data = Path(folder)
        home = data / "codex"
        (home / "sessions").mkdir(parents=True)
        env = dict(os.environ, LOCALAPPDATA=folder, CODEX_HOME=str(home))
        lock = data / "CartethyiaPet" / "instance-qa-motion.lock"
        subprocess.run(
            [app / "Cartethyia.exe", "--profile", "qa-motion", "--background"], env=env, check=True
        )
        try:
            for _ in range(100):
                if lock.is_file() and lock.stat().st_size:
                    break
                time.sleep(0.05)
            pid = int(lock.read_bytes().splitlines()[0])
            process = psutil.Process(pid)
            for _ in range(100):
                windows = []
                G.EnumWindows(
                    lambda h, a: (
                        windows.append(h)
                        if win32process.GetWindowThreadProcessId(h)[1] == pid
                        and G.IsWindowVisible(h)
                        and G.GetWindowText(h) == "Cartethyia"
                        else None
                    ),
                    None,
                )
                if windows:
                    break
                time.sleep(0.05)
            result = run_native(pid)
            Path(sys.argv[2]).write_text(json.dumps(result, indent=2), encoding="utf8")
            print(json.dumps(result))
        finally:
            subprocess.run(
                [app / "runtime/python.exe", "-B", app / "windows/service.py", "shutdown"],
                env=env,
                check=True,
            )
            if "process" in locals():
                process.wait(10)
