"""Sample a visible installed GUI with no Codex work and exercise native relaunch."""

import ctypes, json, os, subprocess, sys, tempfile, time
from pathlib import Path
from ctypes import wintypes as wt
import psutil

app = Path(sys.argv[1]).resolve()
out = Path(sys.argv[2])
user32 = ctypes.WinDLL("user32", use_last_error=True)


def windows(pid):
    found = []

    @ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    def collect(h, arg):
        owner = wt.DWORD()
        user32.GetWindowThreadProcessId(h, ctypes.byref(owner))
        if owner.value == pid and user32.IsWindowVisible(h):
            buf = ctypes.create_unicode_buffer(256)
            user32.GetWindowTextW(h, buf, len(buf))
            found.append((h, buf.value))
        return True

    user32.EnumWindows(collect, 0)
    return found


def wait(f, seconds=12):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        r = f()
        if r:
            return r
        time.sleep(0.1)
    raise RuntimeError("Windows GUI check timed out")


with tempfile.TemporaryDirectory(prefix="cart-idle-") as d:
    folder = Path(d)
    home = folder / "codex"
    (home / "sessions").mkdir(parents=True)
    env = dict(os.environ, LOCALAPPDATA=d, CODEX_HOME=str(home))
    data = folder / "CartethyiaPet"
    profile = "qa-visible-idle"
    subprocess.run([app / "Cartethyia.exe", "--profile", profile, "--background"], env=env, check=True)
    lock = data / ("instance-" + profile + ".lock")
    wait(lambda: lock.is_file() and lock.stat().st_size)
    pid = int(lock.read_bytes().splitlines()[0])
    p = psutil.Process(pid)
    try:
        status = data / "profiles" / profile / "status.json"
        wait(lambda: status.is_file() and any(title == "Cartethyia" for _, title in windows(pid)))
        for _ in range(3):
            subprocess.run([app / "Cartethyia.exe", "--profile", profile], env=env, check=True)
        h = wait(lambda: next((h for h, t in windows(pid) if t == "卡提希娅 · 设置"), None))
        user32.PostMessageW(h, 0x10, 0, 0)
        assert int(lock.read_bytes().splitlines()[0]) == pid
        time.sleep(4)
        samples = []
        start = time.monotonic()
        for n in range(31):
            time.sleep(max(0, start + 5 * n - time.monotonic()))
            cpu = p.cpu_times()
            v = json.loads(status.read_bytes())
            samples.append(
                dict(
                    elapsed=round(time.monotonic() - start, 3),
                    cpu=cpu.user + cpu.system,
                    rss_mib=round(p.memory_info().rss / 1048576, 2),
                    state=v["state"],
                )
            )
        duration = samples[-1]["elapsed"] - samples[0]["elapsed"]
        measured = 100 * (samples[-1]["cpu"] - samples[0]["cpu"]) / duration
        result = dict(
            default_visible=True,
            same_pid_after_three_launches=True,
            settings_window_opened=True,
            elapsed_s=duration,
            cpu_percent_one_core=round(measured, 3),
            rss_peak_mib=max(x["rss_mib"] for x in samples),
            all_idle=all(x["state"] == "idle" for x in samples),
            samples=samples,
        )
        out.write_text(json.dumps(result, indent=2), encoding="utf8")
        print(json.dumps({k: v for k, v in result.items() if k != "samples"}))
        assert result["all_idle"] and measured < 2 and result["rss_peak_mib"] * 1048576 < 200_000_000
    finally:
        subprocess.run(
            [app / "runtime/python.exe", "-X", "utf8", "-B", app / "windows/service.py", "shutdown"],
            env=env,
            check=True,
        )
        p.wait(10)
