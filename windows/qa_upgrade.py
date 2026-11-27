"""Use separate Codex/data/install paths for the destructive lifecycle tests. Then upgrade the real installation."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import time
import tomllib
import uuid
import winreg
import psutil

parser = argparse.ArgumentParser()
parser.add_argument("directory", type=Path)
parser.add_argument("--upgrade-user", action="store_true", required=True)
args = parser.parse_args()
out = args.directory.resolve()
out.mkdir(parents=True, exist_ok=True)
repo = Path(__file__).resolve().parents[1]
real_env = dict(os.environ)
local = Path(real_env["LOCALAPPDATA"])
userapp = local / "Programs/CartethyiaPet"
userdata = local / "CartethyiaPet"
home = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")
previous_setup = repo / "dist/Cartethyia-0.1.0-Windows-x64-Setup.exe"
current_setup = repo / "dist/Cartethyia-0.2.0-Windows-x64-Setup.exe"


def digest(p):
    with p.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


assert digest(previous_setup) == "611ba7070bbed4f24313f4f008ca5ca68e3348f4b2978c4f8ff563a9d46c007a"
assert digest(current_setup) == (current_setup.parent / "SHA256SUMS-Windows.txt").read_text().split()[0]
backup = userdata / "backup" / ("before-0.2-" + uuid.uuid4().hex)
backup.mkdir(parents=True)
if (userdata / "profiles").is_dir():
    shutil.copytree(
        userdata / "profiles",
        backup / "profiles",
        ignore=shutil.ignore_patterns("status.json", "*.lock"),
    )
if (home / "config.toml").exists():
    shutil.copy2(home / "config.toml", backup / "codex.toml")


def todos(path):
    with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as db:
        return (
            list(db.execute("select * from todos"))
            if db.execute("select 1 from sqlite_master where name='todos'").fetchone()
            else list(db.iterdump())
        )


dbpath = userdata / "reminders.sqlite3"
if dbpath.exists():
    with (
        sqlite3.connect(dbpath.as_uri() + "?mode=ro", uri=True) as src,
        sqlite3.connect(backup / "reminders.sqlite3") as dest,
    ):
        src.backup(dest)
area = out / ("isolated-" + uuid.uuid4().hex[:8])
app = area / "app"
qa_local = area / "Local"
data = qa_local / "CartethyiaPet"
codex = area / "Codex"
codex.mkdir(parents=True)
env = dict(real_env, LOCALAPPDATA=str(qa_local), CODEX_HOME=str(codex))
(codex / "config.toml").write_text('model_reasoning_effort="medium"\n', encoding="utf8")
reg = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\{4B5A08E3-1FB6-40AC-B847-3F96BDBA4CF2}_is1"


def version():
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, reg) as key:
        return winreg.QueryValueEx(key, "DisplayVersion")[0]


def installer(exe, path, env, step):
    args = [exe, "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/LOG=" + str(out / (step + ".log"))]
    if exe in (previous_setup, current_setup):
        args += [
            "/DIR=" + str(path),
            "/GROUP=" + ("卡提希娅" if path == userapp else "Cartethyia QA " + area.name),
        ]
    subprocess.run(args, env=env, check=True, timeout=180)
    time.sleep(0.8)


def gui(binary):
    for _ in range(40):
        for p in psutil.process_iter(["name", "exe"]):
            if (
                p.info["name"] == "pythonw.exe"
                and p.info["exe"]
                and Path(p.info["exe"]) == binary / "runtime/pythonw.exe"
            ):
                return p
        time.sleep(0.2)
    raise RuntimeError("Installed GUI did not start")


def shutdown():
    subprocess.run(
        [app / "runtime/python.exe", "-B", app / "windows/service.py", "shutdown"], check=True, env=env
    )
    time.sleep(1)


result = {}
try:
    installer(current_setup, app, env, "01-fresh")
    assert (
        version() == "0.2.0" and gui(app) and json.loads((data / "connection.json").read_bytes())["ok"]
    )
    result["fresh_0_2"] = True
    installer(app / "unins000.exe", app, env, "02-fresh-uninstall")
    assert not (app / "Cartethyia.exe").exists()
    installer(previous_setup, app, env, "03-baseline")
    assert version() == "0.1.0" and gui(app)
    shutdown()
    profile = data / "profiles/main"
    cfg = {
        "pack": "cartethyia",
        "persona": "纸船测试员",
        "model": "qa-saved.gguf",
        "shortcut": "J",
        "size": 173,
        "muted": True,
    }
    before = json.loads((profile / "config.json").read_bytes())
    (profile / "config.json").write_text(json.dumps({**before, **cfg}), encoding="utf8")
    saved = [dict(id="synthetic", user="纸船", assistant="收到了。")]
    for n in ("history", "memory"):
        (profile / (n + ".json")).write_text(json.dumps(saved, ensure_ascii=False), encoding="utf8")
    sys.path.insert(0, str(repo / "src"))
    import reminders

    reminders.add(data, dict(text="折纸验收"))
    with (codex / "config.toml").open("a", encoding="utf8") as f:
        f.write('\n[profiles.after_install]\nmodel_reasoning_effort="low"\n')
    for exe, ver, step in (
        (current_setup, "0.2.0", "04-upgrade"),
        (previous_setup, "0.1.0", "05-rollback"),
        (current_setup, "0.2.0", "06-upgrade"),
    ):
        installer(exe, app, env, step)
        assert gui(app) and version() == ver
        conf = json.loads((profile / "config.json").read_bytes())
        assert all(conf[k] == v for k, v in cfg.items())
        assert all(
            json.loads((profile / (n + ".json")).read_bytes()) == saved for n in ("history", "memory")
        )
        assert [x["text"] for x in reminders.items(data)] == ["折纸验收"]
        result[step] = dict(version=ver, settings=True, history=True, memory=True, todos=True)
    installer(app / "unins000.exe", app, env, "07-remove")
    restored = tomllib.loads((codex / "config.toml").read_text(encoding="utf8"))
    assert restored == {
        "model_reasoning_effort": "medium",
        "profiles": {"after_install": {"model_reasoning_effort": "low"}},
    }
    assert not (app / "Cartethyia.exe").exists()
    result["uninstall_preserved_later_config"] = True
finally:
    installer(current_setup, userapp, real_env, "08-real-upgrade")
p = gui(userapp)
assert version() == "0.2.0" and json.loads((userdata / "connection.json").read_bytes())["ok"]
for f in (backup / "profiles").rglob("*"):
    if not f.is_file():
        continue
    dest = userdata / "profiles" / f.relative_to(backup / "profiles")
    if f.name == "config.json":
        old = json.loads(f.read_bytes())
        new = json.loads(dest.read_bytes())
        assert all(new.get(k) == v for k, v in old.items() if k not in ("x", "y"))
    elif f.name != "usage.json":
        assert digest(f) == digest(dest)
if (backup / "reminders.sqlite3").exists():
    assert todos(backup / "reminders.sqlite3") == todos(dbpath)
owned = tomllib.loads((home / "config.toml").read_text(encoding="utf-8-sig"))
if (backup / "codex.toml").exists():
    assert owned == tomllib.loads((backup / "codex.toml").read_text(encoding="utf-8-sig"))
stage = repo / ".build/windows-app-0.2.0"
files = [f for f in stage.rglob("*") if f.is_file() and "__pycache__" not in f.parts]
assert all(digest(f) == digest(userapp / f.relative_to(stage)) for f in files)
result.update(
    user_version=version(),
    retained_user_data=True,
    installed_files_verified=len(files),
    gui_pid=p.pid,
    installer_sha256=digest(current_setup),
)
(out / "result.json").write_text(json.dumps(result, indent=2), encoding="utf8")
print(json.dumps(result), flush=True)
