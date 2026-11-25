"""Transparent Windows character surface. Qt uses a per-pixel layered HWND."""
import math
import os
import random
import time
from collections import deque
from PySide6.QtCore import QPoint, Qt, QTimer, Signal
from PySide6.QtGui import QCursor, QGuiApplication, QPainter, QPixmap
from PySide6.QtWidgets import QWidget
from common import ART, CLIPS, CODEX, read

ROWS = ["idle","running-right","running-left","waving","jumping","failed","waiting","running","review"]
COUNTS = [6,8,8,4,5,8,6,6,6]
FLAGS = Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint


class Pet(QWidget):
    clicked = Signal()
    menuAt = Signal(object)
    hovered = Signal(bool)
    positioned = Signal()
    settled = Signal()
    painted = Signal(str)
    def __init__(self, config):
        super().__init__(None, FLAGS | Qt.WindowDoesNotAcceptFocus)
        self.setWindowTitle("Cartethyia")
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMouseTracking(True)
        self.config = config
        self.state = "idle"
        self.last_painted = ""
        self.action = ""
        self.until = 0
        self.samples = deque()
        self.drag = None
        self.velocity = None
        self.load_pack()
        self.set_size(config["size"])
        self.frame = QTimer(self, interval=125)
        self.frame.timeout.connect(self.update)
        self.frame.start()
        self.physics = QTimer(self, interval=16, timerType=Qt.PreciseTimer)
        self.physics.timeout.connect(self.fly)
        self.move(config["x"],config["y"])
        self.constrain()

    def load_pack(self):
        key = self.config["pack"]
        base = CODEX / "pets" / key if key and key == os.path.basename(key) else ART
        meta = read(base/"pet.json", {})
        name = os.path.basename(meta.get("spritesheetPath","spritesheet.webp"))
        self.sheet = QPixmap(str(base/name))
        if self.sheet.width() != 1536 or self.sheet.height() < 1872:
            self.sheet = QPixmap(str(ART/"pets/cartethyia/spritesheet.webp"))
        self.cliproot = base if (base/"pet-plus.json").exists() else CLIPS
        self.clips = read(self.cliproot/"pet-plus.json",{}).get("clips",{}) if key=="cartethyia" or self.cliproot==base else {}
        self.cached = ("", None)

    def set_size(self, width):
        self.setFixedSize(width,round(width*208/192))
        self.update()

    def image(self):
        mapped = self.config["mapping"].get(self.state,"idle")
        action = self.action if self.state=="idle" and time.monotonic()<self.until else mapped
        if action in self.clips:
            spec = self.clips[action]
            if self.cached[0] != action:
                self.cached = (action,QPixmap(str(self.cliproot/os.path.basename(spec["file"]))))
            sheet = self.cached[1]
            count = max(1,int(spec["frames"]))
            width = sheet.width()//count
            index = int(time.monotonic()*spec.get("fps",8))%count
            if width:
                return sheet.copy(index*width,0,width,sheet.height())
        row = ROWS.index(action) if action in ROWS else 0
        index = int(time.monotonic()*8)%COUNTS[row]
        return self.sheet.copy(index*192,row*208,192,208)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        painter.drawPixmap(self.rect(),self.image())
        painter.end()
        if self.state!=self.last_painted:
            self.last_painted=self.state
            self.painted.emit(self.state)

    def play(self, action):
        self.action = action
        self.until = time.monotonic()+2
        self.update()

    def bounds(self, point=None):
        screen = QGuiApplication.screenAt(point or self.frameGeometry().center()) or self.screen() or QGuiApplication.primaryScreen()
        return screen.availableGeometry()

    def constrain(self, screen=None):
        area = screen or self.bounds()
        self.move(max(area.left(),min(self.x(),area.right()+1-self.width())),
                  max(area.top(),min(self.y(),area.bottom()+1-self.height())))

    def enterEvent(self,event):
        self.hovered.emit(True)

    def leaveEvent(self,event):
        self.hovered.emit(False)

    def moveEvent(self,event):
        self.positioned.emit()

    def mousePressEvent(self,event):
        if event.button()==Qt.RightButton:
            self.menuAt.emit(event.globalPosition().toPoint())
        elif event.button()==Qt.LeftButton:
            self.physics.stop()
            self.drag = event.globalPosition().toPoint()-self.pos()
            self.origin = event.globalPosition().toPoint()
            self.samples.clear()
            self.samples.append((time.monotonic(), self.origin))
            self.moved = False
            self.reverse = False
            self.grabMouse()

    def mouseDoubleClickEvent(self,event):
        self.mousePressEvent(event)
        self.reverse = True

    def mouseMoveEvent(self,event):
        if self.drag is None:
            return
        pos = event.globalPosition().toPoint()
        if (pos-self.origin).manhattanLength()>4:
            self.moved = True
        if self.moved:
            self.move(pos-self.drag)
            self.constrain(self.bounds(pos))
            now = time.monotonic()
            self.samples.append((now,pos))
            while len(self.samples)>1 and self.samples[0][0]<now-.75:
                self.samples.popleft()

    def mouseReleaseEvent(self,event):
        if event.button()!=Qt.LeftButton or self.drag is None:
            return
        self.releaseMouse()
        self.drag = None
        if not self.moved:
            self.clicked.emit()
            return
        now = time.monotonic()
        last, end = self.samples[-1]
        start, prev = self.samples[0]
        distance = sum(math.hypot((b-a).x(),(b-a).y()) for (_,a),(_,b) in zip(self.samples,list(self.samples)[1:]))
        delta = end-prev
        dt = max(.04,last-start)
        recent, p = next(((t,p) for t,p in self.samples if t>=last-.17),(start,prev))
        v = end-p
        vx,vy = v.x()/max(.035,last-recent), v.y()/max(.035,last-recent)
        if now-last>=.18:
            self.settled.emit()
            return
        if self.reverse:
            vx,vy = (self.origin-end).x()*8,(self.origin-end).y()*8
        elif distance>75 and distance>1.55*math.hypot(delta.x(),delta.y()) and distance/dt>240:
            vx,vy = random.choice((-1,1))*max(850, self.bounds().width()*.95),-480
        elif math.hypot(vx,vy)<420:
            self.settled.emit()
            return
        self.velocity = [max(-3000,min(3000,vx)),max(-1800,min(1800,vy))]
        self.fx,self.fy = self.x(),self.y()
        self.arena = self.bounds()
        self.last = now
        self.physics.start()

    def fly(self):
        now = time.monotonic()
        dt,self.last = min(.04,now-self.last),now
        vx,vy = self.velocity
        vy += self.config.get("gravity",1400)*dt
        self.fx += vx*dt
        self.fy += vy*dt
        area = self.arena
        left,right = area.left(),area.right()+1-self.width()
        top,bottom = area.top(),area.bottom()+1-self.height()
        if self.fx<left or self.fx>right:
            self.fx=max(left,min(right,self.fx))
            vx *= -.78
        if self.fy<top or self.fy>=bottom:
            self.fy=max(top,min(bottom,self.fy))
            vy *= -.68
            if self.fy==bottom:
                vx *= .88
                if abs(vy)<35:
                    vy=0
        self.velocity=[vx,vy]
        self.move(round(self.fx),round(self.fy))
        if self.fy>=bottom-1 and abs(vy)<35 and abs(vx)<15:
            self.physics.stop()
            self.settled.emit()

