"""Read-only rollout fallback. Start at EOF, including for old chats resumed later."""

import json
import time
import re
from datetime import datetime, timedelta
from state import VALID_ID


class Tail:
    def __init__(self, base):
        self.base = base
        self.files = {}
        self.began = time.time()
        self.next_scan = 0
        self.watcher = None
        self.pending = set()
        try:
            from watch import RolloutWatch

            self.watcher = RolloutWatch(base)
            for path in self.watcher.initial:
                self.add(path, True)
        except (AttributeError, OSError):
            self.close()
            self.discover(initial=True)

    def close(self):
        if self.watcher is not None:
            self.watcher.close()
            self.watcher = None

    def __del__(self):
        self.close()

    def discover(self, initial=False):
        today = datetime.now()
        for day in (today, today - timedelta(days=1)):
            for f in (self.base / day.strftime("%Y/%m/%d")).glob("*.jsonl"):
                self.add(f, initial)
        # A resumed chat keeps its original date. Follow recently written historical files.
        if initial or time.monotonic() >= getattr(self, "historical", 0):
            self.historical = time.monotonic() + 0.6
            for f in self.base.glob("*/*/*/*.jsonl"):
                if f not in self.files and f.stat().st_mtime >= self.began - 2:
                    self.add(f, initial)

    def add(self, f, initial):
        if f in self.files:
            return
        s = f.stat()
        # Old chat first discovered after resume: filter old records by timestamp.
        offset = (
            s.st_size
            if initial or s.st_mtime < self.began
            else max(0, s.st_size - 2 * 1024 * 1024)
        )
        m = re.search(r"([0-9a-fA-F-]{36})\.jsonl$", f.name)
        if m:
            self.files[f] = [s.st_ino, offset, m.group(1), "", False]

    @staticmethod
    def prior_turn(f, end):
        # Existing files start at EOF. Recover only the turn identity when a new
        # live tool record arrives without one. Historical events never play.
        with f.open("rb") as fp:
            lo = max(0, end - 8 * 1024 * 1024)
            fp.seek(lo)
            lines = fp.read(end - lo).splitlines()
        for line in reversed(lines):
            if b'"turn_context"' not in line and b'"task_started"' not in line:
                continue
            try:
                r = json.loads(line)
                p = r["payload"]
                if r["type"] == "turn_context" or (
                    r["type"] == "event_msg" and p.get("type") == "task_started"
                ):
                    turn = p.get("turn_id", "")
                    if VALID_ID.fullmatch(turn):
                        return turn
            except (KeyError, ValueError, TypeError, AttributeError):
                pass
        return ""

    def poll(self):
        if self.watcher is not None:
            try:
                changed = self.watcher.changes() | self.pending
                self.pending = set()
                for f in changed:
                    if f not in self.files and f.exists():
                        self.add(f, False)
                targets = [(f, self.files[f]) for f in changed if f in self.files]
            except OSError:
                self.close()
                self.discover()
                targets = list(self.files.items())
        else:
            self.discover()
            targets = list(self.files.items())
        for f, cur in targets:
            try:
                s = f.stat()
            except FileNotFoundError:
                del self.files[f]
                continue
            if s.st_ino != cur[0] or s.st_size < cur[1]:
                cur[:2] = [s.st_ino, 0]
            if s.st_size == cur[1]:
                continue
            with f.open("rb") as fp:
                if not cur[3] and cur[1]:
                    cur[3] = self.prior_turn(f, cur[1])
                fp.seek(cur[1])
                budget = 4 * 1024 * 1024
                while budget > 0:
                    line = fp.readline(2 * 1024 * 1024)
                    budget -= len(line)
                    if not line:
                        break
                    if not line.endswith(b"\n"):
                        if len(line) == 2 * 1024 * 1024:
                            cur[1] = fp.tell()
                            cur[4] = True
                            continue
                        break
                    cur[1] = fp.tell()
                    if cur[4]:
                        cur[4] = False
                        continue
                    try:
                        r = json.loads(line)
                        p = r["payload"]
                        typ = p.get("type")
                        group = r["type"]
                        if group == "turn_context":
                            cur[3] = p.get("turn_id", "")
                        if group == "event_msg" and typ == "task_started":
                            cur[3] = p.get("turn_id", "")
                        stamp = datetime.fromisoformat(
                            r["timestamp"].replace("Z", "+00:00")
                        ).timestamp()
                        if stamp < self.began or time.time() - stamp > 120:
                            continue
                        e = dict(
                            v=1,
                            thread=cur[2],
                            turn=p.get("turn_id") or cur[3],
                            source="jsonl",
                        )
                        if (
                            group == "event_msg"
                            and typ == "token_count"
                            and p.get("rate_limits")
                        ):
                            windows = p["rate_limits"]
                            parts = []
                            percents = []
                            for name in ["primary", "secondary"]:
                                win = windows.get(name) or {}
                                if isinstance(win.get("used_percent"), (float, int)):
                                    percents.append(
                                        max(0, min(100, win["used_percent"]))
                                    )
                                    parts.append(
                                        f"{win.get('window_minutes', '?')} 分钟窗已用 {win['used_percent']:g}%"
                                    )
                            if parts:
                                yield dict(
                                    e,
                                    kind="quota",
                                    used=max(percents),
                                    text=" · ".join(parts),
                                )
                        elif group == "event_msg" and typ in (
                            "task_started",
                            "task_complete",
                            "turn_aborted",
                            "error",
                        ):
                            yield dict(
                                e,
                                kind={
                                    "task_started": "start",
                                    "task_complete": "end",
                                    "turn_aborted": "abort",
                                    "error": "error",
                                }[typ],
                            )
                        elif group == "response_item" and typ in (
                            "custom_tool_call",
                            "function_call",
                            "custom_tool_call_output",
                            "function_call_output",
                        ):
                            name = p.get("name", "")
                            yield dict(
                                e,
                                kind="result" if typ.endswith("output") else "tool",
                                call=p.get("call_id", ""),
                                tool=name,
                            )
                            if name == "update_plan" and typ == "function_call":
                                plan = json.loads(p.get("arguments", "{}")).get(
                                    "plan", []
                                )
                                if plan:
                                    yield dict(
                                        e,
                                        kind="plan",
                                        completed=all(
                                            x.get("status") == "completed" for x in plan
                                        ),
                                        progress=f"{sum(x.get('status') == 'completed' for x in plan)}/{len(plan)}"
                                        + next(
                                            (
                                                " · " + str(x.get("step", ""))[:64]
                                                for x in plan
                                                if x.get("status") == "in_progress"
                                                and x.get("step")
                                            ),
                                            "",
                                        ),
                                    )
                        elif (
                            group == "response_item"
                            and p.get("phase") == "final_answer"
                        ):
                            yield dict(e, kind="review")
                    except (KeyError, ValueError, TypeError, AttributeError):
                        continue

            if budget <= 0 and cur[1] < s.st_size:
                self.pending.add(f)
