"""Per-turn observations and account snapshots. No prompts or tool arguments are stored."""
import json
import time
from datetime import datetime
from pathlib import Path

FIELDS = ("input_tokens", "cached_input_tokens", "output_tokens", "reasoning_output_tokens", "total_tokens")


def counts(value):
    if not isinstance(value, dict) or type(value.get("total_tokens")) is not int or value["total_tokens"] < 0:
        return None
    return {k: value[k] if type(value.get(k)) is int and value[k] >= 0 else None for k in FIELDS}


def money_line(summary, label):
    if not summary:
        return label + " · 暂未提供"
    items = []
    for key, title, unit in (("estimatedUsageCreditsMicros", "估算积分", ""),
                             ("nativeUsageUsdMicros", "原生美元用量", "$"),
                             ("estimatedUsageUsdMicros", "估算美元", "$")):
        value = summary.get(key)
        if isinstance(value, int) and value >= 0:
            items.append(f"{title} {unit}{value / 1_000_000:,.6f}".rstrip("0").rstrip("."))
    return label + " · " + (" / ".join(items) or "暂未提供")


class Ledger:
    def __init__(self, folder):
        self.file = Path(folder) / "usage.json"
        try:
            saved = json.loads(self.file.read_text())
        except (OSError, ValueError):
            saved = {}
        self.turns = saved.get("turns", {})
        self.last = saved.get("last", {})
        self.stamps = saved.get("stamps", {})
        self.billing = saved.get("billing", {})
        self.quota = saved.get("quota", {})
        self.pet = saved.get("pet", {})
        self.latest = {}
        for row in self.turns.values():
            self.latest[row["thread"]] = row["turn"]
        self.dirty = False
        self.next_flush = 0

    def flush(self, force=False):
        if not self.dirty or not force and time.monotonic() < self.next_flush:
            return
        self.next_flush = time.monotonic() + 3
        while len(self.turns) > 2500:
            del self.turns[next(iter(self.turns))]
        for mapping in (self.last, self.billing, self.stamps):
            while len(mapping) > 1500:
                del mapping[next(iter(mapping))]
        payload = {k: getattr(self, k) for k in ("turns", "last", "stamps", "billing", "quota", "pet")}
        temp = self.file.with_suffix(".tmp")
        temp.write_text(json.dumps(payload, ensure_ascii=False))
        temp.replace(self.file)
        self.dirty = False

    def observe(self, event):
        tid, turn = event["thread"], event["turn"]
        key = tid + "/" + turn
        kind = event["kind"]
        if kind not in ("start", "usage", "end", "error", "abort", "tool", "approval"):
            return
        row = self.turns.get(key)
        if row is None:
            row = {"thread": tid, "turn": turn, "time": event.get("stamp", time.time()),
                   "role": event.get("role", "unknown"), "status": "进行中",
                   "counts": dict.fromkeys(FIELDS, 0), "samples": 0,
                   "partial": kind != "start", "root": "", "parent": ""}
            self.turns[key] = row
        if event.get("role") in ("root", "child"):
            row["role"] = event["role"]
        if event.get("parent_thread"):
            row["parent"] = event["parent_thread"]
        if event.get("root_turn"):
            row["root"] = event["root_turn"]
        if event.get("parent_turn"):
            row["parentTurn"] = event["parent_turn"]
        if not self.latest.get(tid) or kind == "start":
            self.latest[tid] = turn
        if kind in ("abort", "end", "error"):
            row["status"] = {"abort": "已中断", "end": "已结束", "error": "失败"}[kind]
        if kind == "usage":
            stamp = event.get("stamp", 0)
            if stamp and stamp < self.stamps.get(tid, 0):
                return
            current = counts(event.get("total"))
            last_sample = counts(event.get("last"))
            if current is None:
                return
            previous = self.last.get(tid) or counts(event.get("baseline"))
            if previous is not None and current == previous:
                return
            if previous and current["total_tokens"] < previous["total_tokens"] and self.latest.get(tid) != turn:
                return
            if stamp:
                self.stamps[tid] = stamp
            if previous and all(current[k] >= previous[k] for k in FIELDS
                                if current[k] is not None and previous.get(k) is not None):
                delta = {k: current[k] - previous[k] if current[k] is not None and previous.get(k) is not None
                         else None for k in FIELDS}
            else:
                if not last_sample:
                    self.last[tid] = current
                    row["partial"] = True
                    self.dirty = True
                    return
                delta = last_sample
                row["partial"] |= bool(previous or current != last_sample)
            self.last[tid] = current
            for name in FIELDS:
                if delta[name] is not None:
                    row["counts"][name] += delta[name]
                elif name not in row.setdefault("unreported", []):
                    row["unreported"].append(name)
            row["samples"] += 1
        self.dirty = True

    def remember_billing(self, tid, value, stamp):
        if value and value.get("threadId") == tid:
            self.billing[tid] = {**{k: value.get(k) for k in
                ("nativeUsageUsdMicros", "estimatedUsageUsdMicros", "estimatedUsageCreditsMicros")},
                "at": stamp}
            self.dirty = True

    def record_pet(self, phase, route, usage):
        row = self.pet.setdefault(route, {"calls": 0, "tokens": 0, "reported": 0})
        if phase == "start":
            row["calls"] += 1
        if phase == "result" and isinstance(usage, int):
            row["tokens"] += usage
            row["reported"] += 1
        self.dirty = True

    def add_pet(self, route, usage):
        self.record_pet("start", route, None)
        self.record_pet("result", route, usage)

    def belongs(self, child, root):
        if child is root:
            return True
        if child["role"] != "child":
            return False
        owner = child
        visited = set()
        while owner.get("parent") and owner["thread"] not in visited:
            visited.add(owner["thread"])
            parent = owner["parent"]
            if owner.get("root") == root["turn"] and parent == root["thread"]:
                return True
            owner = self.turns.get(parent + "/" + owner.get("parentTurn", ""))
            if owner is root:
                return True
            if owner is None:
                return False
        return False

    def view(self, selected=""):
        roots = sorted((r for r in self.turns.values() if r["role"] == "root"),
                       key=lambda r: r["time"], reverse=True)
        row = self.turns.get(selected)
        if row is None or row["role"] != "root":
            row = next((r for r in roots if r["status"] == "进行中"), roots[0] if roots else None)
        listed = roots[:80]
        if row is not None and row not in listed:
            listed.append(row)
        options = [{"key": r["thread"] + "/" + r["turn"],
                    "label": datetime.fromtimestamp(r["time"]).strftime("%m-%d %H:%M") +
                    " · " + r["status"] + " · " + r["thread"][-6:] + "/" + r["turn"][-4:]}
                   for r in listed]
        if row:
            selected = row["thread"] + "/" + row["turn"]
            family = [r for r in self.turns.values() if self.belongs(r, row)]
            children = {}
            for item in family:
                if item is not row:
                    children.setdefault(item["thread"], []).append(item)
            valid = any(r["samples"] for r in family)
            lines = [f"本次请求 · {row['status']} · 已关联 {len(children)} 个子会话"]
            if valid:
                def display(field):
                    if any(field in r.get("unreported", ()) for r in family):
                        return "未提供"
                    return f"{sum(r['counts'][field] for r in family):,}"
                lines += [f"合计 {display('total_tokens')} tokens",
                          f"输入 {display('input_tokens')}（含缓存 {display('cached_input_tokens')}）",
                          f"输出 {display('output_tokens')}（含推理 {display('reasoning_output_tokens')}）"]
                if children:
                    own = f"{row['counts']['total_tokens']:,} tokens" if row["samples"] else "等待数据"
                    lines.append("本轮主会话 · " + own)
                    for thread, items in children.items():
                        amount = sum(child["counts"]["total_tokens"] for child in items)
                        observed = f"{amount:,} tokens" if any(child["samples"] for child in items) else "等待数据"
                        lines.append(f"子会话 …{thread[-6:]} · {observed}")
                if any(r["partial"] or not r["samples"] for r in family):
                    lines.append("本轮数据不完整，仅列出已观察到的用量。")
            else:
                lines.append("等待可归属的 token 数据")
            lines.append(money_line(row.get("cost"), "本轮主会话估算增量") if row.get("cost") else "本轮积分与金额 · 暂不可拆分")
            lines.append("账户周期百分比按全账户统计，单次请求占比未提供。")
            bill = self.billing.get(row["thread"], {})
            thread_counts = self.last.get(row["thread"])
            if thread_counts:
                lines.append(f"主会话累计 · {thread_counts['total_tokens']:,} tokens")
            lines.append(money_line(bill, "整条主会话累计"))
            if bill.get("at"):
                lines.append("账户接口更新于 " + datetime.fromtimestamp(bill["at"]).strftime("%m-%d %H:%M"))
        else:
            lines = ["暂未收到可归属到主会话的任务。"]
        for route, entry in self.pet.items():
            tokens = f"{entry['tokens']:,} tokens" if entry["reported"] else "token 未提供"
            missing = entry["calls"] - entry["reported"]
            detail = f"（{missing} 次未提供 token）" if missing else ""
            lines.append(f"桌宠自身 · {route} · {entry['calls']} 次 · {tokens}{detail}")
        return {"options": options, "selected": selected, "text": "\n".join(lines)}
