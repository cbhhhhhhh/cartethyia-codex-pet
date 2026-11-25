"""Exercise a temporary real Chrome stage without access to the user's chat history."""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "src"))
from local_api import LocalStage
from reminders import add

with tempfile.TemporaryDirectory() as d:
    folder = Path(d) / "profiles" / "qa"
    folder.mkdir(parents=True)
    (Path(d)/"appearance").symlink_to(Path.home()/"Library/Application Support/CodexPetPlus/appearance")
    add(Path(d), {"text": "测试待办"})
    (folder / "history.json").write_text(
        json.dumps([dict(user="舞台记录", assistant="好。")])
    )
    state = dict(pack="cartethyia", state="idle", action="idle", bubble="")

    def send(m):
        if m["op"]=="play":state["action"]=m["action"]
        if m["op"] == "chat":
            state["bubble"] = "收到舞台消息 " + m["text"]

    s = LocalStage(folder, send, lambda: state.copy())
    try:
        result = subprocess.run(
            ["node", str(root / "tests/browser.mjs"), str(s.credentials)],
            capture_output=True,
            text=True,
            timeout=40,
        )
        if result.returncode:
            raise RuntimeError(result.stderr[-900:])
        data = json.loads(result.stdout)
        assert all(data.values())
        (root / "docs/v21-web-qa.json").write_text(json.dumps(data, indent=2))
        print(data)
    finally:
        s.close()
