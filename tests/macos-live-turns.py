"""Opt-in diagnostic with the current Codex account. Only artificial arithmetic is sent.

python tests/macos-live-turns.py --account --output path.json
No session content, thread IDs, credentials or prompts enter the report.
"""
import argparse
import json
import os
from pathlib import Path
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/"src"))
from preference import Rpc


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--account", action="store_true", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    home = Path(os.environ.get("CODEX_HOME", Path.home()/".codex"))
    with tempfile.TemporaryDirectory(dir="/tmp", prefix="cart-live-") as temporary:
        temp = Path(temporary)
        isolated, pet, work = (temp/n for n in ("codex","pet","empty"))
        for d in (isolated, pet, work):
            d.mkdir(mode=0o700)
        for candidate in ("auth.json","models_cache.json"):
            if (home/candidate).is_file():
                shutil.copyfile(home/candidate,isolated/candidate)
                (isolated/candidate).chmod(0o600)
        (isolated/"config.toml").write_text('model="gpt-6.2-sol"\nmodel_reasoning_effort="ultra"\nservice_tier="priority"\n[features]\nmulti_agent_v2=true\nplugins=false\napps=false\n[agents]\nmax_threads=3\nmax_depth=1\n')
        os.environ.update(CODEX_HOME=str(isolated),PET_PLUS_HOME=str(pet))
        inbox = queue.Queue()
        broker = subprocess.Popen([sys.executable,"-B","-u",str(ROOT/"src/broker.py"),"main"],
                                  stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
        def listen():
            for line in broker.stdout:
                inbox.put(json.loads(line))
        threading.Thread(target=listen,daemon=True).start()
        def send(op, **values):
            broker.stdin.write(json.dumps(dict(op=op,**values))+"\n");broker.stdin.flush()
        rpc = Rpc(cwd=work)
        try:
            deadline = time.monotonic()+430
            assert inbox.get(timeout=10)["type"]=="history"
            send("config",config=dict(pack="cartethyia",muted=True,chat=False,whispers=False))
            rpc.call("initialize",dict(clientInfo=dict(name="cartethyia_release_test",version="0.2.0"),
                                       capabilities=dict(experimentalApi=True)))
            rpc.send(dict(method="initialized",params={}))
            def start(prompt):
                thread = rpc.call("thread/start",dict(cwd=str(work),sandbox="read-only",approvalPolicy="never",
                                    model="gpt-6.2-sol",serviceTier="priority"))["thread"]["id"]
                turn=rpc.call("turn/start",dict(threadId=thread,input=[dict(type="text",text=prompt)],
                                               effort="ultra",serviceTier="priority"))["turn"]["id"]
                return thread,turn
            root,turn=start("This is a desktop pet integration test in an empty directory. Explicitly spawn exactly two subagents in parallel. Ask one for 2+3 and the other for 3+4. Wait for both answers. AFTER both children have finished, run the harmless shell command /bin/echo READY through a tool, then end your turn with the sum of the two answers. Do not inspect files or use external services.")
            other,second=start("Return only the sum of 3 and 6. Do not call tools.")
            latest = {}
            ended=set()
            updates=0
            while time.monotonic()<deadline and len(ended)<2:
                try: msg=rpc.next_event(.5)
                except queue.Empty: continue
                if msg is None: break
                p=msg.get("params",{});method=msg.get("method")
                if msg.get("id") is not None and method:
                    rpc.send({"id":msg["id"],"error":{"code":-32601,"message":"No approvals supported"}})
                if method=="thread/tokenUsage/updated":
                    updates+=1
                    latest[p.get("threadId")]=(p.get("tokenUsage",{}).get("total") or {}).get("totalTokens")
                if method=="turn/completed" and p.get("threadId") in (root,other):
                    assert p["turn"]["status"]=="completed",p["turn"]["status"]
                    ended.add(p["threadId"])
            time.sleep(.9)
            send("usage",selected=root+"/"+turn,refresh=False)
            events=[]
            end=time.monotonic()+6
            while time.monotonic()<end:
                try: e=inbox.get(timeout=.25);events.append(e)
                except queue.Empty: continue
                if e["type"]=="usage" and e.get("selected")==root+"/"+turn:break
            usage=next(e for e in reversed(events) if e["type"]=="usage")
            logs={}
            for path in (isolated/"sessions").rglob("*.jsonl"):
                with path.open() as stream:
                    meta=json.loads(stream.readline())["payload"]
                    if not meta.get("id"):continue
                    ordinal=meta.get("subagent_history_start_ordinal") or 0
                    stamps=[]; total=None; attrs={}
                    for num,line in enumerate(stream,1):
                        if num<=ordinal:continue
                        r=json.loads(line);body=r["payload"];typ=body.get("type");group=r["type"]
                        if group=="event_msg" and typ in ("task_started","task_complete","token_count"):
                            stamps.append((typ,r["timestamp"]))
                            if typ=="token_count":
                                counts=(body.get("info") or {}).get("total_token_usage") or {}
                                if counts: total=counts.get("total_tokens")
                            if typ=="task_started":attrs=body.get("turn_attribution",{})
                        if group=="response_item" and typ in ("function_call","custom_tool_call"):
                            stamps.append(("tool",r["timestamp"]))
                    logs[meta["id"]]=dict(parent=meta.get("parent_thread_id"),root=attrs.get("root_turn_id"),
                                          rows=stamps,total=total,ordinal=ordinal)
            children=[x for x in logs.values() if x["parent"]==root and x["root"]==turn]
            root_timeline=logs[root]["rows"]
            child_ends=[stamp for c in children for typ,stamp in c["rows"] if typ=="task_complete"]
            root_notice=[e for e in events if e["type"]=="notice" and e.get("state")=="success"]
            expected=(logs[root]["total"] or 0)+sum(c["total"] or 0 for c in children)
            import re
            match=re.search(r"合计 ([0-9,]+) tokens",usage["text"])
            measured=int(match.group(1).replace(",","")) if match else None
            displayed_children=sorted(int(n.replace(",", "")) for n in
                                      re.findall(r"子会话 …[0-9a-f]+ · ([0-9,]+) tokens", usage["text"]))
            expected_children=sorted(c["total"] for c in children)
            report=dict(model="gpt-6.2-sol",effort="ultra",service_tier="priority",
                        completed_root_threads=len(ended),verified_children=len(children),children_finished=len(child_ends),
                        root_executed_tool_after_children=bool(child_ends) and any(k=="tool" and t>max(child_ends) for k,t in root_timeline),
                        child_success_notices=sum(e.get("thread") not in (root,other) for e in root_notice),
                        root_success_notices=sum(e.get("thread")==root for e in root_notice),
                        independent_success_notices=sum(e.get("thread")==other for e in root_notice),
                        selectable_root_turns=len(usage["options"]),official_token_updates=updates,
                        inherited_records_skipped=sum(c["ordinal"] for c in children),
                        expected_family_tokens=expected,actual_family_tokens=measured,
                        main_turn_tokens=logs[root]["total"], child_turn_tokens=displayed_children,
                        child_breakdown_matches_source=displayed_children==expected_children,
                        root_thread_usage_matches_official=latest.get(root)==logs[root]["total"])
            args.output.write_text(json.dumps(report,indent=2)+"\n")
            print(json.dumps(report),flush=True)
            assert (len(ended)==2 and len(children)==len(child_ends)==2 and
                    report["root_executed_tool_after_children"] and report["child_success_notices"]==0 and
                    report["root_success_notices"]==report["independent_success_notices"]==1 and
                    report["selectable_root_turns"]==2 and expected==measured and expected>0 and
                    report["root_thread_usage_matches_official"] and report["child_breakdown_matches_source"])
        finally:
            rpc.close()
            broker.stdin.close()
            broker.wait(timeout=8)
            broker.stdout.close()

if __name__=="__main__":
    main()
