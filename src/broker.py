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
from pet_response import answer
from dialogue import Rules, gallery, cue_line
from providers import account, list_models
from usage import Ledger
from observe import quota_view
from state import VALID_ID

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
    ledger = Ledger(folder)
    usage_view = None
    pending_reads = set()
    interaction_file = folder / "interaction.json"
    interaction = load(interaction_file, {})
    last_performed = interaction.get("clip", "")
    last_picture = interaction.get("picture", "")
    last_kind = interaction.get("kind", "")
    recent_picture = ""
    def remember():
        save(interaction_file, dict(clip=last_performed, picture=last_picture, kind=last_kind))
    active_turns = {}
    def official(operation, tid="", phase="", turn=""):
        key = (operation, tid, phase, turn)
        if key in pending_reads or len(pending_reads) >= 8:
            return
        pending_reads.add(key)
        options = dict(cfg)
        def read():
            result = None
            problem = ""
            try:
                if operation == "quota":
                    result = quota_view(account("account/rateLimits/read"))
                elif operation == "billing":
                    result = account("account/usage/read", threadId=tid).get("threadUsage")
                else:
                    result = list_models(operation, options)
            except (RuntimeError, ValueError, KeyError, OSError, TimeoutError) as exc:
                problem = str(exc)[:160]
            finally:
                jobs.put((0, "official", (key, result, problem)))
        threading.Thread(target=read, daemon=True).start()

    def usage_display():
        if usage_view is not None:
            data = ledger.view(usage_view)
            stage_view["usage"] = data
            emit("usage", **data)
    def event(e, now):
        tid, turn, kind = e.get("thread", ""), e.get("turn", ""), e.get("kind")
        if not isinstance(tid, str) or not VALID_ID.fullmatch(tid):
            return
        if e.get("role") == "pet" or (base / "pet-threads" / tid).exists():
            return
        if kind == "quota":
            ledger.quota = dict(text=e["text"], used=e["used"])
            ledger.dirty = True
            stage_view["quota"] = e["text"]
            emit("quota", **ledger.quota)
            return
        if not isinstance(turn, str) or not VALID_ID.fullmatch(turn):
            return
        if not e.get("role"):
            e.update(tail.origin(tid))
        if e["role"] == "pet":
            return
        old_turn = active_turns.get(tid)
        new_turn = kind == "start" and old_turn != turn and (tid, turn) not in reducer.closed
        ledger.observe(e)
        if usage_view is not None and (kind in ("usage","end","abort","error") or new_turn):
            usage_display()
        if e["role"] == "child":
            reducer.turns.pop((tid, turn), None)
            return
        if new_turn:
            if old_turn:
                reducer.turns.pop((tid, old_turn), None)
            active_turns[tid] = turn
            emit("turn-start", thread=tid, turn=turn)
            if (usage_view is not None or cfg.get("trackCost")) and e["role"] == "root":
                official("billing", tid, "start", turn)
        if kind in ("end", "error") and e["role"] != "root":
            return
        if kind in ("end", "abort", "error") and (usage_view is not None or cfg.get("trackCost")) and e["role"] == "root":
            official("billing", tid, "end", turn)
        if old_turn and turn != old_turn and not new_turn:
            if (tid, old_turn) in reducer.turns or (tid, turn) in reducer.closed:
                return
            if kind in ("end", "error") and e["role"] != "root":
                return
        reducer.event(e, now)
        if reducer.notice:
            what, thread = reducer.notice
            emit("notice", state=what, thread=thread, turn=reducer.notice_turn, otherActive=any(t.thread != thread and not t.terminal for t in reducer.turns.values()))
            stage_view["notice"] = dict(state=what, thread=thread, turn=reducer.notice_turn, time=time.time())
            reducer.notice = None
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

    def begin(user, whisper, image=None, mode="", picture=""):
        nonlocal cancel, serial
        if cancel:
            cancel.set()
        cancel = threading.Event()
        serial += 1
        current, guard = serial, cancel
        opts = dict(cfg)
        memory = list(history)
        previous_action, previous_picture = last_performed, last_picture
        previous_kind, recent_art = last_kind, recent_picture
        def worker():
            try:
                rules = Rules(opts)
                weather_line = ""
                if (not whisper and opts.get("weatherEnabled") and not rules.places and not rules.weather
                        and any(word in user for word in ("天气", "气温", "降雨"))):
                    weather_line = weather.current(opts.get("weatherCity", ""))
                result = answer(base, folder, opts, memory, user, whisper, mode, image, picture,
                                previous_action, previous_picture, guard,
                                lambda part: jobs.put((current, "part", part)), weather_line, previous_kind, recent_art,
                                lambda phase, route, count: jobs.put((current, "meter", (phase, route, count))))
                if not guard.is_set():
                    jobs.put((current, "done", (result, user, whisper, mode, image)))
            except Exception as ex:
                jobs.put((current, "fail", ("生成未完成：" + str(ex)[:140], whisper and mode != "manual")))

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
                                        "picture",
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
                        if op == "read-aloud" and isinstance(m.get("text"), str):
                            if Rules(cfg).allows(m["text"][:3000]):
                                emit("read-aloud", text=m["text"][:3000])
                            else:
                                emit("ui-error", text="这段旧文字涉及当前人设禁用的话题。")
                        if op == "gallery-refresh":
                            items = list(gallery(folder, cfg.get("pack","cartethyia")).values())
                            emit("gallery", items=items)
                            stage_view["gallery"] = [{k:v for k,v in item.items() if k != "file"} for item in items]
                        if op == "action-line" and isinstance(m.get("clip"), str):
                            if not cfg.get("muted") and not cfg.get("asleep"):
                                line = cue_line(m["clip"], Rules(cfg))
                                if line:
                                    emit("action-line", text=line, clip=m["clip"])
                        if op == "performed" and isinstance(m.get("clip"), str):
                            last_performed = m["clip"][:100]
                            last_kind = "clip"
                            remember()
                        if op == "model-list" and m.get("source") in ("api", "codex"):
                            official(m["source"])
                        if op == "usage-close":
                            usage_view = None
                        if op == "usage":
                            usage_view = m.get("selected", "")
                            data = ledger.view(usage_view)
                            stage_view["usage"] = data
                            emit("usage", **data)
                            if data["selected"] and m.get("refresh", True):
                                official("billing", data["selected"].split("/")[0])
                        if op == "quota-read":
                            if ledger.quota:
                                emit("quota-card", text=ledger.quota["text"] + "（上次快照）")
                            official("quota")
                        if op == "config":
                            old_pack = cfg.get("pack")
                            policy_changed = bool(cfg) and any(cfg.get(k) != m["config"].get(k) for k in
                                ("persona", "avoidWeather", "avoidPlaces", "blockedWords", "chatSource",
                                 "whisperSource", "apiURL", "apiKeyEnv", "apiModel", "codexModel"))
                            cfg = m["config"]
                            if old_pack != cfg.get("pack") or not stage_view.get("gallery"):
                                items = list(gallery(folder, cfg.get("pack", "cartethyia")).values())
                                emit("gallery", items=items)
                                stage_view["gallery"] = [{k:v for k,v in item.items() if k != "file"} for item in items]
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
                                (policy_changed and cancel is not None) or kind_job == "chat"
                                and not cfg.get("chat", True)
                                or kind_job == "whisper"
                                and (cfg.get("muted") or not cfg.get("whispers"))
                            ):
                                if policy_changed:
                                    emit("interrupted")
                                m = {"op": "cancel"}
                                op = "cancel"
                        if (
                            op == "whisper"
                            and cfg.get("whisperReady", True)
                            and not cfg.get("asleep")
                            and kind_job != "chat"
                        ):
                            kind_job = "manual"
                            begin("", True, mode="manual", picture=m.get("picture", ""))
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
                                last_performed = last_picture = last_kind = recent_picture = ""
                                remember()
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
                        event(e, now)
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
                        event(e, now)
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
            ledger.flush()
            if reducer.notice:
                what, thread = reducer.notice
                stage_view["notice"] = dict(state=what, thread=thread, time=time.time())
                emit("notice", state=what, thread=thread, turn=reducer.notice_turn)
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
                if k == "official":
                    key, result, problem = data
                    pending_reads.discard(key)
                    op, tid, phase, turn = key
                    if op == "quota":
                        if result:
                            ledger.quota = result
                            ledger.dirty = True
                            stage_view["quota"] = result["text"]
                            emit("quota", **result)
                        text = (ledger.quota or {}).get("text", "账户暂未提供额度。")
                        emit("quota-card", text=text + ("（上次快照）" if problem and ledger.quota else ""))
                    elif op == "billing":
                        ledger.remember_billing(tid, result, time.time())
                        row = ledger.turns.get(tid + "/" + turn)
                        if row and result and result.get("threadId") == tid and active_turns.get(tid) == turn:
                            if phase == "start" and not row["samples"] and row["status"] == "进行中":
                                row["opening"] = ledger.billing[tid].copy()
                            elif phase == "end" and row.get("opening") and row["status"] != "进行中":
                                row["cost"] = {k:result[k]-v for k,v in row["opening"].items()
                                               if k != "at" and isinstance(v,int) and isinstance(result.get(k),int)
                                               and result[k] >= v}
                        usage_display()
                    else:
                        emit("model-list", source=op, models=result or [], error=problem)
                    continue
                if k == "meter":
                    ledger.record_pet(*data)
                    usage_display()
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
                        result.pop("reported", None)
                        if result.get("clip"):
                            last_performed = result["clip"]
                            last_kind = "clip"
                        recent_picture = result.get("picture", "")
                        if recent_picture:
                            last_picture = recent_picture
                            last_kind = "picture"
                        remember()
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
                            pair.update(clip=result["clip"], picture=result["picture"], art=result["art"])
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
        ledger.flush(force=True)
        tail.close()
        sock.close()
        addr.unlink(missing_ok=True)


if __name__ == "__main__":
    run()
