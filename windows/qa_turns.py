"""Exercise real local Codex turns with the public app-server stdio protocol.
The approval probe declines an actual request. Nothing grants tool permissions."""
import argparse
import json
import hashlib
import os
from pathlib import Path
import queue
import shutil
import subprocess
import threading
import time

parser=argparse.ArgumentParser()
parser.add_argument("mode",choices=["hooks","success","interrupt","failure","approval","plan"])
parser.add_argument("report",type=Path)
parser.add_argument("--thread-note",type=Path,help="Write the real thread ID before submitting the acceptance turn.")
parser.add_argument("--review-project-hooks",action="store_true",help="Trust only the seven verified local definitions in this QA process.")
args=parser.parse_args()
diagnostics=args.report.with_suffix(".stderr").open("w",encoding="utf8")
def server(overrides=()):
    return subprocess.Popen([shutil.which("codex.exe"),*overrides,"app-server","--listen","stdio://"],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=diagnostics,encoding="utf8",creationflags=subprocess.CREATE_NO_WINDOW)
proc=server()
messages=queue.Queue()
result={"mode":args.mode,"events":[]}
seq=0

def reader(stream):
    for line in stream:
        try:
            messages.put(json.loads(line))
        except ValueError:
            pass
threading.Thread(target=reader,args=(proc.stdout,),daemon=True).start()


def send(message):
    proc.stdin.write(json.dumps(message)+"\n")
    proc.stdin.flush()


def call(method,params):
    global seq
    seq+=1
    send(dict(id=seq,method=method,params=params))
    return seq


def response(ident):
    until=time.monotonic()+65
    while time.monotonic()<until:
        msg=messages.get(timeout=max(.1,until-time.monotonic()))
        if msg.get("id")==ident and "method" not in msg:
            if "error" in msg:
                raise RuntimeError(msg["error"])
            return msg["result"]
    raise TimeoutError("Codex app-server 请求超时")


def initialize():
    response(call("initialize",{"clientInfo":{"name":"cartethyia_qa","version":"2.2.0"},"capabilities":{"experimentalApi":True}}))
    send({"method":"initialized","params":{}})

try:
    initialize()
    if args.review_project_hooks:
        infos=response(call("hooks/list",{"cwds":[str(Path.cwd())]}))
        selected=[h for x in infos["data"] for h in x["hooks"] if h.get("pluginId")=="pet-plus@cartethyia-windows-local"]
        if len(selected)!=7:
            raise RuntimeError("Unexpected set of project hooks")
        installed=Path(os.environ["LOCALAPPDATA"])/"Programs/CartethyiaPet"
        for f in ("service.py","transport.py","common.py"):
            staged=Path(__file__).resolve().parents[1]/".build/windows-app/windows"/f
            assert (installed/"windows"/f).read_bytes()==staged.read_bytes()
        expected='"'+(installed/"runtime/python.exe").as_posix()+'" -B "'+(installed/"windows/service.py").as_posix()+'" hook'
        def quoted(path):
            return "'"+str(path).replace("'","''")+"'"
        expected_windows="& "+quoted(installed/"runtime/python.exe")+" -B "+quoted(installed/"windows/service.py")+" hook"
        states=[]
        for h in selected:
            source=Path(h["sourcePath"])
            data=json.loads(source.read_bytes())
            hooks=data["hooks"]
            if "hooks" in hooks:
                hooks=hooks["hooks"]
            assert all(e["command"]==expected and e["commandWindows"]==expected_windows and e["type"]=="command" for group in hooks.values() for spec in group for e in spec["hooks"])
            declaration,_,content=h["currentHash"].partition("/")
            states.append(json.dumps(h["key"])+"={trusted_hash="+json.dumps(declaration)+",trusted_content_hash="+json.dumps(content)+"}")
        overrides=["-c","hooks.state={"+",".join(states)+"}"]
        proc.stdin.close()
        proc.wait(timeout=8)
        proc=server(overrides)
        threading.Thread(target=reader,args=(proc.stdout,),daemon=True).start()
        initialize()
        checked=response(call("hooks/list",{"cwds":[str(Path.cwd())]}))
        result["trusted_for_this_process"]=[h["trustStatus"] for x in checked["data"] for h in x["hooks"] if h.get("pluginId")=="pet-plus@cartethyia-windows-local"]
        assert result["trusted_for_this_process"]==["trusted"]*7
    if args.mode=="hooks":
        infos=response(call("hooks/list",{"cwds":[str(Path.cwd())]}))
        result["hooks"]=[{k:h.get(k) for k in ("eventName","enabled","pluginId","trustStatus")} for x in infos["data"] for h in x["hooks"] if "cartethyia-windows-local" in str(h.get("pluginId"))]
    else:
        thread=response(call("thread/start",{"cwd":str(Path.cwd()),"sandbox":"read-only","approvalPolicy":"untrusted" if args.mode=="approval" else "never"}))["thread"]["id"]
        result["thread"]=thread
        if args.thread_note:
            args.thread_note.write_text(thread,encoding="ascii")
        if args.review_project_hooks:
            active=response(call("hooks/list",{"threadId":thread}))
            result["thread_hook_status"]=[(h["eventName"],h["trustStatus"]) for x in active["data"] for h in x["hooks"] if h.get("pluginId")=="pet-plus@cartethyia-windows-local"]
        prompt={"success":"Use PowerShell to run Get-Date. Reply with the day only.",
                "plan":"Use update_plan with two steps: read the date with Get-Date, then report it. Use update_plan again to mark both steps complete.",
                "interrupt":"Use PowerShell to run Start-Sleep -Seconds 8. Then say done.",
                "failure":"Reply with one word.",
                "approval":"Use the shell to calculate a SHA-256 digest of this checkout's existing README.md with Get-FileHash. If approval is declined just stop."}[args.mode]
        turn_params={"threadId":thread,"input":[{"type":"text","text":prompt}]}
        if args.mode=="failure":
            turn_params["model"]="cartethyia-qa-unavailable"
        result["sent"]=time.time()
        turn=response(call("turn/start",turn_params))["turn"]["id"]
        result["turn"]=turn
        until=time.monotonic()+100
        interrupt_at=time.monotonic()+1.5
        interrupted=False
        while time.monotonic()<until:
            if args.mode=="interrupt" and not interrupted and time.monotonic()>interrupt_at:
                result["interrupt_request"]=time.time()
                call("turn/interrupt",{"threadId":thread,"turnId":turn})
                interrupted=True
            try:
                msg=messages.get(timeout=.1)
            except queue.Empty:
                continue
            method=msg.get("method","")
            if method.startswith("hook/"):
                h=msg.get("params",{}).get("run",{})
                result.setdefault("hook_notifications",[]).append([method,h.get("eventName"),h.get("status")])
                if "cartethyia" in str(h).lower():
                    result.setdefault("hook_runs",[]).append({k:h.get(k) for k in ("eventName","status","entries","statusMessage")})
            if method=="item/started" or method=="item/completed":
                result["events"].append([time.time(),method,msg.get("params",{}).get("item",{}).get("type")])
            if method.endswith("requestApproval") and "id" in msg:
                result["approval"]=method
                result["approval_at"]=time.time()
                time.sleep(2)
                reply={"permissions":{},"scope":"turn"} if "permissions" in method.lower() else {"decision":"decline"}
                send(dict(id=msg["id"],result=reply))
            if method=="turn/completed":
                result["finished"]=time.time()
                result["status"]=msg["params"]["turn"]["status"]
                break
        else:
            call("turn/interrupt",{"threadId":thread,"turnId":turn})
            result["status"]="probe-timeout"
finally:
    args.report.write_text(json.dumps(result,indent=2),encoding="utf8")
    proc.stdin.close()
    try:
        proc.wait(timeout=4)
    except subprocess.TimeoutExpired:
        proc.terminate()
print(json.dumps(result))

