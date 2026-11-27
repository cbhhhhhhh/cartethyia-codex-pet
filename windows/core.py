"""Correlate hooks, rollout records and the Windows history projection on the GUI thread."""
import json
import os
import threading
import time
from collections import OrderedDict, deque
from PySide6.QtCore import QObject, QTimer, Signal
from common import CODEX, DATA, write
from events import History, Rollouts
from observe import quota_view
from providers import account
from state import Reducer, VALID_ID
from usage import Ledger

class Work(QObject):
    changed = Signal(dict)
    notice = Signal(str, str, str)
    started = Signal(str, str)
    usageChanged = Signal()
    quotaChanged = Signal(str)
    officialResult = Signal(object, object)
    petMeter = Signal(str, str, object)

    def __init__(self, profile):
        super().__init__()
        self.profile = profile
        self.reducer = Reducer()
        self.history = History()
        self.rollouts = Rollouts(CODEX/"sessions")
        self.ledger = Ledger(profile)
        self.last = {}
        self.quota = self.ledger.quota.get("text", "")
        self.active = {}
        self.seen = OrderedDict()
        self.pending = deque(maxlen=2048)
        self.requests = set()
        self.track_cost = False
        self.audit = os.environ.get("CARTETHYIA_QA_LOG")
        self.heartbeat = 0
        self.officialResult.connect(self.received)
        self.petMeter.connect(self.record_pet)
        self.timer = QTimer(self, interval=85)
        self.timer.timeout.connect(self.poll)
        self.timer.start()

    def record(self, row):
        if self.audit:
            with open(self.audit, "a", encoding="utf8") as f:
                f.write(json.dumps(dict(at=time.time(), **row)) + "\n")

    def record_pet(self, phase, channel, tokens):
        self.ledger.record_pet(phase, channel, tokens)
        self.usageChanged.emit()

    def official(self, operation, thread="", turn="", phase=""):
        key = (operation, thread, turn, phase)
        if key in self.requests or len(self.requests) >= 8:
            return
        self.requests.add(key)
        def fetch():
            result = None
            try:
                if operation == "quota":
                    result = quota_view(account("account/rateLimits/read"))
                else:
                    result = account("account/usage/read", threadId=thread).get("threadUsage")
            except (OSError, ValueError, RuntimeError, TimeoutError):
                pass
            self.officialResult.emit(key, result)
        threading.Thread(target=fetch, daemon=True).start()

    def received(self, key, result):
        self.requests.discard(key)
        operation, thread, turn, phase = key
        if operation == "quota":
            if result:
                self.ledger.quota = result
                self.ledger.dirty = True
                self.quota = result["text"]
            self.quotaChanged.emit(self.quota or "账户额度暂未提供")
            return
        if result and result.get("threadId") == thread:
            self.ledger.remember_billing(thread, result, time.time())
            row = self.ledger.turns.get(thread + "/" + turn)
            if row and self.active.get(thread) == turn:
                if phase == "start" and not row["samples"] and row["status"] == "进行中":
                    row["opening"] = dict(self.ledger.billing[thread])
                if phase == "end" and row.get("opening") and row["status"] != "进行中":
                    row["cost"] = {k: result[k]-v for k,v in row["opening"].items()
                                   if k != "at" and type(v) is int and type(result.get(k)) is int and result[k]>=v}
        self.usageChanged.emit()

    def accept(self, e, deadline=None):
        now = time.monotonic()
        thread, turn, kind = (e.get(k) or "" for k in ("thread", "turn", "kind"))
        if not isinstance(thread,str) or not VALID_ID.fullmatch(thread) or (DATA/"pet-threads"/thread).exists():
            return
        origin = self.history.origin(thread, self.rollouts)
        role = origin.get("role")
        if role == "pet" or kind == "child-stop":
            return
        if role == "unknown":
            until = now + 3 if deadline is None else deadline
            if now < until:
                self.pending.append((until, e))
            return
        e = {**origin, **e, "role": role}
        ordinal, inherited = e.get("ordinal"), origin.get("inherited")
        if e.get("source") == "history" and inherited is not None and (ordinal is None or ordinal <= inherited):
            return
        if kind == "quota":
            if "text" in e:
                self.quota = e["text"]
                self.ledger.quota = {"text":self.quota, "used":e.get("used")}
                self.ledger.dirty = True
            return
        if not isinstance(turn,str) or not VALID_ID.fullmatch(turn):
            return
        key = (thread, turn)
        if kind == "usage":
            self.ledger.observe(e)
            self.usageChanged.emit()
            return
        if role == "child":
            # Only live JSONL past the fork boundary carries authoritative child accounting.
            if e.get("source") == "jsonl":
                self.ledger.observe(e)
                self.usageChanged.emit()
            return
        if key in self.reducer.closed or (e.get("root_turn") and e["root_turn"] != turn):
            return
        signature = (key, kind, e.get("call"), e.get("tool"), e.get("progress"))
        while self.seen and (now - next(iter(self.seen.values())) > 3 or len(self.seen)>4096):
            self.seen.popitem(last=False)
        if signature in self.seen:
            return
        current = self.active.get(thread)
        if kind in ("end", "error", "abort") and (current != turn or key not in self.reducer.turns):
            return
        if current != turn:
            if current and kind != "start":
                return
            if kind not in ("start","tool","approval","result","review"):
                return
            if current:
                self.reducer.turns.pop((thread, current), None)
                self.reducer.closed[(thread, current)] = None
            self.active[thread] = turn
            self.started.emit(thread, turn)
            if self.track_cost and kind == "start":
                self.official("billing", thread, turn, "start")
        self.seen[signature] = now
        self.ledger.observe(e)
        self.reducer.event(e, now)
        if kind == "stop-attempt" and key in self.reducer.turns:
            # Stop is advisory. Keep observing tools until the authoritative terminal or timeout.
            self.reducer.turns[key].expires = now + 120
        if kind in ("end", "error", "abort") and self.track_cost:
            self.official("billing", thread, turn, "end")
        self.record(dict(thread=thread, turn=turn, source=e.get("source"), kind=kind))
        self.refresh()
        self.usageChanged.emit()

    def refresh(self):
        now = time.monotonic()
        status = self.reducer.snapshot(now)
        if self.last != status:
            self.last = status
            self.changed.emit(status)
            self.record(dict(shown=status["state"], thread=status["thread"]))
            self.heartbeat = 0
        if now >= self.heartbeat:
            write(self.profile/"status.json", dict(status, updated=time.time(), online=True))
            self.heartbeat = now + 5
        if self.reducer.notice:
            kind, thread = self.reducer.notice
            self.reducer.notice = None
            turn = self.reducer.notice_turn
            self.record(dict(notice=kind, thread=thread, turn=turn))
            self.notice.emit(kind, thread, turn)

    def close(self):
        self.timer.stop()
        self.rollouts.close()
        for connection in (self.history.db,self.history.meta_db):
            if connection is not None:
                connection.close()
        self.ledger.flush(force=True)

    def poll(self):
        try:
            for e in self.rollouts.poll():
                self.accept(e)
            for e in self.history.poll():
                self.accept(e)
            pending, self.pending = self.pending, deque(maxlen=2048)
            for deadline, e in pending:
                self.accept(e, deadline)
        except OSError:
            pass
        self.ledger.flush()
        self.refresh()
