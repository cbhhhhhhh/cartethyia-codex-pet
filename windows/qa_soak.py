"""Wall-clock sampling of the installed GUI PID, including its local inference children."""
import argparse
import datetime
import json
import statistics
import time
from pathlib import Path
import psutil

parser=argparse.ArgumentParser()
parser.add_argument("pid",type=int)
parser.add_argument("directory",type=Path)
parser.add_argument("--seconds",type=int,default=3600)
args=parser.parse_args()
args.directory.mkdir(parents=True,exist_ok=True)
target=psutil.Process(args.pid)
born=target.create_time()
start=time.monotonic()
stamp=datetime.datetime.now().astimezone().isoformat(timespec="seconds")
rows=[]
events=[]
def stats(p):
    cpu=p.cpu_times()
    return cpu.user+cpu.system,p.memory_info().rss/1048576
with (args.directory/"soak-samples.jsonl").open("w",encoding="utf8") as log:
    while True:
        elapsed=time.monotonic()-start
        if not target.is_running() or target.create_time()!=born:
            events.append("原 GUI 进程退出")
            break
        cpu,rss=stats(target)
        children=[]
        for c in target.children(recursive=True):
            try:
                ct,mem=stats(c)
                children.append(dict(pid=c.pid,name=c.name(),rss_mib=round(mem,2),cpu_seconds=ct))
            except (psutil.AccessDenied,psutil.NoSuchProcess):
                continue
        row=dict(elapsed=round(elapsed,3),pid=target.pid,cpu_seconds=cpu,rss_mib=round(rss,2),children=children)
        rows.append(row)
        log.write(json.dumps(row)+"\n")
        log.flush()
        if elapsed>=args.seconds:
            break
        time.sleep(min(30,args.seconds-elapsed))
duration=rows[-1]["elapsed"]-rows[0]["elapsed"]
usage=[(b["cpu_seconds"]-a["cpu_seconds"])*100/(b["elapsed"]-a["elapsed"]) for a,b in zip(rows,rows[1:]) if b["elapsed"]>a["elapsed"]]
summary=dict(start=stamp,end=datetime.datetime.now().astimezone().isoformat(timespec="seconds"),pid=target.pid,
             monitored_seconds=duration,samples=len(rows),exceptions=events,gui_cpu_percent_one_core=round((rows[-1]["cpu_seconds"]-rows[0]["cpu_seconds"])*100/max(duration,.001),3),
             gui_cpu_interval_peak_percent=round(max(usage,default=0),2),gui_rss_peak_mib=max(r["rss_mib"] for r in rows),
             gui_rss_median_mib=statistics.median(r["rss_mib"] for r in rows),gui_rss_final_mib=rows[-1]["rss_mib"],
             process_tree_rss_sampled_peak_mib=max(r["rss_mib"]+sum(c["rss_mib"] for c in r["children"]) for r in rows))
(args.directory/"soak-summary.json").write_text(json.dumps(summary,indent=2,ensure_ascii=False),encoding="utf8")
print(json.dumps(summary))

