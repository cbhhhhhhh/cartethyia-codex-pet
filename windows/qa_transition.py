"""Measure actual paints from the installed pet during real app-server tasks.
The observer selects the test thread so other simultaneously active Codex work cannot mask it."""
import datetime
import json
import os
from pathlib import Path
import subprocess
import sys
import time

repo=Path(__file__).resolve().parents[1]
install=Path(os.environ.get("CARTETHYIA_QA_INSTALL") or Path(os.environ["LOCALAPPDATA"])/"Programs/CartethyiaPet")
sys.path.insert(0,str(install/"windows"))
from common import CODEX
from app import QApplication, Companion, QIcon, QLocalServer, Qt, STYLE
from transport import name

out=Path(os.environ.get("CARTETHYIA_TURN_QA",repo/".build/windows-0.2.0/turns"))
out.mkdir(parents=True,exist_ok=True)
events=out/"events.jsonl"
os.environ["CARTETHYIA_QA_LOG"]=str(events)
app=QApplication([])
app.setStyleSheet(STYLE)
app.setQuitOnLastWindowClosed(False)
app.setWindowIcon(QIcon(str(install/"art/cartethyia.ico")))
profile="windows-acceptance"
server=QLocalServer()
server.setSocketOptions(QLocalServer.UserAccessOption)
assert server.listen(name(profile))
owner=Companion(profile,server)
owner.config["notifications"]=False
owner.pet.show()
owner.pet.move(640,420)
owner.tick.stop()
note=out/"active-thread.txt"
original=owner.work.accept
def only_test(e,*args):
    if note.is_file() and e.get("thread")==note.read_text(encoding="ascii"):
        original(e,*args)
owner.work.accept=only_test
def pump(seconds):
    end=time.monotonic()+seconds
    while time.monotonic()<end:
        app.processEvents()
        time.sleep(.008)
summary={}
try:
    pump(.15)
    for scenario in ("success","interrupt","failure","approval"):
        note.unlink(missing_ok=True)
        report=out/(scenario+".json")
        begin=time.time()
        run=subprocess.Popen([sys.executable,"-B",str(repo/"windows/qa_turns.py"),scenario,str(report),"--thread-note",str(note),"--review-project-hooks"],stdout=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW)
        while run.poll() is None:
            pump(.06)
        if run.returncode:
            raise RuntimeError(scenario+" verification failed")
        pump(1.0)
        r=json.loads(report.read_bytes())
        t=r["thread"]
        log=next((CODEX/"sessions").rglob("*"+t+".jsonl"))
        stamps={}
        with log.open(encoding="utf8") as f:
            for line in f:
                row=json.loads(line)
                v=row.get("payload",{})
                kind=v.get("type")
                if row.get("type")=="event_msg" and kind in ("task_started","task_complete","turn_aborted","error"):
                    if kind=="task_complete" and v.get("error"):
                        kind="error"
                    stamps[kind]=datetime.datetime.fromisoformat(row["timestamp"].replace("Z","+00:00")).timestamp()
        observed=[e for l in events.read_text(encoding="utf8").splitlines() if (e:=json.loads(l))["at"]>=begin]
        paints=[e for e in observed if "painted" in e]
        terminal={"success":"success","interrupt":"idle","failure":"error","approval":"success"}[scenario]
        onset=next(e["at"] for e in paints if e["painted"]=="thinking")
        ended=next(e["at"] for e in paints if e["painted"]==terminal and e["at"]>onset)
        idle=next(e["at"] for e in paints if e["painted"]=="idle" and e["at"]>=ended)
        end_ref=stamps.get({"interrupt":"turn_aborted","failure":"error"}.get(scenario,"task_complete"),r["finished"])
        result=dict(status=r["status"],onset_ms=round(1000*(onset-stamps["task_started"])),terminal_ms=round(1000*(ended-end_ref)),idle_ms=round(1000*(idle-end_ref)),
                    painted=[e["painted"] for e in paints],hook_events=[e["kind"] for e in observed if e.get("source")=="hook"],
                    end_reference="rollout" if any(k in stamps for k in ("turn_aborted","error","task_complete")) else "app-server")
        if scenario=="approval":
            waiting=next(e["at"] for e in paints if e["painted"]=="waiting-for-approval")
            result["approval_ms"]=round(1000*(waiting-r["approval_at"]))
        summary[scenario]=result
        (out/"summary.json").write_text(json.dumps(summary,indent=2),encoding="utf8")
        print(scenario,result,flush=True)
finally:
    owner.shutdown()
    owner.pet.hide()

