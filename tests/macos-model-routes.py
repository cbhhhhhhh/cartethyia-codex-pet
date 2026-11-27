"""Opt-in chat integration; test a local model, local HTTP provider, and an existing Codex login.

Only synthetic prompts use the account. No secrets, personal chats or session identifiers
are written to the report. Use --account explicitly on a Mac with the local model installed.
"""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import queue
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument("--account",action="store_true",required=True)
parser.add_argument("--output",type=Path,required=True)
args=parser.parse_args()
class Provider(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def do_POST(self):
        m=json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        assert m["model"]=="fixture"
        self.send_response(200);self.send_header("Content-Type","text/event-stream");self.end_headers()
        phrases=['{"text":"我陪着你','，慢慢来。","action":"waving","emotion":"happy"}']
        for part in phrases:
            if self.server.slow:time.sleep(.45)
            try:
                self.wfile.write(b"data: "+json.dumps({"choices":[{"delta":{"content":part}}]}).encode()+b"\n\n");self.wfile.flush()
            except (BrokenPipeError,ConnectionResetError):return
        try:self.wfile.write(b'data: {"choices":[],"usage":{"total_tokens":32}}\n\ndata: [DONE]\n\n')
        except (BrokenPipeError,ConnectionResetError):pass

with tempfile.TemporaryDirectory(prefix="pet-model-",dir="/tmp") as tmp:
    scratch=Path(tmp);base=scratch/"pet";home=scratch/"codex";base.mkdir();home.mkdir()
    real=Path(os.environ.get("CODEX_HOME",Path.home()/".codex"))
    for name in ("auth.json","models_cache.json"):
        if (real/name).exists():
            shutil.copyfile(real/name,home/name);(home/name).chmod(0o600)
    (home/"config.toml").write_text('model="gpt-6.2-sol"\n[features]\nplugins=false\napps=false\n')
    (base/"runtime").symlink_to(Path.home()/"Library/Application Support/CodexPetPlus/runtime",target_is_directory=True)
    env=dict(os.environ,PET_PLUS_HOME=str(base),CODEX_HOME=str(home))
    broker=subprocess.Popen([sys.executable,"-B","-u",str(ROOT/"src/broker.py"),"main"],env=env,
                            stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
    events=queue.Queue()
    def read():
        for line in broker.stdout:events.put(json.loads(line))
    threading.Thread(target=read,daemon=True).start()
    def send(op,**kw):
        broker.stdin.write(json.dumps(dict(op=op,**kw))+"\n");broker.stdin.flush()
    def until(test,seconds=75):
        deadline=time.monotonic()+seconds;seen=[]
        while time.monotonic()<deadline:
            try:e=events.get(timeout=max(.01,deadline-time.monotonic()))
            except queue.Empty:break
            seen.append(e)
            if e["type"]=="failure":raise RuntimeError(e["text"])
            if test(e):return e,seen
        raise TimeoutError("Did not receive expected event")
    def kind(name):return lambda e:e["type"]==name
    fixture=ThreadingHTTPServer(("127.0.0.1",0),Provider);fixture.slow=False
    threading.Thread(target=fixture.serve_forever,daemon=True).start()
    tg=str(uuid.uuid4());tr=str(uuid.uuid4())
    hook=socket.socket(socket.AF_UNIX,socket.SOCK_DGRAM)
    def work_event(op):
        hook.sendto(json.dumps(dict(v=1,token=(base/"token").read_text(),source="hook",kind=op,thread=tg,turn=tr,
                                    call="work",tool="synthetic")).encode(),str(base/"events.sock"))
    result={}
    try:
        until(kind("history"));work_event("tool");until(lambda e:e["type"]=="status" and e["state"]=="working")
        cfg=dict(pack="cartethyia",chat=True,whispers=False,model="qwen2.5-1.5b-instruct-q4_k_m.gguf",
                 apiURL=f"http://127.0.0.1:{fixture.server_port}/v1",apiModel="fixture",rounds=2,
                 replyArt=False,persona="你叫纸船。不要出现地名和天气。")
        for route in ("local","api","codex"):
            send("config",config=dict(cfg,chatSource=route,whisperSource="inherit"))
            send("chat",text="不要重复这个问题。北京的天气怎么样？")
            answer,seen=until(kind("reply"))
            assert answer["route"]==route and answer["text"].strip() and not answer["picture"]
            assert not any(x["type"]=="partial" for x in seen)
            assert not any(w in answer["text"] for w in ["北京","上海","天气","下雨","气温"])
            send("whisper",picture="happy-1")
            card,_=until(kind("whisper"))
            assert card["route"]==route and card["picture"]=="happy-1" and card["text"].strip()
            send("config",config=dict(cfg,chatSource=route,persona="你叫纸船。用中文回答。"))
            fixture.slow=True
            send("chat",text="分十行描述一艘彩色小纸船。尽量写长一点。")
            until(kind("partial"))
            send("cancel")
            send("usage",selected="",refresh=False)
            until(kind("usage"));time.sleep(.8)
            file=base/"profiles/main/history.json";history=json.loads(file.read_text())
            expected=len(result)+1
            assert len(history)==expected,(route,len(history),expected)
            state=json.loads((base/"profiles/main/status.json").read_text())
            assert state["state"]=="working"
            result[route]=dict(guarded_reply=True,text_only=True,protected_stream=True,
                               chosen_picture_retained=True,interrupt_after_visible_delta=True,
                               cancelled_turn_excluded_from_history=True,work_continued=True)
            fixture.slow=False
        send("usage",selected="",refresh=False)
        usage,_=until(lambda e:e["type"]=="usage" and all("桌宠自身 · "+r in e["text"] for r in result))
        assert not usage["options"]
        result["companion_calls_separate"]=True
        args.output.write_text(json.dumps(result,indent=2)+"\n")
        print(json.dumps(result))
    finally:
        fixture.shutdown();fixture.server_close();hook.close()
        broker.stdin.close();broker.wait(timeout=9);broker.stdout.close()
