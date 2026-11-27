"""Exercise the actual installed Qt card, audio boundary and all three routes on synthetic inputs."""

import argparse, json, os, queue, sys, tempfile, threading, time
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

parser = argparse.ArgumentParser()
parser.add_argument("install", type=Path)
parser.add_argument("out", type=Path)
args = parser.parse_args()
install = args.install.resolve()
sys.path[:0] = [str(install / "windows"), str(install / "src"), str(Path(__file__).resolve().parent)]
from qa_account import account_home, initialize
from preference import Rpc
from dialogue import Rules
from providers import route
from win_credentials import save_key, get_key

runtime = Path(os.environ["LOCALAPPDATA"]) / "CartethyiaPet/runtime"
args.out.parent.mkdir(parents=True, exist_ok=True)


class Fixture(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        assert self.path == "/v1/models"
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'{"data":[{"id":"qa-model"}]}')

    def do_POST(self):
        request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        assert request["model"] == "qa-model" and self.path == "/v1/chat/completions"
        if self.server.guard:
            text = str(request["messages"][1:])
            assert "奥斯陆" not in text and "北京" not in text and "上海" not in text
            phrase = "在奥斯陆，明天会下雨。"
        else:
            phrase = "一只小纸船，平稳地绕过木板。"
        body = json.dumps(dict(text=phrase, action="waving", emotion="happy"), ensure_ascii=False)
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        try:
            for i in range(0, len(body), 4):
                self.wfile.write(
                    b"data: "
                    + json.dumps({"choices": [{"delta": {"content": body[i : i + 4]}}]}).encode()
                    + b"\n\n"
                )
                self.wfile.flush()
                time.sleep(0.035)
            self.wfile.write(b'data: {"choices":[],"usage":{"total_tokens":32}}\n\ndata: [DONE]\n\n')
            self.wfile.flush()
        except (OSError, ConnectionError):
            pass


with account_home() as (home, work), tempfile.TemporaryDirectory(prefix="Cartethyia-routes-") as temp:
    (home / "sessions").mkdir()
    local = Path(temp)
    model_root = local / "CartethyiaPet/runtime"
    for f in runtime.rglob("*"):
        if f.is_file() and f.suffix.lower() != ".zip":
            dst = model_root / f.relative_to(runtime)
            dst.parent.mkdir(parents=True, exist_ok=True)
            os.link(f, dst)
    os.environ["LOCALAPPDATA"] = str(local)
    from app import QApplication, Companion, QIcon, QLocalServer, Qt
    from PySide6.QtWidgets import QMenu, QMessageBox
    from PySide6.QtCore import QTimer
    from transport import name
    from common import read
    from model_store import TEXT

    application = QApplication([])
    application.setQuitOnLastWindowClosed(False)
    application.setWindowIcon(QIcon(str(install / "art/cartethyia.ico")))
    server = QLocalServer()
    server.setSocketOptions(QLocalServer.UserAccessOption)
    assert server.listen(name("routes"))
    owner = Companion("routes", server)
    owner.pet.show()
    owner.open_settings()
    owner.settings.hide()
    owner.tick.stop()
    fixture = ThreadingHTTPServer(("127.0.0.1", 0), Fixture)
    threading.Thread(target=fixture.serve_forever, daemon=True).start()
    origin = f"http://127.0.0.1:{fixture.server_port}"
    block = "不要出现地名以及天气。"
    cfg = owner.config
    cfg.update(
        persona=block,
        voiceChat=True,
        voiceWhisper=True,
        weatherEnabled=True,
        weatherCity="北京",
        model=TEXT,
        apiURL=origin + "/v1",
        apiModel="qa-model",
        codexModel="gpt-6.2-sol",
        notifications=False,
        randomActions=False,
    )
    spoken = []
    deltas = []
    weather = []
    displays = []
    owner.speak = lambda line: spoken.append(line)
    owner.weather.current = lambda city: weather.append(city) or "北京正在下雨。"
    owner.stream.connect(lambda i, text: deltas.append(text))
    normal_display = owner.card.display

    def observe_display(mode, text="", *a, **kw):
        if mode in ("reply", "stream", "cue"):
            displays.append(text)
        return normal_display(mode, text, *a, **kw)

    owner.card.display = observe_display

    def pump():
        application.processEvents()
        time.sleep(0.004)

    def until(predicate, seconds=110):
        end = time.monotonic() + seconds
        while not predicate():
            if time.monotonic() > end:
                raise AssertionError("timed out: " + str(owner.card.mode))
            pump()
        pump()

    def chat(text, **kw):
        before = len(owner.history)
        owner.chat(text, None, **kw)
        until(lambda: owner.cancel is None)
        assert owner.card.mode == "reply"
        if not kw.get("whisper"):
            assert len(owner.history) == before + 1, owner.card.body.text()
        return owner.card.body.text()

    rpc = Rpc(cwd=work, internal=False)
    initialize(rpc)

    def hold_work():
        tool = dict(
            type="function",
            name="wait_for_card_check",
            description="Wait for this local UI test to finish.",
            inputSchema={"type": "object", "properties": {}, "additionalProperties": False},
        )
        thread = rpc.call(
            "thread/start",
            dict(cwd=str(work), approvalPolicy="never", sandbox="read-only", dynamicTools=[tool]),
        )["thread"]["id"]
        turn = rpc.call(
            "turn/start",
            dict(
                threadId=thread,
                input=[
                    dict(
                        type="text",
                        text="You must call wait_for_card_check now with an empty object, wait for its response, then say OK. Use no other tools.",
                    )
                ],
                effort="low",
            ),
        )["turn"]["id"]
        end = time.monotonic() + 80
        while time.monotonic() < end:
            pump()
            try:
                e = rpc.next_event(0.05)
            except queue.Empty:
                continue
            if (
                e
                and e.get("method") == "item/tool/call"
                and e.get("params", {}).get("tool") == "wait_for_card_check"
            ):
                until(
                    lambda: owner.work.last.get("state") == "working"
                    and owner.work.last.get("thread") == thread
                )
                return thread, turn, e["id"]
        raise RuntimeError("Real fixture tool did not start")

    def release_work(tid, turn, ident):
        rpc.send(
            {
                "id": ident,
                "result": {"success": True, "contentItems": [{"type": "inputText", "text": "OK"}]},
            }
        )
        until(lambda: (tid, turn) in owner.work.reducer.closed)

    results = {}
    user_seed = dict(user="旧问提到了北京和天气", assistant="上海在下雨。", id="seed")
    owner.history = [user_seed]
    owner.save_history()
    try:
        for source in ("local", "api", "codex"):
            tid, tr, request_id = hold_work()
            before_rows = len(owner.history)
            cfg.update(chatSource=source, whisperSource="inherit", persona=block)
            fixture.guard = True
            spoken.clear()
            deltas.clear()
            weather.clear()
            displays.clear()
            owner.test_route(False)
            until(lambda: owner.settings.model_status.text().startswith("已连接"))
            text = chat("奥斯陆和北京明天的天气怎么样？")
            assert text and not owner.card.portrait.isVisible() and not owner.history[-1].get("picture")
            pics = QMenu()
            owner.fill_menu(pics)
            menu_actions = pics.actions()
            sub = next(a.menu() for a in menu_actions if a.text() == "配图")
            assert len(sub.actions()) == 10 and all(
                not a.icon().isNull() and a.text() for a in sub.actions()
            )
            selected = sub.actions()[3]
            selected.trigger()
            until(lambda: owner.cancel is None)
            picture = owner.interaction.get("picture")
            assert picture and owner.card.portrait.isVisible()
            chat("刚才那张图再给我看看")
            assert owner.history[-1]["picture"] == picture and owner.card.portrait.isVisible()
            chat("", whisper=True, mode="dream")
            chat("", whisper=True, mode="whisper")
            assert not weather and not deltas and all(Rules(cfg).allows(s) for s in spoken + displays)
            assert all(Rules(cfg).allows(r["assistant"]) for r in owner.history[before_rows:])
            guarded_voices = len(spoken)
            owner.card.close_card()
            owner.perform("提裙行骑士礼")
            # Beats are suppressed during real work. Explicit named actions still play.
            chat("给我行个礼")
            assert owner.history[-1]["clip"] == "提裙行骑士礼"
            chat("刚才那个再来一次")
            assert owner.history[-1]["clip"] == "提裙行骑士礼"
            assert all(Rules(cfg).allows(s) for s in spoken + displays)
            cfg.update(persona="你是纸船，请用中文回答。", weatherEnabled=False)
            fixture.guard = False
            deltas.clear()
            before = len(owner.history)
            owner.chat("编一段有十句话的折纸故事。", None)
            until(lambda: bool(deltas))
            owner.card.stop.click()
            until(lambda: owner.worker is None or not owner.worker.is_alive())
            assert len(owner.history) == before and owner.cancel is None
            assert owner.work.last.get("thread") == tid and owner.work.last["state"] == "working"
            assert not any(r["role"] == "pet" for r in owner.work.ledger.turns.values())
            release_work(tid, tr, request_id)
            results[source] = dict(
                real_work_active=True,
                guarded_bubble_history_voice=True,
                guarded_utterances=guarded_voices,
                blocked_stream_leaks=0,
                plain_text_default=True,
                selected_picture=picture,
                picture_replay=True,
                action_replay=True,
                interrupted_after_delta=True,
                model_connection=True,
            )
            args.out.write_text(json.dumps(results, indent=2), encoding="utf8")
            cfg["weatherEnabled"] = True
        cfg.update(chatSource="local", whisperSource="api", persona=block, weatherEnabled=True)
        fixture.guard = True
        assert route(cfg, False)[0] == "local" and route(cfg, True)[0] == "api"
        chat("", whisper=True, picture="happy-1")
        assert owner.interaction["picture"] == "happy-1"
        save_key(origin, "synthetic-test-key")
        assert get_key(origin) == "synthetic-test-key"
        save_key(origin, "")
        assert get_key(origin) == ""
        assert not (owner.cfgfile.exists() and b"synthetic-test-key" in owner.cfgfile.read_bytes())
        cfg["weatherEnabled"] = False
        owner.card.close_card()
        owner.last_cue = 0
        owner.perform("提裙行骑士礼")
        until(lambda: owner.card.mode == "cue", 5)
        assert Rules(cfg).allows(owner.card.body.text())
        roots = owner.work.ledger.view()["options"]
        assert len(roots) == 3, len(roots)
        assert all(
            k in owner.work.ledger.pet
            for k in (
                "聊天 · local",
                "聊天 · api",
                "聊天 · codex",
                "碎碎念 · local",
                "碎碎念 · api",
                "碎碎念 · codex",
            )
        )
        settings = owner.folder / "config.json"
        owner.setting("persona", "合成档案A")
        assert read(settings, {})["persona"] == "合成档案A"
        other = Companion("other-routes", QLocalServer())
        assert other.history == [] and other.config["persona"] != owner.config["persona"]
        other.shutdown()
        results["shared"] = dict(
            gallery_thumbnails=10,
            independent_sources=True,
            cue_checked=True,
            credential_roundtrip=True,
            separate_pet_meters=6,
            work_roots_excluding_all_pet_calls=len(roots),
            persisted_history_rounds=len(read(owner.folder / "history.json", [])),
            isolated_profile=True,
            windows_gazetteer_terms=sum(
                len(x) for x in __import__("dialogue").windows_places().values()
            ),
        )
        args.out.write_text(json.dumps(results, indent=2), encoding="utf8")
        print(json.dumps(results), flush=True)
    finally:
        fixture.shutdown()
        fixture.server_close()
        rpc.close()
        owner.shutdown()
        for widget in application.topLevelWidgets():
            widget.hide()
