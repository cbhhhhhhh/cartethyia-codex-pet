"""Sample one installed GUI process by identity and optionally probe the real Codex account."""
import argparse
import datetime
import hashlib
import json
import os
import statistics
import subprocess
import sys
import threading
import time
from pathlib import Path
import psutil

parser=argparse.ArgumentParser()
parser.add_argument("pid",type=int)
parser.add_argument("directory",type=Path)
parser.add_argument("--seconds",type=int,default=3600)
parser.add_argument("--installer",type=Path)
parser.add_argument("--probes",action="store_true")
args=parser.parse_args()
args.directory.mkdir(parents=True,exist_ok=True)
target=psutil.Process(args.pid)
born=target.create_time()
binary=Path(target.exe())
installed=binary.parent.parent
assert binary.name.lower()=="pythonw.exe" and (installed/"Cartethyia.exe").is_file()
assert any(Path(v).name.lower()=="app.py" for v in target.cmdline())
def sha(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f,"sha256").hexdigest()
digest=sha(args.installer) if args.installer else None
samples=[]
issues=[]
probes=[]
threads=[]
profile=Path(os.environ["LOCALAPPDATA"])/"CartethyiaPet/profiles/main/status.json"
def check(minute):
    at=time.monotonic()
    cmd=[sys.executable,"-X","utf8","-B",str(Path(__file__).with_name("qa_probe.py")),str(installed)]
    try:
        job=subprocess.run(cmd,capture_output=True,timeout=125,creationflags=subprocess.CREATE_NO_WINDOW)
        ok=job.returncode==0
    except (OSError,subprocess.TimeoutExpired):
        ok=False
    probes.append(dict(minute=minute,elapsed_s=round(at-start,2),latency_s=round(time.monotonic()-at,2),ok=ok))
    (args.directory/"probes.json").write_text(json.dumps(sorted(probes,key=lambda x:x["minute"]),indent=2),encoding="utf8")
def stats(p):
    cpu=p.cpu_times()
    return cpu.user+cpu.system,p.memory_info().rss/1048576
start=time.monotonic()
stamp=datetime.datetime.now().astimezone().isoformat(timespec="seconds")
due=[0,15,30,45,60] if args.probes else []
try:
    with (args.directory/"soak-samples.jsonl").open("w",encoding="utf8") as log:
        n=0
        while True:
            elapsed=time.monotonic()-start
            if not target.is_running() or target.create_time()!=born:
                raise RuntimeError("original GUI exited")
            cpu,rss=stats(target)
            children=[]
            for child in target.children(recursive=True):
                try:
                    ct,mem=stats(child)
                    children.append(dict(pid=child.pid,name=child.name(),rss_mib=round(mem,2),cpu_seconds=ct))
                except (psutil.AccessDenied,psutil.NoSuchProcess):
                    continue
            try:
                status=json.loads(profile.read_bytes())
            except (OSError,ValueError):
                status={}
            row=dict(elapsed=round(elapsed,3),pid=target.pid,cpu_seconds=cpu,rss_mib=round(rss,2),children=children,
                     state=status.get("state","unknown"),heartbeat_age_s=round(time.time()-status.get("updated",time.time()),2))
            samples.append(row)
            log.write(json.dumps(row)+"\n")
            log.flush()
            while due and elapsed>=due[0]*60:
                t=threading.Thread(target=check,args=(due.pop(0),))
                t.start()
                threads.append(t)
            if elapsed>=args.seconds: break
            n+=1
            time.sleep(max(0,min(args.seconds,30*n)- (time.monotonic()-start)))
except (OSError,psutil.Error,RuntimeError) as exc:
    issues.append(type(exc).__name__+": "+str(exc))
end=datetime.datetime.now().astimezone().isoformat(timespec="seconds")
for t in threads:t.join()
duration=samples[-1]["elapsed"]
rates=[(b["cpu_seconds"]-a["cpu_seconds"])*100/(b["elapsed"]-a["elapsed"])
       for a,b in zip(samples,samples[1:]) if b["elapsed"]>a["elapsed"]]
idle=[r for r,(a,b) in zip(rates,zip(samples,samples[1:])) if a["state"]==b["state"]=="idle"]
summary=dict(start=stamp,end=end,pid=target.pid,created=datetime.datetime.fromtimestamp(born).astimezone().isoformat(),
             gui_image="runtime/pythonw.exe",gui_sha256=sha(binary),installer_sha256=digest,
             monitored_seconds=duration,samples=len(samples),exceptions=issues,
             gui_cpu_percent_one_core=round((samples[-1]["cpu_seconds"]-samples[0]["cpu_seconds"])*100/max(duration,.001),3),
             gui_cpu_interval_peak_percent=round(max(rates,default=0),3),
             idle_intervals=len(idle),idle_cpu_percent=round(statistics.mean(idle),3) if idle else None,
             gui_rss_peak_mib=max(r["rss_mib"] for r in samples),gui_rss_median_mib=statistics.median(r["rss_mib"] for r in samples),
             gui_rss_initial_mib=samples[0]["rss_mib"],gui_rss_final_mib=samples[-1]["rss_mib"],
             gui_rss_change_mib=round(samples[-1]["rss_mib"]-samples[0]["rss_mib"],2),
             process_tree_rss_sampled_peak_mib=max(r["rss_mib"]+sum(c["rss_mib"] for c in r["children"]) for r in samples),
             probes=sorted(probes,key=lambda x:x["minute"]))
(args.directory/"soak-summary.json").write_text(json.dumps(summary,indent=2,ensure_ascii=False),encoding="utf8")
print(json.dumps(summary))
if issues or duration<args.seconds or (args.probes and not (len(probes)==5 and all(p["ok"] for p in probes))):
    sys.exit(1)
