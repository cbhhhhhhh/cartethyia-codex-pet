import json
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys
import tempfile
import threading
import unittest
import uuid
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from dialogue import Rules, action_request, cue_line, gallery, gallery_pick
from observe import Tail, quota_view
from pet_response import answer, actions
from providers import api_chat, list_models, route
from state import Reducer
from usage import Ledger, money_line

def ident():
    return str(uuid.uuid4())

def totals(n):
    return dict(input_tokens=n-2, cached_input_tokens=2, output_tokens=2,
                reasoning_output_tokens=1, total_tokens=n)

class TurnOwnership(unittest.TestCase):
    def test_fork_boundary_with_restamped_inherited_events(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)
            reader=Tail(folder)
            root, child, parentTurn, ownTurn=ident(),ident(),ident(),ident()
            now=datetime.now(timezone.utc).isoformat(timespec="milliseconds")
            def line(group, **data):
                return json.dumps(dict(timestamp=now,type=group,payload=data))+"\n"
            inherited=[line("event_msg", type="task_started",turn_id=parentTurn),
                       line("event_msg", type="token_count",info=dict(total_token_usage=totals(8000))),
                       line("event_msg", type="task_complete",turn_id=parentTurn)]
            meta=line("session_meta",id=child,timestamp=now,thread_source="subagent",
                      source={"subagent":{"thread_spawn":{"parent_thread_id":root}}},
                      subagent_history_start_ordinal=len(inherited))
            actual=[line("event_msg",type="task_started",turn_id=ownTurn,
                         turn_attribution=dict(root_turn_id=parentTurn,parent_turn_id=parentTurn)),
                    line("turn_context",turn_id=ownTurn),
                    line("event_msg",type="token_count",info=dict(total_token_usage=totals(12),last_token_usage=totals(12))),
                    line("event_msg",type="task_complete",turn_id=ownTurn)]
            p=folder/("rollout-"+child+".jsonl")
            p.write_text(meta+"".join(inherited+actual))
            reader.close()
            reader.began-=1
            reader.add(p,False)
            events=list(reader.poll())
            self.assertEqual([e["kind"] for e in events],["start","usage","end"])
            self.assertTrue(all(e["turn"]==ownTurn and e["root_turn"]==parentTurn and e["role"]=="child" for e in events))
            self.assertEqual(events[1]["total"]["total_tokens"],12)

    def test_unique_root_children_late_sample_and_separate_pet(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger=Ledger(tmp);root,child,foreign,rt,ct,ft=[ident() for _ in range(6)]
            def event(tid,turn,kind,role,**extra):
                ledger.observe(dict(thread=tid,turn=turn,kind=kind,role=role,**extra))
            for tid,turn,role in ((root,rt,"root"),(child,ct,"child"),(foreign,ft,"root")):
                attrs=dict(root_turn=rt,parent_turn=rt,parent_thread=root) if role=="child" else {}
                event(tid,turn,"start",role,**attrs)
            for tid,turn,role,n in ((root,rt,"root",45),(child,ct,"child",12),(foreign,ft,"root",800)):
                for _ in range(2): event(tid,turn,"usage",role,total=totals(n),last=totals(n),stamp=10)
            event(child,ct,"end","child")
            event(root,rt,"usage","root",total=totals(9),last=totals(9),stamp=8)
            ledger.add_pet("codex",250)
            data=ledger.view(root+"/"+rt)
            self.assertIn("合计 57 tokens",data["text"])
            self.assertIn("本轮主会话 · 45 tokens", data["text"])
            self.assertIn("子会话 …" + child[-6:] + " · 12 tokens", data["text"])
            self.assertNotIn("800 tokens", data["text"])
            self.assertIn("本次请求 · 进行中",data["text"])
            self.assertIn("桌宠自身 · codex · 1 次 · 250 tokens",data["text"])
            self.assertEqual(len(data["options"]),2)
            ledger.flush(True)
            self.assertIn("合计 57",Ledger(tmp).view(root+"/"+rt)["text"])

    def test_total_only_event_and_true_zero_are_distinct(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Ledger(tmp)
            root, turn = ident(), ident()
            who = dict(thread=root, turn=turn, role="root")
            ledger.observe(dict(who, kind="start"))
            usage = dict(total_tokens=41, output_tokens=0)
            ledger.observe(dict(who, kind="usage", total=usage, last=usage))
            ledger.flush(True)
            text = Ledger(tmp).view()["text"]
            self.assertIn("合计 41 tokens", text)
            self.assertIn("输入 未提供（含缓存 未提供）", text)
            self.assertIn("输出 0（含推理 未提供）", text)

    def test_real_window_units_and_missing_cost(self):
        q=quota_view({"rateLimits":{"secondary":{"windowDurationMins":10080,"usedPercent":23},"primary":{"windowDurationMins":300,"usedPercent":6}}},0)
        self.assertIn("7 天额度 · 剩余 77%（已用 23%）",q["text"])
        self.assertIn("5 小时额度",q["text"])
        self.assertIn("$0.000005",money_line({"estimatedUsageUsdMicros":5},"估算"))
        self.assertIn("暂未提供",money_line({"estimatedUsageUsdMicros":None},"估算"))
        self.assertIn("$0",money_line({"nativeUsageUsdMicros":0},"估算"))

    def test_parallel_completion_keeps_other_root_working(self):
        r=Reducer();a,b,one,two=[ident() for _ in range(4)]
        for t,v,k in ((a,one,"start"),(b,two,"start"),(a,one,"tool"),(a,one,"plan"),(b,two,"end")):
            r.event(dict(v=1,thread=t,turn=v,kind=k,progress="1/1",complete=True),12)
        self.assertEqual(r.snapshot(12)["state"],"working")
        self.assertEqual(r.notice,("success",b))
        r.notice=None;r.event(dict(v=1,thread=b,turn=two,kind="end"),13)
        self.assertIsNone(r.notice)

class SpeechAndGallery(unittest.TestCase):
    def test_all_paths_guard_partial_archive_and_cues(self):
        cfg=dict(persona="你叫小卡。不要出现地名以及天气。",model="local",localTime=False,replyArt=True)
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)
            for mode in ("chat","manual","auto","dream"):
                observations=[];published=[]
                def generate(base,model,persona,memory,prompt,cancel,callback,**kw):
                    observations.append((persona,memory,prompt));callback("上海");return dict(text="上海有雨。",emotion="happy",action="waving",usageTokens=8)
                with patch("pet_response.generate",side_effect=generate):
                    got=answer(folder,folder,cfg,[dict(user="去北京吗",assistant="巴黎下雨")],
                               "北京天气好吗",mode!="chat",mode,None,"","","",threading.Event(),published.append,"气温 28℃")
                self.assertFalse(published);self.assertTrue(Rules(cfg).allows(got["text"]))
                self.assertEqual(got["reported"],[8,8]);self.assertFalse(observations[0][1])
                self.assertNotIn("北京",observations[0][2]);self.assertNotIn("28℃",observations[0][2])
            self.assertFalse(cue_line("未收录",Rules(cfg)))
            self.assertFalse(gallery_pick(gallery(folder),"普通你好","happy","","",True,False,Rules(cfg)))
            forced=gallery_pick(gallery(folder),"","calm","","happy-1",False,True,Rules(cfg))
            self.assertEqual(forced["title"],"送你一颗心")
            self.assertNotEqual(gallery_pick(gallery(folder),"换一张","happy","happy-1","",True,False,Rules(cfg))["id"],"happy-1")

    def test_action_resolution_and_models(self):
        self.assertEqual(len(actions()),109)
        for word,name in (("写字","写下旅途一笔"),("给我行个礼","提裙行骑士礼"),("拆礼物","拆开丝带礼物")):
            self.assertEqual(action_request(word,actions()),name)
            self.assertEqual(action_request("再来一次",actions(),name),name)
        self.assertEqual(route({"model":"m","whisperModel":"w"},True),("local","w"))
        self.assertEqual(route({"chatSource":"codex","codexModel":"c","whisperSource":"inherit"},True),("codex","c"))
        self.assertEqual(route({"chatSource":"local","whisperSource":"api","whisperApiModel":"w"},True),("api","w"))

    def test_compatible_api_real_http_stream(self):
        class Fixture(BaseHTTPRequestHandler):
            def log_message(self,*args): pass
            def do_GET(self):
                self.send_response(200);self.end_headers();self.wfile.write(b'{"data":[{"id":"fixture"}]}')
            def do_POST(self):
                data=json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                self.server.request_data=data
                self.send_response(200);self.send_header("Content-Type","text/event-stream");self.end_headers()
                for fragment in ('{"text":"Hello',' there","action":"waving","emotion":"happy"}'):
                    self.wfile.write(b"data: "+json.dumps({"choices":[{"delta":{"content":fragment}}]}).encode()+b"\n\n")
                self.wfile.write(b'data: {"usage":{"total_tokens":19},"choices":[]}\n\ndata: [DONE]\n\n')
        http=ThreadingHTTPServer(("127.0.0.1",0),Fixture)
        th=threading.Thread(target=http.serve_forever,daemon=True);th.start()
        try:
            cfg={"apiURL":"http://127.0.0.1:%s/v1"%http.server_port}
            self.assertEqual(list_models("api",cfg),["fixture"])
            out=[];reply=api_chat(cfg,"fixture",[dict(role="user",content="hello")],threading.Event(),out.append)
            self.assertEqual(reply["usageTokens"],19);self.assertEqual(reply["text"],"Hello there")
            self.assertTrue(out);self.assertTrue(http.request_data["stream"])
        finally:
            http.shutdown();http.server_close()
