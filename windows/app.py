import argparse
import ctypes
import datetime
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import random
import re
import subprocess
import sys
import threading
import time
from common import DATA, ROOT, read, write
from PySide6.QtCore import QAbstractNativeEventFilter, QLockFile, QObject, QPoint, QSize, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QAction, QCursor, QDesktopServices, QIcon
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from shiboken6 import isValid
from PySide6.QtWidgets import (QApplication,QDialog,QInputDialog,QLabel,QMenu,QMessageBox,QSystemTrayIcon,
                               QTextEdit,QVBoxLayout,QLineEdit)
import archive
from dialogue import Rules, gallery, cue_line
from pet_response import answer as generate_answer
from providers import list_models, route
import reminders
from cards import Card, LABELS, Settings, STYLE, Tasks, button
from core import Work
from model_store import install, PROJECTOR, RUNTIME, VISION
from pet import FLAGS, Pet, ROWS
from state import VALID_ID, allow_whisper
from transport import name, send
from weather import Weather


class Hotkeys(QAbstractNativeEventFilter):
    def __init__(self,owner):
        super().__init__()
        self.owner=owner
        self.hwnd=int(owner.pet.winId())
        self.keys=[]
        self.user=ctypes.windll.user32
        self.bind()

    def bind(self):
        self.clear()
        bindings=[(1,3,self.owner.config["shortcut"])]
        if self.owner.profile=="main":
            bindings.extend([(2,7,"M"),(3,7,"Q")])
        for idx,mods,key in bindings:
            if len(key)==1 and self.user.RegisterHotKey(self.hwnd,idx,mods|0x4000,ord(key)):
                self.keys.append(idx)
            elif idx==1:
                self.owner.tray.showMessage("卡提希娅","唤醒快捷键已被占用，可在设置里换键。")

    def clear(self):
        for idx in self.keys:
            self.user.UnregisterHotKey(self.hwnd,idx)
        self.keys.clear()

    def nativeEventFilter(self,event_type,message):
        from ctypes.wintypes import MSG
        msg=MSG.from_address(int(message))
        if msg.message==0x312 and msg.wParam in self.keys:
            action={1:self.owner.toggle,2:self.owner.mute,3:QApplication.quit}[msg.wParam]
            QTimer.singleShot(0,action)
            return True,0
        return False,0


class Companion(QObject):
    stream=Signal(int,str)
    finished=Signal(int,object,str)
    progress=Signal(str)
    modelDone=Signal()
    registered=Signal()
    modelList=Signal(str,object,str)
    def __init__(self,profile,server):
        super().__init__()
        self.profile=profile
        self.folder=DATA/"profiles"/profile
        self.folder.mkdir(parents=True,exist_ok=True)
        self.cfgfile=self.folder/"config.json"
        defaults=read(ROOT/"examples/config.json",{})
        self.config={**defaults,"vision":VISION,"projector":PROJECTOR,"backend":"auto",**read(self.cfgfile,{})}
        self.config["mapping"]={**defaults["mapping"],**self.config["mapping"]}
        self.history=archive.normalize(read(self.folder/"history.json",[]))
        self.pet=Pet(self.config)
        if not self.cfgfile.exists():
            area=self.pet.bounds()
            self.pet.move(area.right()-self.pet.width()-36,area.bottom()-self.pet.height()-44)
        self.server=server
        self.sockets=set()
        self.server.newConnection.connect(self.connections)
        self.cancel=None
        self.worker=None
        self.serial=0
        self.partial=""
        self.last_action=""
        self.last_thread=""
        self.settings=None
        self.tasks=None
        self.logwindow=None
        self.downloading=False
        self.weather=Weather()
        self.last_whisper=time.monotonic()
        self.card=Card(self)
        self.interaction=read(self.folder/"interaction.json",{})
        self.last_cue=0
        self.next_action=time.monotonic()+random.uniform(25,55)
        self.notices=[]
        self.notice_key=None
        self.usage_key=""
        self.modelList.connect(self.models_loaded)
        self.pet.positioned.connect(self.position_cards)
        self.pet.settled.connect(self.save_position)
        self.pet.clicked.connect(self.compose)
        self.pet.menuAt.connect(self.menu)
        self.tray=QSystemTrayIcon(QApplication.windowIcon(),self)
        self.tray.setToolTip("卡提希娅 · "+profile)
        self.tray.activated.connect(lambda reason:self.open_settings() if reason==QSystemTrayIcon.DoubleClick else None)
        self.traymenu=QMenu()
        self.traymenu.aboutToShow.connect(lambda:self.fill_menu(self.traymenu))
        self.tray.setContextMenu(self.traymenu)
        self.tray.show()
        self.work=Work(self.folder)
        if self.work.audit:
            self.pet.painted.connect(lambda state:self.work.record(dict(painted=state,thread=self.work.last.get("thread",""))))
        self.work.track_cost=bool(self.config["trackCost"])
        self.work.started.connect(self.turn_started)
        self.work.usageChanged.connect(self.refresh_usage)
        self.work.quotaChanged.connect(lambda text:self.card.display("quota",text) if self.card.mode=="quota" else None)
        self.work.changed.connect(self.state)
        self.work.notice.connect(self.notice)
        self.keys=Hotkeys(self)
        QApplication.instance().installNativeEventFilter(self.keys)
        self.stream.connect(self.delta)
        self.finished.connect(self.answer)
        self.progress.connect(lambda text:self.settings.download.setText(text) if self.settings else None)
        self.modelDone.connect(lambda:setattr(self,"downloading",False))
        self.registered.connect(self.open_settings)
        self.tick=QTimer(self,interval=2000)
        self.tick.timeout.connect(self.periodic)
        self.tick.start()
        self.notice_timer=QTimer(self,singleShot=True,interval=5500)
        self.notice_timer.timeout.connect(self.end_notice)
        if not self.config["asleep"]:
            self.pet.show()
        QApplication.instance().aboutToQuit.connect(self.shutdown)

    def connections(self):
        while self.server.hasPendingConnections():
            sock=self.server.nextPendingConnection()
            self.sockets.add(sock)
            sock.setReadBufferSize(8192)
            sock.readyRead.connect(lambda s=sock:self.receive(s))
            sock.disconnected.connect(lambda s=sock:self.disconnected(s))
            self.receive(sock)

    def disconnected(self,sock):
        self.sockets.discard(sock)
        if isValid(sock):
            self.receive(sock)
            sock.deleteLater()

    def receive(self,sock):
        while sock.canReadLine():
            try:
                msg=json.loads(bytes(sock.readLine(8192)))
                cmd=msg.get("command")
                if cmd=="settings":
                    self.open_settings()
                elif cmd=="quit":
                    QApplication.quit()
                elif msg.get("source")=="hook":
                    self.work.accept(msg)
            except (ValueError,TypeError,AttributeError):
                pass

    def state(self,status):
        if self.pet.state!=status["state"] and status["state"]!="idle":
            self.pet.action=""
            self.pet.travel=None
            self.pet.frame.setInterval(125)
        self.pet.state=status["state"]
        self.pet.update()
        if self.card.mode == "work":
            self.work_details()

    def work_details(self):
        s=self.work.last
        seconds=max(0,int(time.monotonic()-s["since"])) if s.get("since") else 0
        self.card.display("work",f"{LABELS.get(s.get('state'),'待机')} · {seconds} 秒\n工具　{s.get('tool') or '—'}\n计划　{s.get('progress') or '—'}")

    def position_cards(self):
        if self.card.isVisible():
            self.card.layout_at_pet()

    def turn_started(self,thread,turn):
        self.notices=[n for n in self.notices if n[1]!=thread or n[2]==turn]
        if self.card.mode=="notice" and self.notice_key and self.notice_key[0]==thread and self.notice_key[1]!=turn:
            self.end_notice()

    def notice(self,kind,thread,turn):
        if not self.config["notifications"] or self.config["muted"]:
            return
        if kind=="waiting-for-approval":
            self.notices=[n for n in self.notices if n[1:3]!=(thread,turn)]
        else:
            self.notices=[n for n in self.notices if n[:3]!=("waiting-for-approval",thread,turn)]
        self.notices.append((kind,thread,turn,time.monotonic()+30))
        self.present_notice()

    def end_notice(self):
        if self.card.mode=="notice":
            self.card.close_card()
        self.notice_key=None
        self.present_notice()

    def present_notice(self):
        if self.card.mode not in ("","cue") or self.config["muted"]:
            return
        texts={"success":"任务完成了。","error":"这次任务遇到了问题。","waiting-for-approval":"Codex 正在等待你的审批。","timeout":"暂时没有新的工作信号。"}
        while self.notices:
            kind,thread,turn,expires=self.notices.pop(0)
            if time.monotonic()>expires or self.work.active.get(thread)!=turn:
                continue
            if kind=="waiting-for-approval" and (thread,turn) in self.work.reducer.closed:
                continue
            self.notice_key=(thread,turn)
            self.notify(texts[kind],thread,"voiceNotice")
            self.work.record(dict(bubble=kind,thread=thread,turn=turn))
            break

    def notify(self,text,thread,voice):
        if self.config["muted"]:
            return
        self.last_thread=thread
        if self.pet.isVisible() and self.card.mode not in ("input","stream","reply"):
            self.card.display("notice",text)
            self.notice_timer.start()
        else:
            self.tray.showMessage("卡提希娅",text)
        if self.config.get(voice):
            self.speak(text)

    def speak(self,text):
        if self.config["muted"] or not Rules(self.config).allows(text):
            return
        script="[Console]::InputEncoding=[Text.Encoding]::UTF8; $v=New-Object -ComObject SAPI.SpVoice; [void]$v.Speak([Console]::In.ReadToEnd(),16)"
        def run():
            try:
                subprocess.run(["powershell.exe","-NoProfile","-Command",script],input=text.encode(),creationflags=subprocess.CREATE_NO_WINDOW,timeout=90)
            except (OSError,subprocess.TimeoutExpired):
                logging.exception("Windows speech service")
        threading.Thread(target=run,daemon=True).start()

    def periodic(self):
        self.present_notice()
        if self.card.mode=="work":
            self.work_details()
        for item in reminders.pending(DATA if self.profile=="main" else self.folder):
            self.notify(item["text"],item["thread"],"voiceTodo")
        cfg=self.config
        if allow_whisper(time.monotonic(),self.last_whisper,cfg["minutes"],datetime.datetime.now().hour,cfg["quietStart"],cfg["quietEnd"],
                         cfg["whispers"],cfg["muted"],cfg["focus"] or self.pet.state!="idle" or not self.pet.isVisible() or self.card.isVisible()):
            self.last_whisper=time.monotonic()
            source,model=route(cfg,True)
            if source!="local" or (RUNTIME/model).is_file():
                self.chat("",None,True,mode="dream" if cfg["dreams"] and random.random()<.22 else "whisper")
            else:
                self.notify(Rules(cfg).safe_line(), None, "voiceWhisper")
        if time.monotonic()>=self.next_action:
            self.next_action=time.monotonic()+random.uniform(25,55)
            if cfg.get("randomActions") and self.pet.isVisible() and self.pet.state=="idle" and self.pet.drag is None and not self.card.isVisible():
                idle=[k for k in self.pet.idle_clips if k in self.pet.clips]
                if idle:
                    self.pet.play(random.choice(idle))

    def compose(self):
        self.card.compose()

    def chat(self,prompt,image,whisper=False,picture="",mode=""):
        self.cancel_chat(visible=False)
        self.serial+=1
        ident=self.serial
        cancel=self.cancel=threading.Event()
        cfg=dict(self.config)
        history=archive.context(self.history,cfg["rounds"])
        previous=dict(self.interaction)
        self.pending=(prompt,image,whisper,picture)
        self.partial=""
        self.card.display("stream","正在思考…","focused")
        def run():
            try:
                rules=Rules(cfg)
                weather=self.weather.current(cfg["weatherCity"]) if cfg["weatherEnabled"] and not (rules.weather or rules.places) else ""
                result=generate_answer(DATA,self.folder,cfg,history,prompt,whisper,mode,image,picture,
                    previous.get("clip",""),previous.get("picture",""),cancel,lambda text:self.stream.emit(ident,text),
                    retrieved_weather=weather,last_kind=previous.get("kind",""),recent_picture=previous.get("recent",""),
                    audit=lambda phase,source,tokens:self.work.petMeter.emit(phase,("碎碎念" if whisper else "聊天")+" · "+source,tokens))
                self.finished.emit(ident,result,"")
            except Exception as exc:
                self.finished.emit(ident,None,str(exc))
        self.worker=threading.Thread(target=run,daemon=True)
        self.worker.start()

    def delta(self,ident,text):
        if ident==self.serial and Rules(self.config).allows(text):
            self.partial=text
            if self.card.isVisible():
                self.card.display("stream",text,"focused",False)

    def answer(self,ident,result,error):
        if ident!=self.serial:
            return
        self.cancel=None
        if not result:
            if error:
                message=error+"。可在设置的模型线路中检查连接。"
                self.card.display("reply",message if Rules(self.config).allows(message) else "模型连接暂时不可用。","sad")
            return
        prompt,image,whisper,forced=self.pending
        rules=Rules(self.config)
        if not rules.allows(result["text"]):
            result.update(text=rules.safe_line(),action="idle",emotion="calm")
        picture=result.get("picture","")
        clip=result.get("clip","")
        if not whisper:
            record=dict(user=prompt,assistant=result["text"],emotion=result["emotion"],action=result["action"],
                        clip=clip,picture=picture,time=time.time())
            if image:
                record["image"]=archive.keep_image(self.folder,image)
            self.history.extend(archive.normalize([record]))
            self.save_history()
        if clip:
            self.perform(clip,False)
        else:
            self.pet.play(result["action"])
        if picture:
            self.interaction.update(picture=picture,kind="picture")
        self.interaction["recent"]=picture
        write(self.folder/"interaction.json",self.interaction)
        if self.card.isVisible():
            self.card.display("reply",result["text"],result["emotion"],art=next(iter(result.get("art",[])),None))
        if self.config.get("voiceWhisper" if whisper else "voiceChat"):
            self.speak(result["text"])
        if whisper and not forced:
            QTimer.singleShot(6500,lambda:self.card.close_card() if self.serial==ident and self.card.mode=="reply" else None)

    def perform(self,title,with_cue=True):
        self.pet.play(title)
        self.interaction.update(clip=title,kind="action")
        write(self.folder/"interaction.json",self.interaction)
        started=self.pet.started
        def cue():
            if self.pet.started!=started or self.config["muted"] or self.card.mode not in ("","cue") or self.pet.state!="idle":
                return
            line=cue_line(title, Rules(self.config))
            if line and time.monotonic()-self.last_cue>=6:
                self.last_cue=time.monotonic()
                self.card.display("cue",line)
                if self.config.get("voiceWhisper"):
                    self.speak(line)
                QTimer.singleShot(2700,lambda:self.card.close_card() if self.card.mode=="cue" else None)
        if with_cue:
            QTimer.singleShot(660,cue)

    def cancel_chat(self,visible=True):
        if self.cancel is not None:
            self.cancel.set()
            self.cancel=None
            self.serial+=1
            if visible:
                self.card.display("reply","已中断。")

    def save_history(self):
        write(self.folder/"history.json",self.history)
        write(self.folder/"memory.json",archive.context(self.history,self.config["rounds"]))
        if self.logwindow:
            self.history_text.setPlainText("\n\n".join("我　"+r["user"]+"\n卡提　"+r["assistant"] for r in self.history))

    def history_window(self):
        if not self.logwindow:
            self.logwindow=QDialog()
            self.logwindow.setWindowTitle("卡提希娅 · 聊天记录")
            self.logwindow.resize(460,440)
            box=QVBoxLayout(self.logwindow)
            self.history_text=QTextEdit(readOnly=True)
            box.addWidget(self.history_text)
            box.addWidget(button("清空聊天与记忆",self.clear))
        self.save_history()
        self.logwindow.show()
        self.logwindow.raise_()

    def clear(self):
        if QMessageBox.question(self.logwindow,"清空聊天","清空当前档案的聊天、图片和记忆？")==QMessageBox.Yes:
            self.cancel_chat(False)
            self.card.close_card()
            for item in self.history:
                p=Path(item.get("image","")).resolve()
                if p.parent==(self.folder/"images").resolve():
                    p.unlink(missing_ok=True)
            self.history=[]
            self.interaction={}
            write(self.folder/"interaction.json",{})
            self.save_history()

    def menu(self,pos):
        menu=QMenu()
        self.fill_menu(menu)
        menu.exec(pos)

    def fill_menu(self,menu):
        menu.clear()
        actions=menu.addMenu("点播动作")
        for r in ROWS:
            actions.addAction(r,lambda checked=False,r=r:self.pet.play(r))
        groups={}
        for key,spec in self.pet.clips.items():
            group=spec.get("group","角色包")
            if group not in groups:
                groups[group]=actions.addMenu(group)
            groups[group].addAction(key,lambda checked=False,k=key:self.perform(k))
        pictures=menu.addMenu("配图")
        for pic in gallery(self.folder,self.config["pack"]).values():
            pictures.addAction(QIcon(pic["file"]),pic["title"],lambda checked=False,k=pic["id"]:self.chat("",None,True,picture=k))
        for title,fn in [("工作详情",self.work_details),("当前任务用量",self.show_usage),("待办事项",self.todos),("聊天记录",self.history_window),("账户额度",self.show_quota),("设置",self.open_settings)]:
            menu.addAction(title,fn)
        menu.addSeparator()
        for title,fn in [("收起" if self.pet.isVisible() else "唤醒",self.toggle),("取消静音" if self.config["muted"] else "静音",self.mute),("退出",QApplication.quit)]:
            menu.addAction(title,fn)

    def jump(self,thread):
        if thread and VALID_ID.fullmatch(thread):
            QDesktopServices.openUrl(QUrl("codex://threads/"+thread))

    def show_quota(self):
        self.card.display("quota",self.work.quota or "正在读取 Codex 账户额度…")
        self.work.official("quota")

    def show_usage(self):
        self.card.display("usage","")
        self.refresh_usage()
        if self.usage_key:
            self.work.official("billing",self.usage_key.split("/")[0])

    def usage_selection(self,key):
        if key:
            self.usage_key=key
            self.refresh_usage()

    def refresh_usage(self):
        if self.card.mode!="usage":
            return
        view=self.work.ledger.view(self.usage_key,explicit_missing=True)
        self.usage_key=view["selected"]
        field=self.card.turns
        field.blockSignals(True)
        field.clear()
        for opt in view["options"]:
            field.addItem(opt["label"],opt["key"])
        field.setCurrentIndex(field.findData(self.usage_key))
        field.blockSignals(False)
        self.card.display("usage",view["text"])

    def test_route(self,whisper):
        cfg=dict(self.config)
        source,model=route(cfg,whisper)
        self.settings.model_status.setText("正在检查连接…")
        def run():
            try:
                if source=="local":
                    models=[p.name for p in RUNTIME.glob("*.gguf") if not p.name.startswith("mmproj")]
                    if model not in models or not any(RUNTIME.glob("llama-*/llama-server.exe")):
                        raise ValueError("请下载或选择已安装的本地模型")
                else:
                    models=list_models(source,cfg)
                    if model and model not in models:
                        raise ValueError("已连接，所选模型不在返回的列表中")
                self.modelList.emit(source,models,"已连接。可用模型 "+str(len(models))+" 个。")
            except Exception as exc:
                self.modelList.emit(source,[],str(exc))
        threading.Thread(target=run,daemon=True).start()

    def models_loaded(self,source,models,message):
        if not self.settings:
            return
        self.settings.model_status.setText(message)
        keys={"api":("apiModel","whisperApiModel"),"codex":("codexModel","whisperCodexModel"),"local":("whisperModel",)}
        for key in keys[source]:
            field=self.settings.model_fields[key]
            field.blockSignals(True)
            for model in models:
                if field.findText(model)<0:
                    field.addItem(model)
            field.blockSignals(False)

    def edit_credential(self):
        from urllib.parse import urlsplit
        from providers import endpoint
        from win_credentials import save_key
        try:
            conn,_,_=endpoint(self.config)
            conn.close()
            u=urlsplit(self.config["apiURL"])
            origin=u.scheme+"://"+u.netloc
            secret,ok=QInputDialog.getText(self.settings,"Windows 凭据管理器",origin+" 的 API 密钥（留空移除）",QLineEdit.Password)
            if ok:
                save_key(origin,secret)
                self.settings.model_status.setText("已更新此服务的 Windows 凭据。")
        except (OSError,ValueError) as exc:
            self.settings.model_status.setText(str(exc))

    def todos(self):
        if not self.tasks:
            self.tasks=Tasks(self)
        self.tasks.refresh()
        self.tasks.show()
        self.tasks.raise_()

    def open_settings(self):
        if self.settings is None:
            self.settings=Settings(self)
        self.settings.show_front()

    def register(self):
        import service
        def run():
            try:
                service.lifecycle()
                write(DATA/"connection.json",{"ok":True})
            except Exception as exc:
                write(DATA/"connection.json",{"ok":False,"message":str(exc)})
            self.registered.emit()
        threading.Thread(target=run,daemon=True).start()

    def download(self,vision):
        if self.downloading:
            return
        self.downloading=True
        def run():
            try:
                install(vision,self.config["backend"],self.progress.emit)
            except Exception as exc:
                self.progress.emit("下载失败，可重试。"+str(exc))
            finally:
                self.modelDone.emit()
        threading.Thread(target=run,daemon=True).start()

    def setting(self,key,value):
        self.config[key]=value
        write(self.cfgfile,self.config)
        if key=="trackCost":
            self.work.track_cost=bool(value)
        if key in ("persona","blockedWords","avoidWeather","avoidPlaces") and self.cancel:
            self.cancel_chat()
        if key=="size":
            self.pet.set_size(value)
            self.pet.constrain()
        elif key=="pack":
            self.pet.load_pack()
            self.pet.update()
        elif key=="shortcut":
            self.keys.bind()
        elif key=="rounds":
            self.save_history()

    def mapping(self,key,value):
        self.config["mapping"][key]=value
        write(self.cfgfile,self.config)
        self.pet.update()

    def save_position(self):
        self.config.update(x=self.pet.x(),y=self.pet.y())
        write(self.cfgfile,self.config)

    def recover(self):
        area=self.pet.bounds(QCursor.pos())
        self.pet.move(area.center()-self.pet.rect().center())
        self.pet.show()
        self.pet.frame.start()
        self.config["asleep"]=False
        self.save_position()

    def toggle(self):
        if self.pet.isVisible():
            self.pet.hide()
            self.pet.frame.stop()
            self.pet.physics.stop()
            self.card.close_card()
        else:
            self.pet.constrain()
            self.pet.show()
            self.pet.frame.start()
        self.setting("asleep",not self.pet.isVisible())

    def mute(self):
        self.setting("muted",not self.config["muted"])

    def new_profile(self):
        key,ok=QInputDialog.getText(self.settings,"独立档案","档案名（1–32 个字母、数字、汉字、下划线或短横线）")
        if ok and re.fullmatch(r"[\w-]{1,32}",key):
            subprocess.Popen([sys.executable,str(Path(__file__)),"--profile",key],creationflags=subprocess.CREATE_NO_WINDOW)

    def shutdown(self):
        self.server.newConnection.disconnect(self.connections)
        for sock in list(self.sockets):
            if isValid(sock):
                sock.blockSignals(True)
                sock.close()
        self.sockets.clear()
        self.keys.clear()
        self.cancel_chat(False)
        if self.worker and self.worker.is_alive():
            self.worker.join(2)
        self.save_position()
        self.tray.hide()
        self.work.close()
        self.server.close()
        write(self.folder/"status.json",{"state":"idle","online":False})


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--profile",default="main",type=lambda x:x if re.fullmatch(r"[\w-]{1,32}",x) else "main")
    parser.add_argument("--background",action="store_true")
    args=parser.parse_args()
    if send(args.profile,{"command":"settings"}):
        return
    DATA.mkdir(parents=True,exist_ok=True)
    handler=RotatingFileHandler(DATA/"windows.log",maxBytes=256000,backupCount=2,encoding="utf8")
    logging.basicConfig(handlers=[handler],level=logging.ERROR)
    sys.excepthook=lambda typ,value,tb:logging.error("GUI exception",exc_info=(typ,value,tb))
    app=QApplication(sys.argv)
    app.setApplicationName("Cartethyia")
    app.setApplicationVersion("0.2.0")
    app.setQuitOnLastWindowClosed(False)
    app.setWindowIcon(QIcon(str(ROOT/"art/cartethyia.ico")))
    app.setStyleSheet(STYLE)
    lock=QLockFile(str(DATA/("instance-"+args.profile+".lock")))
    lock.setStaleLockTime(0)
    if not lock.tryLock(0):
        for attempt in range(15):
            if send(args.profile,{"command":"settings"}):
                break
            time.sleep(.08)
        return
    server=QLocalServer()
    server.setSocketOptions(QLocalServer.UserAccessOption)
    if not server.listen(name(args.profile)):
        send(args.profile,{"command":"settings"})
        return
    owner=Companion(args.profile,server)
    if not args.background:
        owner.open_settings()
    try:
        return app.exec()
    finally:
        lock.unlock()


if __name__=="__main__":
    main()

