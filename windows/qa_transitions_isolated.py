import os
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from qa_account import account_home

scripts = Path(__file__).resolve().parent
install = Path(sys.argv[1]).resolve()
out = Path(sys.argv[2]).resolve()
out.mkdir(parents=True, exist_ok=True)
with account_home() as (home, work):
    cfg = home / "config.toml"
    cfg.write_text(cfg.read_text().replace("plugins=false", "plugins=true"), encoding="utf8")
    (work / "README.md").write_text("Synthetic checksum fixture.\n", encoding="utf8")
    local = home.parent / "Local"
    local.mkdir()
    env = dict(
        os.environ,
        LOCALAPPDATA=str(local),
        CARTETHYIA_QA_INSTALL=str(install),
        CARTETHYIA_TURN_QA=str(out),
        PYTHONUTF8="1",
    )
    exe = str(install / "runtime/python.exe")
    subprocess.run(
        [exe, "-X", "utf8", "-B", install / "windows/service.py", "register"],
        env=env,
        cwd=work,
        check=True,
    )
    subprocess.run(
        [exe, "-X", "utf8", "-B", scripts / "qa_transition.py"], env=env, cwd=work, check=True
    )
