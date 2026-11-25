"""Run under different Qt display scale factors, exercise positioning across virtual work areas."""
import argparse
import json
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
from PySide6.QtCore import QPoint,QRect
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
args.out.write_text(json.dumps(result,indent=2))
print(result["window_dpr"],len(result["cases"]))

