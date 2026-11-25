"""Install the actual arm64 release in a fresh user directory, run it, upgrade and uninstall."""
import argparse
import json
import os
import subprocess
import tempfile
import time
import urllib.request
from urllib.parse import quote
import uuid
from pathlib import Path

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument("zip", nargs="?", type=Path, default=root / "dist/Cartethyia-Codex-Pet-macOS-arm64.zip")
parser.add_argument("--full", action="store_true", help="also install and run real on-device text inference")
parser.add_argument("--vision", action="store_true", help="also install and exercise the optional local vision model")
parser.add_argument("--cache", type=Path, help="optional directory with the pinned llama.tar.gz and GGUF")
args = parser.parse_args()
archive = args.zip.resolve()


def wait_for(get):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        result = get()
        if result:
            return result
        time.sleep(0.04)
    raise AssertionError("timed out waiting for " + get.__name__)


with tempfile.TemporaryDirectory(dir="/tmp", prefix="cpp-") as tmp:
    home = Path(tmp)
    cfg = home / ".codex/config.toml"
    cfg.parent.mkdir()
    pristine = b"# preserved during upgrade\n[analytics]\nenabled = false\n"
    cfg.write_bytes(pristine)
    base = home / "Library/Application Support/CodexPetPlus"
    app = home / "Applications/Codex Pet Plus.app/Contents"
    env = dict(os.environ, HOME=tmp, CODEX_HOME=str(cfg.parent), PET_PLUS_HOME=str(base),
               CFFIXED_USER_HOME=tmp, CODEX_DISABLE_UPDATE_CHECK="1",
               PATH="/usr/bin:/bin:/usr/sbin:/sbin")
    stage = home / "Cartethyia-Codex-Pet"
    subprocess.run(["unzip", "-tq", str(archive)], check=True)
    subprocess.run(["/usr/bin/ditto", "-x", "-k", str(archive), tmp], check=True)

    def install(*flags):
        subprocess.run([stage / "install.sh", *flags, "--no-launch"], env=env, check=True, cwd=stage)

    install("--events")
    assert (base / "events-only").exists()
    exe = subprocess.check_output([app / "Resources/pet-python", "-I", "-B", "-c",
                                   "import sys; print(sys.executable)"], env=env, text=True).strip()
    assert Path(exe).resolve().is_relative_to((base / "runtime").resolve())
    plugin = json.loads((base / "marketplace/plugins/pet-plus/.mcp.json").read_text())
    assert plugin["mcpServers"]["pet_plus"]["command"] == str(app / "Resources/pet-python")
    assert (base / "backup/config.before").read_bytes() == pristine
    assert not (cfg.parent / "pets/cartethyia").exists()
    assert str(app / "Resources/mcp.py") in (base / "marketplace/plugins/pet-plus/.mcp.json").read_text()
    assert (app / "Resources/Cartethyia.icns").stat().st_size > 1024
    subprocess.run(["codesign", "--verify", "--deep", "--strict", app.parent], check=True)
    assert subprocess.check_output(["lipo", "-archs", app / "MacOS/Companion"]).strip() == b"arm64"
    assert subprocess.check_output(["/usr/libexec/PlistBuddy", "-c", "Print LSMinimumSystemVersion",
                                    app / "Info.plist"]).strip() == b"27.2"
    assert (stage / "安装.command").stat().st_mode & 0o111

    proc = subprocess.Popen([app / "MacOS/Companion", "--api"], env=env)
    try:
        creds = base / "profiles/main/api.json"
        wait_for(creds.is_file)
        auth = json.loads(creds.read_text())
        def get(resource):
            req = urllib.request.Request(auth["origin"] + "/v1/" + resource,
                                         headers={"Authorization": "Bearer " + auth["token"]})
            with urllib.request.urlopen(req, timeout=3) as response:
                return response.read()

        assert get("sprite")[:4] == b"RIFF"
        clips = json.loads(get("clips"))
        assert len(clips) == 109 and sum(x["frames"] for x in clips.values()) == 1744
        assert get("clip/" + quote(next(iter(clips)), safe=""))[:4] in (b"\x89PNG", b"RIFF")
        ids = dict(session_id=str(uuid.uuid4()), turn_id=str(uuid.uuid4()))
        for event, expected in (("UserPromptSubmit", "thinking"), ("PreToolUse", "working"),
                                ("PermissionRequest", "waiting-for-approval"), ("Interrupt", "idle")):
            msg = dict(ids, hook_event_name=event, tool_name="release-check", tool_use_id="fixture")
            subprocess.run([app / "MacOS/pet-hook"], input=json.dumps(msg).encode(), env=env,
                           check=True, stdout=subprocess.DEVNULL)
            wait_for(lambda: json.loads(get("state")).get("state") == expected)
        print("PASS  arm64, signed app, bundled sprite, 109 clips, native hook and state transitions", flush=True)
    finally:
        proc.terminate()
        proc.wait(timeout=10)

    if args.full or args.vision:
        if args.cache:
            cache = stage / ".runtime"
            cache.mkdir(exist_ok=True)
            for name in ("llama.tar.gz", "qwen2.5-1.5b-instruct-q4_k_m.gguf"):
                subprocess.run(["ditto", args.cache / name, cache / name], check=True)
            if args.vision:
                subprocess.run(["ditto", args.cache / "vision", cache / "vision"], check=True)
        install("--full", *(["--vision"] if args.vision else []))
        assert not (base / "events-only").exists()
        inference = """
import sys
import threading
from pathlib import Path
from chat import generate
updates = []
runtime = Path(sys.argv[1])
vision = sys.argv[2] == "vision"
args = dict(image="web/portraits/calm-1.png", projector="mmproj-Qwen3VL-2B-Instruct-Q8_0.gguf") if vision else {}
model = "Qwen3VL-2B-Instruct-Q4_K_M.gguf" if vision else "qwen2.5-1.5b-instruct-q4_k_m.gguf"
reply = generate(runtime, model, "你是卡提。", [], "打个招呼吧。", threading.Event(), updates.append, **args)
assert reply["text"].strip() and updates
"""
        for mode in (["text", "vision"] if args.vision else ["text"]):
            subprocess.run([app / "Resources/pet-python", "-B", "-c", inference, base / "runtime", mode],
                           env=env, cwd=app / "Resources", check=True, timeout=120)
            print("PASS  full upgrade and local streaming inference (" + mode + ")", flush=True)
    else:
        install("--events")
    config = cfg.read_bytes()
    assert config.count(b'[marketplaces.cartethyia-local]') == 1
    assert config.count(b'[plugins."pet-plus@cartethyia-local"]') == 1
    subprocess.run([base / "installer/uninstall.sh", "--local-only"], env=env, check=True)
    assert cfg.read_bytes() == pristine
    assert not app.parent.exists() and not base.exists()
    assert not (cfg.parent / "plugins/cache/cartethyia-local").exists()
    print("PASS  repeat installation, installed uninstaller, original config restored")
