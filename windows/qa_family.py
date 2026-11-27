"""Real Ultra/Fast two-child exercise against the installed Windows GUI and its data sources."""

import argparse
import datetime
import json
import os
from pathlib import Path
import queue
import sys
import tempfile
import time

parser = argparse.ArgumentParser()
parser.add_argument("install", type=Path)
parser.add_argument("output", type=Path)
args = parser.parse_args()
install = args.install.resolve()
sys.path[:0] = [str(install / "windows"), str(install / "src"), str(Path(__file__).resolve().parent)]
from qa_account import account_home, initialize
from preference import Rpc

args.output.parent.mkdir(parents=True, exist_ok=True)

with (
    account_home(family=True) as (home, empty),
    tempfile.TemporaryDirectory(prefix="cart-family-data-") as local,
):
    os.environ["LOCALAPPDATA"] = local
    (home / "sessions").mkdir()
    from app import QApplication, Companion, QLocalServer, QIcon, Qt
    from transport import name

    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    app.setWindowIcon(QIcon(str(install / "art/cartethyia.ico")))
    server = QLocalServer()
    server.setSocketOptions(QLocalServer.UserAccessOption)
    assert server.listen(name("qa-family"))
    owner = Companion("qa-family", server)
    owner.config.update(muted=False, notifications=True, randomActions=False)
    owner.pet.show()
    notes = []
    bubbles = []
    paints = []
    events = []
    owner.work.notice.connect(lambda k, t, u: notes.append((k, t, u)))
    owner.pet.painted.connect(lambda s: paints.append((time.time(), s, owner.work.last.get("thread"))))

    def audit(row):
        if "bubble" in row:
            bubbles.append(row.copy())
        if row.get("source"):
            events.append(row.copy())

    owner.work.record = audit
    rpc = Rpc(cwd=empty, internal=False)

    def pump():
        app.processEvents()
        time.sleep(0.004)

    def start(text):
        tid = rpc.call(
            "thread/start",
            dict(
                cwd=str(empty),
                sandbox="read-only",
                approvalPolicy="never",
                model="gpt-6.2-sol",
                serviceTier="priority",
            ),
        )["thread"]["id"]
        turn = rpc.call(
            "turn/start",
            dict(
                threadId=tid,
                input=[dict(type="text", text=text)],
                effort="ultra",
                serviceTier="priority",
            ),
        )["turn"]["id"]
        return tid, turn

    try:
        initialize(rpc)
        root, turn = start(
            "Windows integration test in an empty directory. Spawn exactly TWO parallel subagents, using the available collaboration tools. Ask one to return 2+3, the other 3+4. Have them finish. Wait for BOTH to finish. Only AFTER both have finished, use the real PowerShell shell tool to run Write-Output READY. Then reply with their summed answers. Do not read files or use network tools. All data are synthetic."
        )
        other, second = start("Return the number 3+6 only. No tools.")
        ended = set()
        latest = {}
        status = {}
        deadline = time.monotonic() + 420
        while time.monotonic() < deadline and len(ended) < 2:
            pump()
            try:
                e = rpc.next_event(0.012)
            except queue.Empty:
                continue
            if e is None:
                break
            method = e.get("method")
            p = e.get("params", {})
            tid = p.get("threadId")
            if "id" in e and method:
                rpc.send(
                    {
                        "id": e["id"],
                        "error": {
                            "code": -32601,
                            "message": "No external requests in this synthetic test",
                        },
                    }
                )
            if method == "thread/tokenUsage/updated":
                latest[tid] = (p["tokenUsage"].get("total") or {}).get("totalTokens")
            if method == "turn/completed" and tid in (root, other):
                status[tid] = p["turn"]["status"]
                ended.add(tid)
        until = time.monotonic() + 8
        while time.monotonic() < until:
            pump()

        def source(path):
            with path.open(encoding="utf8") as f:
                head = json.loads(next(f))["payload"]
                inherited = head.get("subagent_history_start_ordinal") or 0
                stamps = []
                total = None
                attr = {}
                for line_no, line in enumerate(f, 1):
                    if line_no <= inherited:
                        continue
                    r = json.loads(line)
                    body = r["payload"]
                    kind = body.get("type")
                    if r["type"] == "event_msg":
                        if kind == "token_count":
                            counts = (body.get("info") or {}).get("total_token_usage") or {}
                            if counts:
                                total = counts["total_tokens"]
                        if kind in ("task_started", "task_complete"):
                            stamps.append((kind, r["timestamp"]))
                            if kind == "task_started":
                                attr = body.get("turn_attribution", {})
                    if r["type"] == "response_item" and kind in ("function_call", "custom_tool_call"):
                        call = body.get("name", "").split(".")[-1]
                        content = str(body.get("arguments") or body.get("input") or "")
                        if call in ("exec_command", "shell_command", "shell") or (
                            "Write-Output" in content and "READY" in content
                        ):
                            stamps.append(("shell", r["timestamp"]))
                    if (
                        r["type"] == "event_msg"
                        and kind in ("exec_command_begin", "exec_command_end")
                        and "READY" in str(body.get("command", []))
                    ):
                        stamps.append(("shell", r["timestamp"]))
                return head["id"], dict(
                    parent=head.get("parent_thread_id"),
                    root=attr.get("root_turn_id"),
                    stamps=stamps,
                    total=total,
                    inherited=inherited,
                )

        logs = dict(source(f) for f in (home / "sessions").rglob("*.jsonl"))
        children = {k: v for k, v in logs.items() if v["parent"] == root and v["root"] == turn}
        child_end = [s for v in children.values() for kind, s in v["stamps"] if kind == "task_complete"]
        ledger = owner.work.ledger
        rrow = ledger.turns.get(root + "/" + turn, {})
        orow = ledger.turns.get(other + "/" + second, {})
        families = [r for r in ledger.turns.values() if rrow and ledger.belongs(r, rrow)]
        child_measured = sorted(r["counts"]["total_tokens"] for r in families if r is not rrow)
        family_count = sum(r["counts"]["total_tokens"] for r in families)
        shown = [t for k, t, u in notes if k == "success"]
        drawn = [r["thread"] for r in bubbles if r["bubble"] == "success"]
        expected = sum(v["total"] or 0 for v in children.values()) + (logs[root]["total"] or 0)
        independent_end = next((s for k, s in logs[other]["stamps"] if k == "task_complete"), None)
        after_independent = [
            r
            for r in paints
            if independent_end and r[0] >= datetime.datetime.fromisoformat(independent_end).timestamp()
        ]
        result = dict(
            model="gpt-6.2-sol",
            reasoning="ultra",
            service_tier="priority",
            roots_completed=sum(v == "completed" for v in status.values()),
            children_completed=len(child_end),
            inherited_records_skipped=sum(v["inherited"] for v in children.values()),
            root_shell_after_children=bool(child_end)
            and any(k == "shell" and s > max(child_end) for k, s in logs[root]["stamps"]),
            child_notices=sum(t in children for t in shown),
            root_notices=shown.count(root),
            independent_notices=shown.count(other),
            child_bubbles=sum(t in children for t in drawn),
            root_bubbles=drawn.count(root),
            independent_bubbles=drawn.count(other),
            root_tokens=rrow.get("counts", {}).get("total_tokens"),
            root_source=logs[root]["total"],
            child_tokens=child_measured,
            child_source=sorted(v["total"] for v in children.values()),
            family_tokens=family_count,
            family_source=expected,
            independent_tokens=orow.get("counts", {}).get("total_tokens"),
            independent_source=logs[other]["total"],
            official_root_token_match=latest.get(root) == logs[root]["total"],
            active_root_painted_during_overlap=any(
                s in ("thinking", "working", "review") and tid == root
                for _, s, tid in after_independent
            ),
            displayed_roots=len(ledger.view()["options"]),
            event_sources=sorted({r["source"] for r in events}),
        )
        args.output.write_text(json.dumps(result, indent=2), encoding="utf8")
        print(json.dumps(result), flush=True)
        assert (
            result["roots_completed"] == len(child_end) == len(children) == 2
            and result["root_shell_after_children"]
        )
        assert (
            shown.count(root) == shown.count(other) == drawn.count(root) == drawn.count(other) == 1
            and len(shown) == len(drawn) == 2
        )
        assert (
            result["root_tokens"] == result["root_source"]
            and child_measured == result["child_source"]
            and result["independent_tokens"] == result["independent_source"]
        )
        assert (
            expected == family_count
            and result["displayed_roots"] == 2
            and result["official_root_token_match"]
            and result["active_root_painted_during_overlap"]
        )
    finally:
        rpc.close()
        owner.shutdown()
        for connection in (owner.work.history.db, owner.work.history.meta_db):
            if connection is not None:
                connection.close()
        owner.work.rollouts.close()
        for widget in app.topLevelWidgets():
            widget.hide()
