"""One reducer serves both the official hooks and the read-only compatibility paths."""
import json
from collections import OrderedDict
import os
import time
from PySide6.QtCore import QObject, QTimer, Signal
from common import CODEX, write
from events import History, Rollouts
from state import Reducer


class Work(QObject):
    changed = Signal(dict)
    notice = Signal(str,str)
    def __init__(self, profile):
        super().__init__()
        self.profile = profile
        self.reducer = Reducer()
        self.seen = OrderedDict()
        self.history = History()
        self.rollouts = Rollouts(CODEX/"sessions")
        self.last = {}
        self.quota = ""
        self.audit = os.environ.get("CARTETHYIA_QA_LOG")
        self.timer = QTimer(self, interval=90)
        self.timer.timeout.connect(self.poll)
        self.timer.start()
        self.heartbeat = 0

    def record(self, row):
        if self.audit:
            with open(self.audit,"a",encoding="utf-8") as f:
                f.write(json.dumps(dict(at=time.time(),**row))+"\n")

    def accept(self,e):
        if e.get("kind")=="quota":
            self.quota = e.get("text","")
            return
        now = time.monotonic()
        signature = tuple(e.get(k, "") for k in ("thread","turn","kind","call","tool","progress"))
        while self.seen and (now-next(iter(self.seen.values()))>2 or len(self.seen)>4096):
            self.seen.popitem(last=False)
        if signature in self.seen:
            return
        self.seen[signature] = now
        self.reducer.event(e,now)
        if self.audit:
            self.record({k:e.get(k) for k in ("thread","turn","source","kind")})
        self.refresh()

    def refresh(self):
        now = time.monotonic()
        status = self.reducer.snapshot(now)
        if self.last != status:
            self.last = status
            self.changed.emit(status)
            self.record(dict(shown=status["state"],thread=status["thread"]))
            self.heartbeat=0
        if now>=self.heartbeat:
            write(self.profile/"status.json",dict(status,updated=time.time(),online=True))
            self.heartbeat=now+5
        if self.reducer.notice:
            message,self.reducer.notice=self.reducer.notice,None
            self.notice.emit(*message)

    def poll(self):
        for e in self.history.poll():
            self.accept(e)
        try:
            for e in self.rollouts.poll():
                self.accept(e)
        except OSError:
            pass
        self.refresh()

