"""Normalized v1 events. Deadlines use monotonic time, never chat timestamps."""

from collections import OrderedDict
from dataclasses import dataclass, field
import re

STATES = (
    "idle",
    "thinking",
    "working",
    "waiting-for-approval",
    "review",
    "success",
    "error",
)
RANK = (
    "idle",
    "thinking",
    "review",
    "working",
    "success",
    "error",
    "waiting-for-approval",
)
VALID_ID = re.compile(r"(?i)^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$")


@dataclass
class Turn:
    thread: str
    turn: str
    state: str
    changed: float
    expires: float
    tools: dict = field(default_factory=dict)
    approvals: set = field(default_factory=set)
    unnamed_approvals: set = field(default_factory=set)
    stopping: bool = False
    completed_names: dict = field(default_factory=dict)
    finished_tools: set = field(default_factory=set)
    progress: str = ""
    started: float = 0
    terminal: bool = False
    origin: str = ""


class Reducer:
    def __init__(self):
        self.turns = {}
        self.closed = OrderedDict()
        self.notice = None
        self.notice_turn = ""

    def event(self, e, now):
        thread, turn, kind = (e.get(k, "") for k in ("thread", "turn", "kind"))
        if (
            e.get("v") != 1
            or not VALID_ID.fullmatch(thread)
            or not VALID_ID.fullmatch(turn)
        ):
            return
        key = (thread, turn)
        if key in self.closed:
            return
        t = self.turns.get(key)
        if kind == "end" or kind == "abort" or kind == "error":
            self.closed[key] = None
            if len(self.closed) > 4096:
                self.closed.popitem(last=False)
            self.turns.pop(key, None)
            if kind != "abort":
                state = "success" if kind == "end" else "error"
                self.turns[key] = Turn(
                    thread,
                    turn,
                    state,
                    now,
                    now + 0.55,
                    terminal=True,
                    origin=e.get("source", ""),
                )
                self.notice = (state, thread)
                self.notice_turn = turn
            return
        if kind not in (
            "start",
            "tool",
            "result",
            "approval",
            "plan",
            "review",
            "stop-attempt",
        ):
            return
        if not t:
            t = Turn(thread, turn, "thinking", now, now + 120, started=now)
            self.turns[key] = t
        if kind == "stop-attempt":
            t.state = "review"
            t.stopping = True
            t.changed = now
            t.expires = now + 0.55
            return
        t.stopping = False
        call = e.get("call") or e.get("tool") or "tool"
        prior = t.state
        if kind in ("approval", "tool", "result"):
            if call in t.finished_tools:
                return
            if kind == "result":
                t.finished_tools.add(call)
                name = t.tools.pop(call, "") or e.get("tool", "")
                t.completed_names[name] = now
                t.unnamed_approvals.discard(name)
                t.unnamed_approvals.discard(e.get("tool", ""))
                t.approvals.discard(call)
            elif kind == "approval" and not e.get("call"):
                # PermissionRequest has no promised tool_use_id. A named pending
                # request is released by the matching result, not a fabricated call ID.
                name = e.get("tool", "")[:90]
                if (
                    name not in t.tools.values()
                    and now - t.completed_names.get(name, -999) < 2
                ):
                    return
                t.unnamed_approvals.add(name)
            else:
                t.tools[call] = e.get("tool", "")[:90]
                if kind == "approval":
                    t.approvals.add(call)
            t.state = (
                "waiting-for-approval"
                if t.approvals or t.unnamed_approvals
                else "working"
                if t.tools
                else "thinking"
            )
            if t.state == "waiting-for-approval" and prior != t.state:
                self.notice = (t.state, thread)
                self.notice_turn = turn
        elif kind == "review" and not (t.tools or t.unnamed_approvals):
            t.state = "review"
        elif kind == "plan":
            t.progress = e.get("progress", "")[:120]
        elif kind == "start" and not (t.tools or t.approvals or t.unnamed_approvals):
            t.state = "thinking"
        if prior != t.state:
            t.changed = now
        t.origin = e.get("source", "")
        t.expires = now + (300 if t.state == "waiting-for-approval" else 120)

    def snapshot(self, now):
        for key, t in list(self.turns.items()):
            if t.expires <= now:
                if not t.terminal and not t.stopping:
                    self.notice = ("timeout", t.thread)
                    self.notice_turn = t.turn
                del self.turns[key]
        if not self.turns:
            return dict(
                v=1, state="idle", thread="", tool="", progress="", since=0, source=""
            )
        t = max(self.turns.values(), key=lambda t: (not t.terminal, RANK.index(t.state), t.changed))
        return dict(
            v=1,
            state=t.state,
            thread=t.thread,
            turn=t.turn,
            tool=next(iter(t.unnamed_approvals), next(reversed(t.tools.values()), "")),
            progress=t.progress,
            since=t.started,
            source=t.origin,
        )


def allow_whisper(now, last, minutes, hour, start, end, enabled, muted, busy):
    quiet = (
        (start <= hour < end)
        if start < end
        else (hour >= start or hour < end)
        if start > end
        else False
    )
    return (
        enabled and not (quiet or muted or busy) and now - last >= max(5, minutes) * 60
    )
