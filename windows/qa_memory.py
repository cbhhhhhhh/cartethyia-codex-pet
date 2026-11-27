"""Exercise a full process restart and the installed history dialog with two synthetic profiles."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

app = Path(sys.argv[1]).resolve()
output = Path(sys.argv[2]).resolve()
if len(sys.argv) == 3:
    with tempfile.TemporaryDirectory(prefix="cart-memory-") as tmp:
        env = dict(os.environ, LOCALAPPDATA=tmp, CODEX_HOME=str(Path(tmp) / "codex"))
        for phase in ("write", "restart"):
            subprocess.run(
                [app / "runtime/python.exe", "-X", "utf8", "-B", __file__, app, output, phase],
                env=env,
                check=True,
                timeout=70,
            )
    sys.exit(0)

sys.path[:0] = [str(app / "windows"), str(app / "src")]
from app import QApplication, Companion, QLocalServer, QIcon
from common import ROOT, read
from transport import name
from dialogue import gallery
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QMessageBox, QPushButton, QMenu


class Chat(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.server.contexts.append([m["content"] for m in payload["messages"] if m["role"] == "user"])
        self.server.models.append(payload["model"])
        answer = json.dumps(dict(text="记下了。", emotion="happy", action="idle"), ensure_ascii=False)
        delta = {"choices": [{"delta": {"content": answer}}]}
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        self.wfile.write(b"data: " + json.dumps(delta).encode() + b"\n\ndata: [DONE]\n\n")


q = QApplication([])
q.setQuitOnLastWindowClosed(False)
q.setWindowIcon(QIcon(str(ROOT / "art/cartethyia.ico")))
http = ThreadingHTTPServer(("127.0.0.1", 0), Chat)
http.contexts = []
http.models = []
threading.Thread(target=http.serve_forever, daemon=True).start()


def profile(label):
    sock = QLocalServer()
    sock.setSocketOptions(QLocalServer.UserAccessOption)
    assert sock.listen(name(label))
    owner = Companion(label, sock)
    owner.tick.stop()
    owner.work.timer.stop()
    owner.setting("chatSource", "api")
    owner.setting("apiURL", f"http://127.0.0.1:{http.server_port}/v1")
    owner.setting("apiModel", "synthetic-memory")
    owner.setting("localTime", False)
    return owner


def say(owner, text):
    owner.chat(text, None)
    deadline = time.monotonic() + 5
    while owner.cancel is not None and time.monotonic() < deadline:
        q.processEvents()
        time.sleep(0.006)
    assert owner.history[-1]["user"] == text and owner.card.body.text() == "记下了。"


a, b = profile("qa-memory-a"), profile("qa-memory-b")
try:
    assert a.tray.isVisible() and not a.tray.icon().isNull()
    assert a.config["rounds"] == 10
    if sys.argv[3] == "write":
        a.setting("persona", "合成铅笔伙伴")
        a.setting("size", 152)
        a.mapping("review", "jumping")
        for i in range(12):
            say(a, f"合成标记{i:02d}")
        a.perform("提裙行骑士礼", False)
        say(b, "另一本合成记录")
        assert len(read(a.folder / "memory.json", [])) == 10
    else:
        assert (
            a.config["size"],
            a.config["persona"],
            a.config["rounds"],
            a.config["mapping"]["review"],
        ) == (152, "合成铅笔伙伴", 10, "jumping")
        assert a.interaction["clip"] == "提裙行骑士礼" and len(a.history) == 12
        say(a, "复述上下文")
        assert http.contexts[-1][:-1] == [f"合成标记{i:02d}" for i in range(2, 12)], http.contexts[-1]
        assert b.history[0]["user"] == "另一本合成记录"
        a.history_window()
        clear = next(w for w in a.logwindow.findChildren(QPushButton) if w.text() == "清空聊天与记忆")

        def confirm():
            dialog = q.activeModalWidget()
            assert isinstance(dialog, QMessageBox)
            dialog.button(QMessageBox.Yes).click()

        QTimer.singleShot(50, confirm)
        clear.click()
        for key, empty in (("history", []), ("memory", []), ("interaction", {})):
            assert read(a.folder / (key + ".json"), None) == empty
        assert read(b.folder / "memory.json", [])[0]["user"] == "另一本合成记录"
        b.setting("replyArt", True)
        say(b, "太好了，真开心")
        first = b.history[-1]["picture"]
        assert first
        say(b, "太好了，真开心")
        assert not b.history[-1]["picture"]
        say(b, "太好了，真开心")
        assert b.history[-1]["picture"] and b.history[-1]["picture"] != first

        b.setting("whisperSource", "api")
        b.setting("whisperApiModel", "synthetic-gallery")
        menu = QMenu()
        b.fill_menu(menu)
        actions = menu.actions()
        submenu = next(a.menu() for a in actions if a.text() == "配图")
        portraits = {v["title"]: v for v in gallery(b.folder).values()}
        selected = set()
        for action in submenu.actions():
            before = len(http.contexts)
            portrait = portraits[action.text()]
            action.trigger()
            deadline = time.monotonic() + 5
            while b.cancel is not None and time.monotonic() < deadline:
                q.processEvents()
                time.sleep(0.005)
            assert len(http.contexts) == before + 1 and http.models[-1] == "synthetic-gallery"
            assert portrait["description"] in http.contexts[-1][-1]
            assert b.interaction["picture"] == portrait["id"] and b.card.portrait.isVisible()
            selected.add(portrait["id"])
        assert len(selected) == 10
        result = dict(
            rate_limited_contextual_art=True,
            clicked_gallery_items_with_matching_description_and_whisper_model=len(selected),
            tray_icon_visible=True,
            process_restart=True,
            settings_and_last_action_reloaded=True,
            default_context_rounds=10,
            exact_context_after_restart=True,
            history_dialog_confirmed=True,
            cleared_history_memory_and_replay=True,
            other_profile_preserved=True,
        )
        output.write_text(json.dumps(result, indent=2), encoding="utf8")
        print(json.dumps(result))
finally:
    a.shutdown()
    b.shutdown()
    http.shutdown()
    http.server_close()
