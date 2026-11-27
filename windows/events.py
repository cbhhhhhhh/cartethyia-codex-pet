"""Observe the Windows client's paginated history without reading prompts or command output."""
import sqlite3
import time
import json
from pathlib import Path
from common import CODEX
from observe import Tail


class History:
    tables = ("thread_turns", "thread_items")

    def __init__(self, base=CODEX):
        self.meta_path = base / "state_5.sqlite"
        self.meta_db = None
        self.file = base / "thread_history_1.sqlite"
        self.db = None
        self.live = {}
        self.calls = {}
        self.next_open = 0
        self.began = time.time()
        self.offsets = {}

    def connect(self):
        if not self.file.is_file() or time.monotonic() < self.next_open:
            return
        self.next_open = time.monotonic() + 3
        self.db = sqlite3.connect(self.file.as_uri() + "?mode=ro", uri=True, timeout=0.03)
        self.db.execute("pragma query_only=on")
        for table in self.tables:
            self.offsets[table] = self.db.execute("select coalesce(max(rowid),0) from " + table).fetchone()[0]

    def origin(self, thread, tail):
        origin = tail.origin(thread)
        if origin["role"] != "unknown":
            return origin
        # Resolve directly on session discovery races. Read only identity columns.
        try:
            if self.meta_db is None and self.meta_path.exists():
                self.meta_db = sqlite3.connect(self.meta_path.as_uri()+"?mode=ro", uri=True, timeout=.02)
            if self.meta_db is not None:
                row = self.meta_db.execute("select rollout_path,thread_source from threads where id=?", (thread,)).fetchone()
                if row:
                    if row[1] == "cartethyia_companion":
                        return {"role": "pet"}
                    path = Path(row[0])
                    if path.is_file() and path.stem.endswith(thread):
                        tail.add(path, False)
                        return tail.origin(thread)
        except (OSError, sqlite3.Error, TypeError):
            pass
        return origin

    def event(self, thread, turn, kind, **extra):
        return dict(v=1, source="history", thread=thread, turn=turn, kind=kind, **extra)

    def poll(self):
        try:
            if self.db is None:
                self.connect()
                if self.db is None:
                    return
            db = self.db
            turns, items = self.tables
            for row, thread, turn, status, ordinal, started, root in db.execute(
                "select rowid,thread_id,turn_id,status,rollout_ordinal,started_at,root_turn_id from thread_turns where rowid>? order by rowid limit 512",
                (self.offsets[turns],)
            ):
                self.offsets[turns] = row
                if started is not None and started < int(self.began):
                    continue
                info = dict(ordinal=ordinal, root_turn=root)
                self.live[(thread, turn)] = info
                yield self.event(thread, turn, "start", **info)
            for row, thread, turn, call, typ, done, ordinal, name in db.execute(
                """select rowid,thread_id,turn_id,item_id,item_type,completed_at_ms,rollout_ordinal,
                case when item_type='mcpToolCall' then json_extract(item_json,'$.tool')
                     when item_type='commandExecution' then 'exec_command' else item_type end
                from thread_items where rowid>? order by rowid limit 512""", (self.offsets[items],)
            ):
                self.offsets[items] = row
                if typ not in ("commandExecution","mcpToolCall","dynamicToolCall","fileChange","webSearch"):
                    continue
                self.live.setdefault((thread, turn), dict(ordinal=ordinal))
                fields = dict(call=call, tool=name or typ, ordinal=ordinal)
                yield self.event(thread, turn, "tool", **fields)
                if done is None:
                    self.calls[row] = (thread, turn, fields)
                else:
                    yield self.event(thread, turn, "result", **fields)
            for row, (thread, turn, fields) in list(self.calls.items()):
                rec = db.execute("select completed_at_ms from thread_items where rowid=?", (row,)).fetchone()
                if not rec or rec[0] is not None:
                    del self.calls[row]
                    yield self.event(thread, turn, "result", **fields)
            for thread, turn in list(self.live):
                rec = db.execute("select status from thread_turns where thread_id=? and turn_id=?", (thread,turn)).fetchone()
                terminal = {"completed":"end","interrupted":"abort","failed":"error"}.get(rec[0] if rec else "")
                if terminal:
                    info = self.live.pop((thread,turn))
                    for row in [k for k,v in self.calls.items() if v[:2] == (thread,turn)]:
                        del self.calls[row]
                    yield self.event(thread, turn, terminal, **info)
        except sqlite3.Error:
            if self.db:
                self.db.close()
            self.db = None


class Rollouts(Tail):
    """Windows directory notifications wake the parser for changed historical chats."""
    def __init__(self, base):
        import ctypes
        import threading
        import queue
        self.queue = queue.SimpleQueue()
        super().__init__(base)
        self.native = False
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateFileW.restype = ctypes.c_void_p
        handle = kernel.CreateFileW(str(base), 1, 7, None, 3, 0x02000000, None)
        if handle == ctypes.c_void_p(-1).value:
            return
        self.native = True
        # Tail polls only the paths changed by Win32. An overflow triggers a rescan.
        owner = self
        class Changes:
            def changes(self):
                if not owner.native:
                    raise OSError("directory subscription stopped")
                result = set()
                while not owner.queue.empty():
                    item = owner.queue.get()
                    if item is None:
                        Tail.discover(owner)
                        result.update(owner.files)
                    elif item.is_file():
                        result.add(item)
                return result
            def close(self):
                kernel.CancelIoEx(ctypes.c_void_p(handle), None)
        self.watcher = Changes()
        def watch():
            buf = ctypes.create_string_buffer(32768)
            size = ctypes.c_ulong()
            while kernel.ReadDirectoryChangesW(ctypes.c_void_p(handle), buf, len(buf), True, 25,
                                               ctypes.byref(size), None, None):
                data = buf.raw[:size.value]
                i = 0
                while i+12 <= len(data):
                    import struct
                    following, action, length = struct.unpack_from("<III", data, i)
                    path = base / data[i+12:i+12+length].decode("utf-16-le",errors="replace")
                    if path.suffix == ".jsonl":
                        self.queue.put(path)
                    if not following:
                        break
                    i += following
                if not size.value:
                    self.queue.put(None)
            self.native = False
            kernel.CloseHandle(ctypes.c_void_p(handle))
        threading.Thread(target=watch, daemon=True).start()

    def discover(self, initial=False):
        if initial or not getattr(self,"native",False):
            super().discover(initial)
            return
        while not self.queue.empty():
            path = self.queue.get()
            if path is None:
                super().discover()
            elif path.is_file():
                self.add(path, False)

