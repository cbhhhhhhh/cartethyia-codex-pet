"""Run under different Qt display scale factors, exercise positioning across virtual work areas."""
import argparse
import json
import time
from pathlib import Path
import sys
parser=argparse.ArgumentParser()
parser.add_argument("install",type=Path)
parser.add_argument("out",type=Path)
args=parser.parse_args()
sys.path.insert(0,str(args.install/"windows"))
from common import read, ROOT
from pet import Pet
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QEvent, QPoint, QPointF, QRect, Qt
from PySide6.QtGui import QMouseEvent
app=QApplication([])
cfg=read(ROOT/"examples/config.json",{})
pet=Pet(cfg)
pet.show()
app.processEvents()
result={"native_screens":[[s.name(),s.devicePixelRatio(),s.geometry().getRect()] for s in app.screens()],
        "window_dpr":pet.devicePixelRatioF(),"logical_size":[pet.width(),pet.height()],"cases":[]}
for area in [QRect(-1920,0,1920,1040),QRect(0,0,2048,1100),QRect(2048,-180,1707,912)]:
    for pt in [area.topLeft()-QPoint(200,130),area.center(),area.bottomRight()+QPoint(80,100)]:
        pet.move(pt)
        pet.constrain(area)
        assert area.contains(pet.geometry()),(area,pet.geometry())
        if pt==area.center():
            assert pet.pos()==pt
        result["cases"].append([area.getRect(),(pt.x(),pt.y()),(pet.x(),pet.y())])
if len(app.screens())>1:
    primary=next((s for s in app.screens() if s.name()=="Primary"), app.primaryScreen())
    other=next(screen for screen in app.screens() if screen!=primary)
    start=primary.availableGeometry().center()
    end=other.availableGeometry().center()
    pet.move(start-pet.rect().center())
    def deliver(kind,point,button,buttons):
        event=QMouseEvent(kind,QPointF(pet.mapFromGlobal(point)),QPointF(point),button,buttons,Qt.NoModifier)
        QApplication.sendEvent(pet,event)
        app.processEvents()
    deliver(QEvent.MouseButtonPress,start,Qt.LeftButton,Qt.LeftButton)
    for step in range(1,41):
        deliver(QEvent.MouseMove,start+(end-start)*(step/40),Qt.NoButton,Qt.LeftButton)
    time.sleep(.22)
    deliver(QEvent.MouseButtonRelease,end,Qt.LeftButton,Qt.NoButton)
    assert other.availableGeometry().contains(pet.geometry())
    cfg.update(x=pet.x(),y=pet.y())
    restored=Pet(cfg)
    assert restored.pos()==pet.pos() and restored.bounds()==other.availableGeometry()
    result["cross_display"]={"from":primary.name(),"to":other.name(),"restored_xy":[pet.x(),pet.y()]}
args.out.write_text(json.dumps(result,indent=2))
print(result["window_dpr"],len(result["cases"]))

