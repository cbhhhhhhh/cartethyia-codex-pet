"""On-demand, loopback-only web stage and authenticated companion control API."""

import hmac
import json
import os
import secrets
import threading
import time
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit, unquote

STAGE = Path(__file__).resolve().parent / "web"
SHIPPED_PETS = STAGE.parent / "pets"

def pet_roots(name):
    home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
    return home / "pets" / name, SHIPPED_PETS / name

PUBLIC = {"/": "index.html", "/stage.js": "stage.js", "/stage.css": "stage.css"}
PUBLIC.update({f"/portraits/{m}-{v}.png": f"portraits/{m}-{v}.png"
               for m in ("calm","happy","curious","focused","sad") for v in (0,1)})
CONTROL = {
    "say",
    "play",
    "move",
    "throw",
    "dismiss",
    "sleep",
    "wake",
    "chat",
    "cancel",
    "whisper",
    "todos",
    "weather",
    "quota",
    "usage",
    "usage-close",
    "clear",
    "todo-add",
    "todo-toggle",
    "todo-delete",
    "history-delete",
    "sequence",
    "stop-sequence",
    "focus-thread",
}
DIRECTED = {"say", "play", "move", "throw", "dismiss", "sequence", "stop-sequence"}


class LocalStage:
    def __init__(self, folder, submit, read):
        self.folder, self.submit, self.read = folder, submit, read
        self.token = secrets.token_urlsafe(32)
        self.lease = None
        self.menus = {}
        self.events = deque(maxlen=64)
        self.seq = 0
        self.last_visible = 0.0
        self.playbacks = {}
        self.guard = threading.RLock()
        stage = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def answer(self, status, value, mime="application/json"):
                data = (
                    json.dumps(value, ensure_ascii=False).encode()
                    if mime == "application/json"
                    else value
                )
                self.send_response(status)
                self.send_header("Content-Type", mime)
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Referrer-Policy", "no-referrer")
                self.send_header(
                    "Content-Security-Policy",
                    "default-src 'self'; img-src 'self' blob:; style-src 'self' 'unsafe-inline'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'",
                )
                self.end_headers()
                try:
                    self.wfile.write(data)
                except (OSError, ConnectionError):
                    pass

            def local(self):
                return (
                    self.headers.get("Host") == stage.address
                    and self.headers.get("Origin", stage.origin) == stage.origin
                )

            def auth(self):
                return self.local() and hmac.compare_digest(
                    self.headers.get("Authorization", "").encode(),
                    ("Bearer " + stage.token).encode(),
                )

            def do_GET(self):
                path = urlsplit(self.path).path
                if path in PUBLIC and self.local():
                    filename = PUBLIC[path]
                    return self.answer(
                        200,
                        (STAGE / filename).read_bytes(),
                        {
                            ".png": "image/png",
                            ".js": "application/javascript",
                            ".html": "text/html; charset=utf-8",
                            ".css": "text/css",
                        }[Path(filename).suffix],
                    )
                if not self.auth():
                    return self.answer(403, {})
                with stage.guard:
                    snapshot = stage.read()
                    if path == "/v1/state":
                        if self.headers.get("X-Pet-Stage") == "visible":
                            stage.last_visible = time.monotonic()
                        return self.answer(
                            200,
                            dict(
                                snapshot,
                                menus=list(stage.menus.values()),
                                events=list(stage.events),
                                leased=bool(stage.lock_id()),
                            ),
                        )
                    if path.startswith("/v1/picture/"):
                        from dialogue import gallery
                        pic = gallery(folder, snapshot.get("pack", "cartethyia")).get(unquote(path[len("/v1/picture/"):]))
                        if pic:
                            img = Path(pic["file"])
                            try:
                                if img.stat().st_size <= 16 * 1024 * 1024:
                                    return self.answer(200, img.read_bytes(), "image/png" if img.suffix.lower() == ".png" else "image/jpeg")
                            except OSError:
                                pass
                        return self.answer(404, {})
                    if path == "/v1/clips" or path.startswith("/v1/clip/"):
                        pack = snapshot.get("pack", "cartethyia")
                        if (
                            not isinstance(pack, str)
                            or "/" in pack
                            or pack.startswith(".")
                        ):
                            return self.answer(404, {})
                        local, shipped = pet_roots(pack)
                        private = folder.parent.parent / "appearance" / pack / "current"
                        pool = next((p for p in (local, shipped, private)
                                     if (p / "pet-plus.json").is_file()), local).resolve()
                        try:
                            clips = json.loads((pool / "pet-plus.json").read_text())[
                                "clips"
                            ]
                        except (OSError, ValueError, KeyError):
                            clips = {}
                        if path == "/v1/clips":
                            return self.answer(
                                200,
                                {
                                    k: {
                                        v: spec[v]
                                        for v in ("frames", "fps", "group")
                                        if v in spec
                                    }
                                    for k, spec in clips.items()
                                },
                            )
                        try:
                            image = (pool / clips[unquote(path[9:])]["file"]).resolve()
                            if (
                                pool not in image.parents
                                or image.suffix.lower() not in (".png", ".webp")
                                or image.stat().st_size > 16 * 1024 * 1024
                            ):
                                raise ValueError()
                            return self.answer(
                                200, image.read_bytes(), "image/" + image.suffix[1:]
                            )
                        except (OSError, KeyError, ValueError):
                            return self.answer(404, {})
                    if path == "/v1/sprite":
                        pack = snapshot.get("pack", "cartethyia")
                        if not isinstance(pack, str) or not pack or "/" in pack or pack.startswith("."):
                            return self.answer(404, {})
                        local, shipped = pet_roots(pack)
                        root = local if (local / "pet.json").is_file() else shipped
                        directory = root.resolve()
                        if directory.parent != root.parent.resolve():
                            return self.answer(404, {})
                        try:
                            meta = json.loads((directory / "pet.json").read_text())
                            sheet = (directory / meta["spritesheetPath"]).resolve()
                            if (
                                sheet.parent != directory
                                or sheet.suffix.lower() not in (".webp", ".png")
                            ):
                                raise ValueError()
                            return self.answer(
                                200,
                                sheet.read_bytes(),
                                "image/" + sheet.suffix[1:].lower(),
                            )
                        except (OSError, KeyError, ValueError):
                            return self.answer(404, {})
                    if path == "/v1/todos":
                        from reminders import items

                        return self.answer(200, items(folder.parent.parent))
                    if path == "/v1/history":
                        try:
                            history = json.loads((folder / "history.json").read_text())
                        except (OSError, ValueError):
                            history = []
                        return self.answer(200, history)
                    if path.startswith("/v1/playback/"):
                        record = stage.playbacks.get(path.split("/")[-1])
                        return (
                            self.answer(200, record) if record else self.answer(404, {})
                        )
                    if path == "/v1/config":
                        try:
                            config = json.loads((folder / "config.json").read_text())
                        except (OSError, ValueError):
                            config = {}
                        return self.answer(200, config)
                    if path == "/v1/models":
                        return self.answer(
                            200,
                            sorted(
                                p.name
                                for p in (folder.parent.parent / "runtime").glob(
                                    "*.gguf"
                                )
                            ),
                        )
                return self.answer(404, {})

            def do_POST(self):
                if not self.auth():
                    return self.answer(403, {})
                if self.path not in ("/v1/control", "/v1/image"):
                    return self.answer(404, {})
                try:
                    n = int(self.headers.get("Content-Length", "0"))
                    if self.path == "/v1/image":
                        if not 0 < n <= 8 * 1024 * 1024:
                            raise ValueError()
                        from archive import keep_image
                        import tempfile, os

                        with tempfile.NamedTemporaryFile(dir=folder) as source:
                            source.write(self.rfile.read(n))
                            source.flush()
                            if os.path.getsize(source.name) != n:
                                raise ValueError()
                            attachment = Path(keep_image(folder, source.name))
                        return self.answer(200, {"image": attachment.name})
                    if not 0 < n <= 8192:
                        raise ValueError()
                    m = json.loads(self.rfile.read(n))
                    if not isinstance(m, dict):
                        raise ValueError()
                    with stage.guard:
                        res = stage.control(m)
                    return self.answer(200, res)
                except PermissionError:
                    return self.answer(409, {"error": "lease-conflict"})
                except (ValueError, TypeError, KeyError):
                    return self.answer(400, {"error": "invalid-control"})

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server = server
        self.address = "127.0.0.1:" + str(server.server_port)
        self.origin = "http://" + self.address
        self.url = self.origin + "/#" + self.token
        self.credentials = folder / "api.json"
        self.credentials.write_text(
            json.dumps(dict(origin=self.origin, token=self.token))
        )
        self.credentials.chmod(0o600)
        threading.Thread(target=server.serve_forever, daemon=True).start()

    def lock_id(self):
        if self.lease and self.lease[1] <= time.monotonic():
            self.revoke()
        return self.lease[0] if self.lease else None

    def revoke(self):
        with self.guard:
            if self.lease:
                self.lease = None
                self.submit({"op": "lease", "held": False})

    def control(self, m):
        op = m.get("op")
        current = self.lock_id()
        if op == "lock":
            if current and m.get("lock") != current:
                raise PermissionError()
            key = current or secrets.token_urlsafe(18)
            ttl = min(60, max(1, int(m.get("seconds", 15))))
            self.lease = (key, time.monotonic() + ttl)
            self.submit({"op": "lease", "held": True})
            return dict(lock=key, seconds=ttl)
        if op == "release":
            if not current or m.get("lock") != current:
                raise PermissionError()
            self.revoke()
            return {"ok": True}
        if op in ("menu-add", "menu-remove"):
            ident = m.get("id")
            if not isinstance(ident, str) or not 0 < len(ident) <= 60:
                raise ValueError()
            if op == "menu-add":
                label = m["label"]
                if (
                    not isinstance(label, str)
                    or not 0 < len(label) <= 60
                    or len(self.menus) >= 48
                    and ident not in self.menus
                ):
                    raise ValueError()
                self.menus[ident] = dict(id=ident, label=label)
            else:
                self.menus.pop(ident, None)
            self.submit(dict(op="menus", items=list(self.menus.values())))
            return {"ok": True}
        if op not in CONTROL:
            raise ValueError()
        if op in DIRECTED and (current or m.get("lock")) and m.get("lock") != current:
            raise PermissionError()
        if op in {"say", "chat", "todo-add"} and not isinstance(m.get("text"), str):
            raise ValueError()
        if op == "sequence":
            steps = m.get("steps")
            if not isinstance(steps, list) or not 1 <= len(steps) <= 24:
                raise ValueError()
            for step in steps:
                if (
                    not isinstance(step, dict)
                    or not isinstance(step.get("action"), str)
                    or not 0 < len(step["action"]) <= 80
                    or not 0.1 <= float(step.get("seconds", 2.4)) <= 12
                ):
                    raise ValueError()
            ident = secrets.token_hex(10)
            if len(self.playbacks) >= 64:
                self.playbacks.pop(next(iter(self.playbacks)))
            self.playbacks[ident] = dict(id=ident, status="queued", index=0)
            self.submit(dict(m, id=ident))
            return {"id": ident, "ok": True}
        if op == "play" and not isinstance(m.get("action"), str):
            raise ValueError()
        if op in ("move", "throw"):
            if not all(
                isinstance(m.get(k), (float, int)) and abs(m[k]) <= 32000
                for k in ("x", "y")
            ):
                raise ValueError()
        if op == "chat" and "image" in m:
            import re

            name = m["image"]
            if not isinstance(name, str) or not re.fullmatch(
                r"[0-9a-f]{64}\.(png|jpg)", name
            ):
                raise ValueError()
            path = self.folder / "images" / name
            if not path.is_file():
                raise ValueError()
            m = dict(m, image=str(path))
        self.submit(m)
        return {"ok": True}

    def click(self, ident):
        with self.guard:
            if ident in self.menus:
                self.seq += 1
                self.events.append(dict(seq=self.seq, id=ident))

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.credentials.unlink(missing_ok=True)
