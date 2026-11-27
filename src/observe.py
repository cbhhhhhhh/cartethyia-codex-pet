"""Read-only rollout fallback. Start at EOF, including for old chats resumed later."""

import json
import time
import re
from datetime import datetime, timedelta
from state import VALID_ID



def quota_view(data, stamp=None):
    rows = []
    updated = stamp if stamp is not None else time.time()
    buckets = data.get("rateLimitsByLimitId") or {"": data.get("rateLimits", data)}
    for bucket, detail in buckets.items():
        if not isinstance(detail, dict):
            continue
        for name in ("primary", "secondary"):
            window = detail.get(name) or {}
            used = window.get("usedPercent", window.get("used_percent"))
            if not isinstance(used, (float, int)):
                continue
            used = min(100, max(0, used))
            minutes = window.get("windowDurationMins", window.get("window_minutes"))
            period = "额度周期"
            if isinstance(minutes, int) and minutes > 0:
                if minutes % 1440 == 0:
                    period = f"{minutes // 1440} 天额度"
                elif minutes % 60 == 0:
                    period = f"{minutes // 60} 小时额度"
                else:
                    period = f"{minutes} 分钟额度"
            label = detail.get("limitName") or detail.get("limit_name") or bucket
            title = (str(label) + " · " if label and label != "codex" else "") + period
            text = f"{title} · 剩余 {100-used:g}%（已用 {used:g}%）"
            reset = window.get("resetsAt", window.get("resets_at"))
            if isinstance(reset, (int, float)) and 0 < reset < 4102444800:
                text += "\n下次重置 " + datetime.fromtimestamp(reset).strftime("%m-%d %H:%M")
            rows.append((text, used))
    if not rows:
        return None
    return {"text": "\n\n".join(t for t, _ in rows) + "\n\n更新于 " +
            datetime.fromtimestamp(updated).strftime("%m-%d %H:%M"), "used": max(n for _, n in rows)}


class Tail:
    def __init__(self, base):
        self.base = base
        self.files = {}
        self.paths = {}
        self.origins = {}
        self.prefixes = {}
        self.attributes = {}
        self.baselines = {}
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
            tid = m.group(1)
            self.files[f] = [s.st_ino, offset, tid, "", False]
            self.paths[tid] = f

    def origin(self, tid):
        if tid in self.origins:
            return self.origins[tid]
        path = self.paths.get(tid)
        if path:
            try:
                with path.open("rb") as stream:
                    header = json.loads(stream.readline(4 * 1024 * 1024))
                meta = header["payload"]
                if header["type"] == "session_meta" and meta.get("id", meta.get("session_id")) == tid:
                    source = meta.get("source")
                    role, parent = "unknown", ""
                    if isinstance(source, str) and source:
                        role = "root"
                    elif isinstance(source, dict) and "subagent" in source:
                        role = "child"
                        sub = source["subagent"]
                        if isinstance(sub, dict):
                            parent = (sub.get("thread_spawn") or {}).get("parent_thread_id", "")
                    if meta.get("thread_source") == "subagent":
                        role = "child"
                    if meta.get("thread_source") == "cartethyia_companion":
                        role = "pet"
                    born = datetime.fromisoformat(meta["timestamp"].replace("Z", "+00:00")).timestamp()
                    ordinal = meta.get("subagent_history_start_ordinal")
                    self.origins[tid] = dict(role=role, parent_thread=parent or meta.get("parent_thread_id", ""),
                                             born=born, inherited=ordinal if isinstance(ordinal, int) and ordinal >= 0 else None)
                    return self.origins[tid]
            except (OSError, ValueError, KeyError, AttributeError, TypeError):
                pass
        return {"role": "unknown", "born": 0}

    def live_offset(self, fp, tid, origin):
        # Codex rewrites inherited event timestamps at fork time. Its persisted
        # ordinal is the number of copied records after the new session header.
        ordinal = origin.get("inherited")
        if ordinal is None:
            return 0
        lines, offset = self.prefixes.get(tid, (0, 0))
        fp.seek(offset)
        while lines < ordinal + 1:
            part = fp.readline(65536)
            if not part:
                self.prefixes[tid] = (lines, fp.tell())
                return None
            lines += int(part.endswith(b"\n"))
        self.prefixes[tid] = (lines, fp.tell())
        return fp.tell()

    def prior_turn(self, f, end, floor=0):
        # Existing files start at EOF. Recover only the turn identity when a new
        # live tool record arrives without one. Historical events never play.
        with f.open("rb") as fp:
            lo = max(floor, end - 8 * 1024 * 1024)
            fp.seek(lo)
            lines = fp.read(end - lo).splitlines()
        turn = ""
        for line in reversed(lines):
            if b'"total_token_usage"' not in line and b'"turn_context"' not in line and b'"task_started"' not in line:
                continue
            try:
                r = json.loads(line)
                p = r["payload"]
                if p.get("type") == "token_count" and f not in self.baselines:
                    self.baselines[f] = p["info"]["total_token_usage"]
                elif r["type"] == "turn_context" or p.get("type") == "task_started":
                    value = p.get("turn_id", "")
                    if not turn and VALID_ID.fullmatch(value):
                        turn = value
                    if turn == value and p.get("turn_attribution"):
                        self.attributes[(self.files[f][2], turn)] = p["turn_attribution"]
                if turn and (self.files[f][2], turn) in self.attributes and f in self.baselines:
                    break
            except (KeyError, ValueError, TypeError, AttributeError):
                pass
        return turn

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
                cur[:] = [s.st_ino, 0, cur[2], "", False]
                self.origins.pop(cur[2], None)
                self.prefixes.pop(cur[2], None)
            if s.st_size == cur[1]:
                continue
            with f.open("rb") as fp:
                origin = self.origin(cur[2])
                floor = self.live_offset(fp, cur[2], origin)
                if floor is None:
                    continue
                cur[1] = max(cur[1], floor)
                if not cur[3] and cur[1] > floor:
                    cur[3] = self.prior_turn(f, cur[1], floor)
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
                        origin = self.origin(cur[2])
                        if stamp < origin["born"] or origin["role"] == "pet":
                            continue
                        turn = p.get("turn_id") or cur[3]
                        if (group == "turn_context" or typ == "task_started") and turn:
                            attr = p.get("turn_attribution") or {}
                            if attr or p.get("root_turn_id"):
                                self.attributes[(cur[2], turn)] = {
                                "root_turn_id": attr.get("root_turn_id") or p.get("root_turn_id"),
                                "parent_turn_id": attr.get("parent_turn_id")}
                        if stamp < self.began or time.time() - stamp > 120:
                            continue
                        e = dict(
                            v=1,
                            thread=cur[2],
                            turn=p.get("turn_id") or cur[3],
                            source="jsonl",
                        )
                        attr = self.attributes.get((cur[2], turn), {})
                        e.update(role=origin["role"], parent_thread=origin.get("parent_thread", ""),
                                 root_turn=attr.get("root_turn_id"), parent_turn=attr.get("parent_turn_id"),
                                 stamp=stamp)
                        if group == "event_msg" and typ == "token_count":
                            snapshot = quota_view(p.get("rate_limits") or {}, stamp)
                            if snapshot:
                                yield dict(e, kind="quota", **snapshot)
                            info = p.get("info") or {}
                            if info.get("total_token_usage") and turn:
                                yield dict(e, kind="usage", total=info["total_token_usage"],
                                           last=info.get("last_token_usage"), baseline=self.baselines.pop(f, None))
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
