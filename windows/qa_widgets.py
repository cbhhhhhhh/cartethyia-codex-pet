"""Exercise installed Qt widgets on the Windows desktop, including under screen lock.
This intentionally uses Qt input delivery rather than claiming physical mouse delivery."""
import argparse
import json
import math
import os
from pathlib import Path
import sys
import time

parser=argparse.ArgumentParser()
parser.add_argument("install",type=Path)
parser.add_argument("out",type=Path)
args=parser.parse_args()
args.out.mkdir(parents=True,exist_ok=True)
sys.path.insert(0,str(args.install/"windows"))
from common import read, ROOT, write
from app import QApplication, Companion, QIcon, QLocalServer, STYLE
from PySide6.QtCore import QPoint, QPointF, QEvent, Qt
from PySide6.QtGui import QMouseEvent
from cards import LABELS
from model_store import RUNTIME, TEXT, VISION, PROJECTOR
from transport import name
from PySide6.QtWidgets import QPushButton
import app as host

application=QApplication([])
application.setStyleSheet(STYLE)
application.setWindowIcon(QIcon(str(ROOT/"art/cartethyia.ico")))
application.setQuitOnLastWindowClosed(False)
profile="windows-qa"
server=QLocalServer()
server.setSocketOptions(QLocalServer.UserAccessOption)
assert server.listen(name(profile))
owner=Companion(profile,server)
pet=owner.pet
owner.work.timer.stop()  # Keep unrelated real Codex turns out of the gesture test.
owner.tick.stop()
owner.config["size"]=144
pet.set_size(144)
pet.show()
report={"scale":pet.devicePixelRatioF(),"screen_count":len(application.screens())}


def pump(wait):
    until=time.monotonic()+wait
    while time.monotonic()<until:
        application.processEvents()
        time.sleep(.003)


def mouse(kind,p,button,buttons):
    local=pet.mapFromGlobal(p)
    evt=QMouseEvent(kind,QPointF(local),QPointF(p),button,buttons,Qt.NoModifier)
    QApplication.sendEvent(pet,evt)
    pump(.005)


def drag(points,pause):
    mouse(QEvent.MouseButtonPress,points[0],Qt.LeftButton,Qt.LeftButton)
    for p in points[1:]:
        mouse(QEvent.MouseMove,p,Qt.NoButton,Qt.LeftButton)
        pump(.008)
    pump(pause)
    mouse(QEvent.MouseButtonRelease,points[-1],Qt.LeftButton,Qt.NoButton)


def close_windows():
    owner.shutdown()
    for w in application.topLevelWidgets():
        w.hide()


try:
    pump(.15)
    resources=pet.clips
    report["clips"]=len(resources)
    report["frames"]=sum(r["frames"] for r in resources.values())
    assert all((pet.cliproot/s["file"]).is_file() for s in resources.values())
    report["portraits"]=len(list((ROOT/"src/web/portraits").glob("*.png")))
    owner.open_settings()
    pump(.1)
    owner.setting("size",158)
    assert pet.width()==158
    owner.mapping("idle","waving")
    owner.setting("rounds",10)
    assert read(owner.cfgfile,{})["mapping"]["idle"]=="waving"
    owner.setting("size",144)
    owner.mapping("idle","idle")
    owner.settings.hide()
    area=pet.bounds()
    pet.move(area.center()-pet.rect().center())
    start=pet.frameGeometry().center()
    drag([start+QPoint(i*3,0) for i in range(18)],.24)
    held=pet.pos();pump(.4)
    assert held==pet.pos() and not pet.physics.isActive()
    report["slow_drop"]=[held.x(),held.y()]
    for gesture in ("circle","shake"):
        pet.move(area.center()-pet.rect().center())
        p=pet.frameGeometry().center()
        if gesture=="circle":
            points=[p+QPoint(round(38*(math.cos(i*math.tau/24)-1)),round(38*math.sin(i*math.tau/24))) for i in range(25)]
        else:
            points=[p+QPoint(round(53*math.sin(i*math.tau/12)),0) for i in range(25)]
        drag(points,0)
        assert pet.physics.isActive()
        xs=[]
        for _ in range(150):
            xs.append(pet.x())
            pump(.018)
        report[gesture]=dict(span=max(xs)-min(xs),rebound=any(b-a>3 for a,b in zip(xs,xs[1:])) and any(a-b>3 for a,b in zip(xs,xs[1:])))
        assert report[gesture]["rebound"]
        pet.physics.stop()
    owner.pet.move(area.center()-pet.rect().center())
    pet.play(next(iter(resources)))
    pet.grab().save(str(args.out/"character.png"))
    QApplication.sendEvent(pet,QEvent(QEvent.Enter))
    pump(.33)
    report["hover_quiet"]=not owner.card.isVisible()
    assert report["hover_quiet"]
    owner.work_details()
    assert "工具" in owner.card.body.text() and "计划" in owner.card.body.text()
    owner.card.close_card()
    from PySide6.QtWidgets import QMenu
    from PySide6.QtCore import QTimer
    def inspect_menu():
        menu=application.activePopupWidget()
        if isinstance(menu,QMenu):
            report["menu"]=[a.text() for a in menu.actions() if a.text()]
            menu.close()
    QTimer.singleShot(100,inspect_menu)
    mouse(QEvent.MouseButtonPress,pet.frameGeometry().center(),Qt.RightButton,Qt.RightButton)
    assert "待办事项" in report["menu"]
    p=pet.frameGeometry().center()
    mouse(QEvent.MouseButtonPress,p,Qt.LeftButton,Qt.LeftButton)
    mouse(QEvent.MouseButtonRelease,p,Qt.LeftButton,Qt.NoButton)
    assert owner.card.mode=="input" and owner.card.input.isVisible()
    report["input_geometry"]={"card":owner.card.frameGeometry().getRect(),"pet":pet.frameGeometry().getRect(),
                              "tip_down":owner.card.point_down,"work_area":pet.bounds().getRect()}
    report["input_above"]=owner.card.point_down and owner.card.frameGeometry().center().y()<pet.frameGeometry().top()
    assert report["input_above"], report["input_geometry"]
    deltas=[]
    owner.stream.connect(lambda i,t:deltas.append(t))
    before=len(owner.history)
    owner.card.input.setText("用两句话介绍你的旅伴生活，大约四十个字。")
    owner.card.input.returnPressed.emit()
    deadline=time.monotonic()+95
    while owner.cancel is not None and time.monotonic()<deadline:
        pump(.03)
    assert len(owner.history)==before+1 and len(deltas)>=2,owner.card.body.text()
    record=owner.history[-1]
    report["text_chat"]={"chunks":len(deltas),"text":record["assistant"],"emotion":record["emotion"],"action":record["action"]}
    owner.card.grab().save(str(args.out/"reply.png"))
    before=len(owner.history)
    deltas.clear()
    owner.compose()
    owner.card.input.setText("请用一百个中文字讲一段旅途故事，有花草、日落和风。")
    owner.card.input.returnPressed.emit()
    deadline=time.monotonic()+50
    while not deltas and time.monotonic()<deadline:
        pump(.008)
    assert deltas
    owner.card.stop.click()
    pump(2)
    assert len(owner.history)==before and owner.cancel is None and owner.card.body.text()=="已中断。"
    report["chat_cancel"]={"chunks_before_stop":len(deltas),"history_preserved":True}
    if (RUNTIME/VISION).is_file() and (RUNTIME/PROJECTOR).is_file():
        owner.compose()
        owner.card.photo=str(ROOT/"src/web/portraits/happy-1.png")
        owner.card.input.setText("请描述这张图片中的角色。")
        owner.card.input.returnPressed.emit()
        deadline=time.monotonic()+100
        while owner.cancel is not None and time.monotonic()<deadline:
            pump(.04)
        assert len(owner.history)==before+1,owner.card.body.text()
        report["image_reply"]={"text":owner.history[-1]["assistant"],"image_saved":Path(owner.history[-1]["image"]).exists()}
    owner.todos()
    owner.tasks.text.setText("验收待办")
    owner.tasks.add()
    idx=next(i for i,s in enumerate(owner.tasks.items) if s["text"]=="验收待办")
    owner.tasks.list.setCurrentRow(idx)
    owner.tasks.toggle()
    report["todo_toggle"]=any(s["text"]=="验收待办" and s["done"] for s in owner.tasks.items)
    owner.config.update(asleep=False,muted=False)
    owner.toggle()
    assert not pet.isVisible()
    owner.toggle()
    assert pet.isVisible()
    report["wake_hide"]=True
finally:
    close_windows()
    (args.out/"widgets.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf8")

