import sqlite3
import os
import sys
import json
import time
import socket
import secrets
import selectors
import threading
import queue
import fcntl
import hmac
from pathlib import Path
from state import Reducer, allow_whisper
from archive import context, normalize, keep_image
import uuid
from observe import Tail
from chat import generate

os.umask(0o077)
base = Path(
    os.environ.get(
        "PET_PLUS_HOME", Path.home() / "Library/Application Support/CodexPetPlus"
    )
)
base.mkdir(mode=0o700, parents=True, exist_ok=True)
profile = sys.argv[1] if len(sys.argv) > 1 else "main"
import re

if not re.fullmatch("[a-zA-Z0-9_-]{1,48}", profile):
    sys.exit(2)
folder = base / "profiles" / profile
folder.mkdir(parents=True, exist_ok=True)
lock = (folder / "instance.lock").open("a")
try:
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
except BlockingIOError:
    sys.exit(3)


def load(f, default):
    try:
        return json.loads(f.read_text())
    except (ValueError, OSError):
        return default


def save(f, data):
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False))
    tmp.replace(f)


def emit(message_type, **data):
    print(json.dumps(dict(type=message_type, **data), ensure_ascii=False), flush=True)


def run():
    clock_origin = time.time() - time.monotonic()
    primary = profile == "main"
    sel = selectors.DefaultSelector()
    sel.register(sys.stdin, selectors.EVENT_READ, "ui")
    import hashlib

    token = ""
    addr = base / (
        "listen-" + hashlib.sha256(profile.encode()).hexdigest()[:12] + ".sock"
    )
    if primary:
        token = secrets.token_hex(32)
        (base / "token").write_text(token)
        addr = base / "events.sock"
    addr.unlink(missing_ok=True)
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    sock.bind(str(addr))
    sock.setblocking(False)
    sel.register(sock, selectors.EVENT_READ, "hook")
    tail = Tail(Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")) / "sessions")
    reducer = Reducer()
    prev = None
    last = time.monotonic()
    next_poll = 0
    cfg = {}
    jobs = queue.Queue()
    cancel = None
    serial = 0
    history_file = folder / "memory.json"
    archive_file = folder / "history.json"
    history = normalize(load(archive_file, load(history_file, [])))
    save(archive_file, history)

    def persist():
        save(archive_file, history)
        save(history_file, context(history, cfg.get("rounds", 10)))
        live = {p.get("image") for p in history}
        for f in (folder / "images").glob("*"):
            if str(f) not in live:
                f.unlink(missing_ok=True)

    emit("history", pairs=history)
    workers = []
    from weather import Weather

    weather = Weather()

    def begin(user, whisper, image=None, mode=""):
        nonlocal cancel, serial
        if cancel:
            cancel.set()
        cancel = threading.Event()
        serial += 1
        current, guard = serial, cancel
        opts = dict(cfg)
        if image and not opts.get("projector"):
            opts["model"] = "Qwen3VL-2B-Instruct-Q4_K_M.gguf"
            opts["projector"] = "mmproj-Qwen3VL-2B-Instruct-Q8_0.gguf"
        if whisper and opts.get("whisperModel"):
            opts["model"] = opts["whisperModel"]
        memory = context(history, opts.get("rounds", 10))
        prompt = "结合你的人设说一句闲聊，不超过三十字。" if whisper else user
        if mode == "dream":
            prompt = "你在睡梦中，按人设说一句简短的梦话。"
        if opts.get("localTime"):
            prompt += "\n本地时间 " + time.strftime("%H:%M")

        def worker():
            try:
                weather_line = (
                    weather.current(opts.get("weatherCity", ""))
                    if opts.get("weatherEnabled")
                    else ""
                )
                if weather_line:
                    jobs.put((current, "weather", weather_line))

                def infer(model):
                    return generate(
                        base / "runtime",
                        model,
                        opts["persona"],
                        [] if whisper else memory,
                        prompt + (("\n" + weather_line) if weather_line else ""),
                        guard,
                        lambda s: jobs.put((current, "part", s))
                        if not whisper
                        else None,
                        image=image,
                        projector=opts.get("projector"),
                    )

                try:
                    result = infer(opts["model"])
                except (RuntimeError, ValueError, OSError):
                    if (
                        not whisper
                        or guard.is_set()
                        or opts["model"] == cfg.get("model")
                    ):
                        raise
                    result = infer(cfg["model"])
                jobs.put((current, "done", (result, user, whisper, mode, image)))
            except Exception as ex:
                jobs.put(
                    (current, "fail", ("本地推理未完成：" + str(ex)[:100], whisper))
                )

        workers[:] = [t for t in workers if t.is_alive()]
        t = threading.Thread(target=worker, daemon=True)
        workers.append(t)
        t.start()

    buf = b""
    kind_job = ""
    hook_seen = {}
    next_due = 0
    next_heartbeat = 0
    stage = None
    stage_view = {}
    browser_active = False
    peers_exist = False

    def share(record):
        sockets = (
            list(base.glob("listen-*.sock")) if primary else [base / "events.sock"]
        )
        if primary:
            record["token"] = token
        else:
            try:
                record["token"] = (base / "token").read_text()
            except OSError:
                return
        raw = json.dumps(record).encode()
        for peer in sockets:
            if peer == addr:
                continue
            try:
                sock.sendto(raw, str(peer))
            except OSError:
                pass

    try:
        while True:
            now = time.monotonic()
            if now >= next_heartbeat:
                active = (
                    any(base.glob("listen-*.sock"))
                    if primary
                    else (base / "events.sock").is_socket()
                )
                if active != peers_exist:
                    peers_exist = active
                    emit("peer-count", peers=active)
                if stage:
                    with stage.guard:
                        stage.lock_id()
                        visible = now - stage.last_visible < 4
                        if browser_active != visible:
                            browser_active = visible
                            emit("web-presence", active=visible)
                emit("heartbeat")
                next_heartbeat = now + 2
            for key, _ in sel.select(0.10):
                if key.data == "ui":
                    chunk = os.read(sys.stdin.fileno(), 65536)
                    if not chunk:
                        return
                    buf += chunk
                    while b"\n" in buf:
                        line, buf = buf.split(b"\n", 1)
                        try:
                            m = json.loads(line)
                        except ValueError:
                            continue
                        op = m.get("op")
                        if op == "playback" and stage:
                            with stage.guard:
                                if m.get("id") in stage.playbacks:
                                    stage.playbacks[m["id"]].update(
                                        status=m.get("status"), index=m.get("index", 0)
                                    )
                        if op == "web-open":
                            if stage is None:
                                from local_api import LocalStage

                                stage = LocalStage(
                                    folder,
                                    lambda m: jobs.put((0, "control", m)),
                                    lambda: stage_view.copy(),
                                )
                            emit("web-url", url=stage.url, open=m.get("open", True))
                        if op == "web-event" and stage:
                            stage.click(m.get("id"))
                        if op == "web-revoke" and stage:
                            stage.revoke()
                        if op == "display" and "bubble" in m:
                            stage_view["bubbleId"] = stage_view.get("bubbleId", 0) + 1
                            stage_view["duration"] = m.get("duration", 9)
                        if op == "display":
                            stage_view.update(
                                {
                                    k: m[k]
                                    for k in (
                                        "pose",
                                        "bubble",
                                        "mood",
                                        "variant",
                                        "action",
                                        "asleep",
                                        "clientVisible",
                                    )
                                    if k in m
                                }
                            )
                        if op == "peer" and peers_exist:
                            share(dict(m, channel="peer", v=1, **{"from": profile}))
                        if op == "config":
                            cfg = m["config"]
                            stage_view.update(
                                {
                                    k: cfg[k]
                                    for k in (
                                        "pack",
                                        "size",
                                        "gravity",
                                        "rebound",
                                        "friction",
                                        "throwForce",
                                        "asleep",
                                    )
                                    if k in cfg
                                }
                            )
                            if (
                                kind_job == "chat"
                                and not cfg.get("chat", True)
                                or kind_job == "whisper"
                                and (cfg.get("muted") or not cfg.get("whispers"))
                            ):
                                m = {"op": "cancel"}
                                op = "cancel"
                        if (
                            op == "whisper"
                            and not cfg.get("asleep")
                            and kind_job != "chat"
                        ):
                            kind_job = "manual"
                            begin("", True, mode="manual")
                        if (
                            op == "weather"
                            and cfg.get("weatherEnabled")
                            and cfg.get("weatherCity")
                        ):

                            def lookup(city):
                                try:
                                    result = Weather().current(city)
                                except Exception:
                                    result = ""
                                jobs.put(
                                    (
                                        0,
                                        "manual-weather",
                                        result or "暂时查不到这个城市的天气。",
                                    )
                                )

                            threading.Thread(
                                target=lookup, args=(cfg["weatherCity"],), daemon=True
                            ).start()
                        if op in (
                            "todo-list",
                            "todo-add",
                            "todo-toggle",
                            "todo-delete",
                        ):
                            import reminders

                            try:
                                if op == "todo-add":
                                    reminders.add(base, m)
                                elif op == "todo-toggle":
                                    reminders.toggle(base, m["id"])
                                elif op == "todo-delete":
                                    reminders.delete(base, m["id"])
                                emit("task-list", items=reminders.items(base))
                            except (ValueError, KeyError, OSError, sqlite3.Error):
                                emit(
                                    "ui-error", text="待办无法保存，请检查时间与内容。"
                                )
                        if op == "history-delete" and isinstance(m.get("ids"), list):
                            ids = {i for i in m["ids"] if isinstance(i, str)}
                            history = [p for p in history if p["id"] not in ids]
                            persist()
                            emit("history", pairs=history)
                        if op in ("cancel", "clear"):
                            if cancel:
                                cancel.set()
                            serial += 1
                            cancel = None
                            kind_job = ""
                            if op == "clear":
                                history = []
                                persist()
                                emit("history", pairs=[])
                        if (
                            op == "chat"
                            and cfg.get("chat", True)
                            and str(m.get("text", "")).strip()
                        ):
                            kind_job = "chat"
                            begin(m["text"][:2000], False, m.get("image"))
                else:
                    try:
                        raw = sock.recv(8192)
                        e = json.loads(raw)
                        expected = token if primary else (base / "token").read_text()
                        if not hmac.compare_digest(e.pop("token", ""), expected):
                            continue
                        if primary:
                            for peer in base.glob("listen-*.sock"):
                                try:
                                    sock.sendto(raw, str(peer))
                                except OSError:
                                    pass
                        if e.get("channel") == "peer":
                            if e.get("from") != profile:
                                emit("peer", **e)
                            continue
                        hook_seen[
                            (
                                e.get("thread"),
                                e.get("turn"),
                                e.get("kind"),
                                e.get("call", ""),
                            )
                        ] = now
                        reducer.event(e, now)
                    except (OSError, ValueError, TypeError, AttributeError):
                        pass
            if (
                primary
                and now >= next_due
                and not cfg.get("hidden")
                and not cfg.get("asleep")
                and not cfg.get("muted")
            ):
                next_due = now + 2
                from reminders import pending

                if (base / "reminders.sqlite3").exists():
                    try:
                        for item in pending(base):
                            emit("todo", **item)
                    except sqlite3.Error:
                        pass
            if now >= next_poll:
                next_poll = now + 0.20
                try:
                    for e in tail.poll():
                        if e["kind"] == "quota":
                            stage_view["quota"] = e["text"]
                            emit("quota", text=e["text"], used=e["used"])
                            continue
                        if e["kind"] == "plan" and e.get("completed"):
                            emit(
                                "todo",
                                text="计划已完成",
                                thread=e["thread"],
                                completed=True,
                            )
                        if (
                            now
                            - hook_seen.get(
                                (e["thread"], e["turn"], e["kind"], e.get("call", "")),
                                -999,
                            )
                            > 1.5
                        ):
                            reducer.event(e, now)
                except OSError:
                    pass
                hook_seen = {k: v for k, v in hook_seen.items() if now - v < 2}
            s = reducer.snapshot(now)
            if s["since"]:
                s["since"] += clock_origin
            if s != prev:
                stage_view.update(s)
                stage_view["action"] = cfg.get("mapping", {}).get(s["state"], "idle")
                save(folder / "status.json", s)
                emit("status", **s)
                prev = s
            if reducer.notice:
                what, thread = reducer.notice
                stage_view["notice"] = dict(state=what, thread=thread, time=time.time())
                emit("notice", state=what, thread=thread)
                reducer.notice = None
            if kind_job == "whisper" and (
                s["state"] != "idle"
                or cfg.get("hidden")
                or cfg.get("focus")
                or not allow_whisper(
                    now,
                    -1e14,
                    5,
                    time.localtime().tm_hour,
                    int(cfg.get("quietStart", 22)),
                    int(cfg.get("quietEnd", 8)),
                    cfg.get("whispers"),
                    cfg.get("muted"),
                    False,
                )
            ):
                if cancel:
                    cancel.set()
                serial += 1
                cancel = None
                kind_job = ""
            while not jobs.empty():
                ident, k, data = jobs.get()
                if k == "control":
                    emit("external", command=data)
                    continue
                if k == "manual-weather":
                    emit(k, text=data)
                    continue
                if ident != serial:
                    continue
                if k == "weather":
                    emit("weather", text=data)
                elif k == "part":
                    emit("partial", text=data)
                elif k == "done":
                    result, user, w, mode, image = data
                    cancel = None
                    kind_job = ""
                    if result:
                        if mode != "dream":
                            stage_view["action"] = result["action"]
                        if not w:
                            pair = dict(
                                id=str(uuid.uuid4()),
                                user=user,
                                assistant=result["text"],
                                action=result["action"],
                                emotion=result["emotion"],
                                pack=cfg.get("pack", "cartethyia"),
                            )
                            if image:
                                try:
                                    pair["image"] = keep_image(folder, image)
                                except (ValueError, OSError):
                                    pass
                            if cfg.get("replyArt"):
                                stickers = folder / "stickers"
                                candidates = sorted(
                                    p
                                    for p in stickers.glob("*")
                                    if p.suffix.lower() in (".jpg", ".png", ".jpeg")
                                    and p.is_file()
                                )
                                matching = [
                                    p
                                    for p in candidates
                                    if p.stem.startswith(result["emotion"])
                                ]
                                pair["art"] = [
                                    str(p)
                                    for p in (matching or candidates)[
                                        : max(1, min(3, cfg.get("artLimit", 1)))
                                    ]
                                ]
                                pair["spriteArt"] = not pair["art"]
                            history.append(pair)
                            persist()
                            emit("archive-entry", pair=pair)
                        emit(
                            "dream" if mode == "dream" else "whisper" if w else "reply",
                            manual=mode == "manual",
                            **result,
                        )
                elif k == "fail":
                    cancel = None
                    kind_job = ""
                    if not data[1]:
                        emit("failure", text=data[0])
            if (
                cfg.get("asleep")
                and cfg.get("dreams")
                and not cfg.get("muted")
                and not cfg.get("hidden")
                and now - last >= max(5, cfg.get("minutes", 45)) * 60
                and not cancel
            ):
                last = now
                kind_job = "dream"
                begin("", True, mode="dream")
            if (
                not cancel
                and cfg
                and allow_whisper(
                    now,
                    last,
                    int(cfg.get("minutes", 45)),
                    time.localtime().tm_hour,
                    int(cfg.get("quietStart", 22)),
                    int(cfg.get("quietEnd", 8)),
                    cfg.get("whispers"),
                    cfg.get("muted"),
                    s["state"] != "idle" or cfg.get("hidden") or cfg.get("focus"),
                )
            ):
                last = now
                kind_job = "whisper"
                begin("", True)
    finally:
        if stage:
            stage.close()
        if cancel:
            cancel.set()
        for t in workers:
            t.join(3)
        tail.close()
        sock.close()
        addr.unlink(missing_ok=True)


if __name__ == "__main__":
    run()
