from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (QCheckBox,QComboBox,QDateTimeEdit,QDialog,QDialogButtonBox,QFileDialog,
    QFormLayout,QFrame,QHBoxLayout,QInputDialog,QLabel,QLineEdit,QListWidget,QMessageBox,QPushButton,
    QScrollArea,QSpinBox,QTabWidget,QTextEdit,QVBoxLayout,QWidget)
from common import ART, CODEX, DATA
from model_store import TEXT, VISION, PROJECTOR
from pet import FLAGS, ROWS
import datetime
import random
import reminders

LABELS={"idle":"待机","thinking":"思考","working":"工作","review":"检查","success":"完成","error":"失败","waiting-for-approval":"等待审批"}
STYLE="""
QWidget {font-family:'Microsoft YaHei UI','Microsoft YaHei'; font-size:13px; color:#393740}
QDialog {background:#f7f5f0} QFrame#card {background:#fffaf2;border:1px solid #d4c8b5;border-radius:16px}
QPushButton {background:#f0e9dc;border:1px solid #d1c3ac;border-radius:7px;padding:4px 9px}
QPushButton:hover {background:#e4d7be} QLineEdit,QSpinBox,QComboBox,QTextEdit,QListWidget,QDateTimeEdit {background:white;border:1px solid #cfc6b9;border-radius:5px;padding:4px}
QTabWidget::pane {border:0} QLabel#name {font-weight:bold;color:#666343}
"""


def button(label, callback):
    b=QPushButton(label)
    b.clicked.connect(lambda checked=False:callback())
    return b


class Illustration(QWidget):
    def __init__(self):
        super().__init__()
        self.picture=QPixmap()
        self.setFixedHeight(108)

    def paintEvent(self,event):
        p=QPainter(self)
        p.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        rect=QRectF(self.rect()).adjusted(0.5,0.5,-0.5,-0.5)
        border=QPainterPath()
        border.addRoundedRect(rect,15,15)
        gradient=QLinearGradient(rect.topLeft(),rect.bottomRight())
        gradient.setColorAt(0,QColor("#fcf1df"))
        gradient.setColorAt(1,QColor("#f6dfcf"))
        p.setClipPath(border)
        p.fillPath(border,gradient)
        middle=rect.center()
        p.setBrush(QColor("#faf4e8"))
        p.setPen(QPen(QColor("#dfc59e"),1))
        p.drawEllipse(middle,49,49)
        p.setBrush(QColor("#bca173"))
        p.setPen(Qt.NoPen)
        for x,y,size in ((.13,.28,6),(.2,.7,3),(.82,.32,4),(.75,.76,5)):
            cx,cy=rect.width()*x,rect.height()*y
            star=QPainterPath(QPointF(cx,cy-size))
            for dx,dy in ((.22,-.22),(.76,0),(.22,.22),(0,1),(-.22,.22),(-.76,0),(-.22,-.22)):
                star.lineTo(cx+dx*size,cy+dy*size)
            star.closeSubpath()
            p.drawPath(star)
        if not self.picture.isNull():
            height=rect.height()*1.01
            width=self.picture.width()*height/self.picture.height()
            p.drawPixmap(QRectF(middle.x()-width/2,rect.bottom()-height,width,height),
                         self.picture,QRectF(self.picture.rect()))
        p.end()


class Card(QWidget):
    def __init__(self, owner):
        super().__init__(None, FLAGS)
        self.owner=owner
        self.mode=""
        self.photo=None
        self.setWindowTitle("Cartethyia · 气泡")
        self.setAttribute(Qt.WA_TranslucentBackground)
        outer=QVBoxLayout(self)
        outer.setContentsMargins(4,4,4,16)
        self.point_down=True
        self.pointer_x=145
        self.panel=QFrame()
        outer.addWidget(self.panel)
        self.box=QVBoxLayout(self.panel)
        head=QHBoxLayout()
        self.portrait=Illustration()
        self.name=QLabel("Cartethyia",objectName="name")
        self.name.setStyleSheet("font-family:Georgia,serif;font-style:italic;font-weight:700;font-size:16px;color:#48635b")
        head.addWidget(self.name)
        head.addStretch()
        close=button("×",self.close_card)
        close.setStyleSheet("border:0;background:transparent;color:#496258;font-size:20px")
        close.setFixedSize(28,26)
        head.addWidget(close)
        self.box.addLayout(head)
        self.box.addWidget(self.portrait)
        self.body=QLabel()
        self.body.setTextFormat(Qt.PlainText)
        self.body.setWordWrap(True)
        self.body.setStyleSheet("font-family:'幼圆','Microsoft YaHei UI';font-weight:600;font-size:16px;padding:8px 4px")
        self.box.addWidget(self.body)
        self.input=QLineEdit(placeholderText="和卡提说句话…",maxLength=2000)
        self.input.returnPressed.connect(self.submit)
        self.box.addWidget(self.input)
        row=QHBoxLayout()
        self.image=button("图片",self.pick_image)
        self.send=button("发送",self.submit)
        self.stop=button("中断",self.owner.cancel_chat)
        self.reply=button("回复",self.compose)
        self.read_aloud=button("朗读",lambda:owner.speak(self.body.text()))
        self.jump=button("回到会话",lambda:owner.jump(owner.last_thread))
        for w in (self.image,self.send,self.stop,self.reply,self.jump):
            row.addWidget(w)
        row.addStretch()
        row.addWidget(self.read_aloud)
        self.box.addLayout(row)
        self.setFixedWidth(285)

    def paintEvent(self,event):
        p=QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        y=1 if self.point_down else 11
        rect=QRectF(1,y,self.width()-2,self.height()-13)
        bubble=QPainterPath()
        bubble.addRoundedRect(rect,16,16)
        edge=rect.bottom() if self.point_down else rect.top()
        tip=QPainterPath(QPointF(self.pointer_x-10,edge))
        tip.lineTo(self.pointer_x,edge+(10 if self.point_down else -10))
        tip.lineTo(self.pointer_x+10,edge)
        tip.closeSubpath()
        p.setPen(QPen(QColor("#c6cdbf"),1))
        p.setBrush(QColor("#fffcf5"))
        p.drawPath(bubble.united(tip))
        p.end()

    def layout_at_pet(self):
        self.adjustSize()
        pet=self.owner.pet
        area=pet.bounds()
        x=max(area.left(),min(pet.x()+(pet.width()-self.width())//2,area.right()+1-self.width()))
        self.pointer_x=max(22,min(self.width()-22,pet.frameGeometry().center().x()-x))
        y=pet.y()-self.height()+8
        self.point_down=y>=area.top()
        if not self.point_down:
            y=min(area.bottom()+1-self.height(),pet.y()+pet.height()-8)
        self.layout().setContentsMargins(4,4 if self.point_down else 16,4,16 if self.point_down else 4)
        self.move(x,max(area.top(),y))
        self.update()

    def display(self,mode,text="",emotion="calm",new=True):
        self.mode=mode
        self.body.setText(text)
        self.body.setVisible(bool(text))
        if new:
            self.name.setText(self.owner.config["pack"].capitalize())
            if self.owner.config["pack"]=="cartethyia":
                pic=QPixmap(str(ART.parent/f"src/web/portraits/{emotion}-{random.randrange(2)}.png"))
            else:
                pic=self.owner.pet.image()
            self.portrait.picture=pic
            self.portrait.update()
        self.portrait.setVisible(mode in ("reply","stream","notice"))
        self.read_aloud.setVisible(mode=="reply")
        for widget,on in ((self.input,mode=="input"),(self.image,mode=="input"),(self.send,mode=="input"),
                          (self.stop,mode=="stream"),(self.reply,mode in ("reply","notice")),
                          (self.jump,mode=="notice" and bool(self.owner.last_thread))):
            widget.setVisible(on)
        self.setAttribute(Qt.WA_ShowWithoutActivating,mode!="input")
        self.layout_at_pet()
        self.show()
        if mode=="input":
            self.raise_()
            self.activateWindow()
            self.input.setFocus()

    def close_card(self):
        self.hide()
        self.mode=""
        self.photo=None
        self.image.setText("图片")

    def compose(self):
        if self.owner.cancel is not None:
            self.display("stream",self.owner.partial or "正在思考…","focused")
        else:
            self.display("input")

    def pick_image(self):
        path,_=QFileDialog.getOpenFileName(self,"选择本地图片","","PNG / JPEG (*.png *.jpg *.jpeg)")
        if path:
            self.photo=path
            self.image.setText("已选图片")

    def submit(self):
        value=self.input.text().strip()
        if value:
            photo=self.photo
            self.photo=None
            self.image.setText("图片")
            self.input.clear()
            self.owner.chat(value,photo)


class Settings(QDialog):
    def __init__(self,owner):
        super().__init__()
        self.owner=owner
        cfg=owner.config
        self.setWindowTitle("卡提希娅 · 设置")
        self.resize(535,535)
        box=QVBoxLayout(self)
        tabs=QTabWidget()
        box.addWidget(tabs)
        def page(name):
            w=QWidget()
            form=QFormLayout(w)
            form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
            tabs.addTab(w,name)
            return form
        def spin(key,label,low,high):
            field=QSpinBox(minimum=low,maximum=high,value=cfg[key])
            field.valueChanged.connect(lambda v:owner.setting(key,v))
            form.addRow(label,field)
        def check(key,label):
            field=QCheckBox(label,checked=bool(cfg.get(key)))
            field.toggled.connect(lambda v:owner.setting(key,v))
            form.addRow(field)
        def line(key,label):
            field=QLineEdit(str(cfg.get(key,"")))
            field.textEdited.connect(lambda v:owner.setting(key,v))
            form.addRow(label,field)
        def combo(key,label,values,editable=False):
            field=QComboBox(editable=editable)
            field.addItems(list(dict.fromkeys([str(cfg.get(key,""))]+values)))
            field.currentTextChanged.connect(lambda v:owner.setting(key,v))
            form.addRow(label,field)
        form=page("角色")
        spin("size","角色宽度",64,350)
        form.addRow(button("移到鼠标所在屏幕",owner.recover))
        combo("pack","角色包",["cartethyia"]+[p.name for p in (CODEX/"pets").glob("*") if (p/"pet.json").exists()])
        combo("shortcut","唤醒快捷键  Ctrl + Alt +",["P","K","J"])
        form.addRow(button("打开独立伙伴档案",owner.new_profile))
        self.connection=QLabel()
        self.connection.setWordWrap(True)
        form.addRow(self.connection)
        form.addRow(button("连接本机 Codex",owner.register))
        form=page("聊天")
        persona=QTextEdit(cfg["persona"])
        persona.setMaximumHeight(74)
        persona.textChanged.connect(lambda:owner.setting("persona",persona.toPlainText()[:3000]))
        form.addRow("人设",persona)
        spin("rounds","保留上下文（轮）",1,50)
        combo("model","文字模型",[TEXT]+[p.name for p in (DATA/"runtime").glob("*.gguf")],True)
        combo("vision","视觉模型",[VISION],True)
        combo("projector","视觉投影",[PROJECTOR],True)
        combo("backend","推理后端",["auto","cpu"])
        self.download=QLabel("模型保存在本机。仅使用工作提醒时无需下载。")
        self.download.setWordWrap(True)
        form.addRow(self.download)
        form.addRow(button("下载并校验文字模型",lambda:owner.download(False)),button("下载并校验视觉模型",lambda:owner.download(True)))
        form=page("提醒")
        for key,label in (("notifications","任务和审批气泡"),("focus","手动专注"),("whispers","空闲时碎碎念"),
                          ("voiceNotice","朗读任务通知"),("voiceTodo","朗读待办"),("voiceWhisper","朗读碎碎念"),("localTime","聊天附上本地时间")):
            check(key,label)
        spin("minutes","碎碎念间隔（分钟）",5,360)
        spin("quietStart","安静时段开始（小时）",0,23)
        spin("quietEnd","安静时段结束（小时）",0,23)
        check("weatherEnabled","查询 Open-Meteo 天气（发送城市及坐标）")
        line("weatherCity","城市")
        form=page("动作")
        for key,label in LABELS.items():
            field=QComboBox()
            field.addItems(ROWS+list(owner.pet.clips))
            field.setCurrentText(cfg["mapping"].get(key,"idle"))
            field.currentTextChanged.connect(lambda v,k=key:owner.mapping(k,v))
            form.addRow(label,field)
        box.addWidget(button("完成",self.close))

    def show_front(self):
        from common import read
        status=read(DATA/"connection.json",{})
        self.connection.setText("已注册。可到 Codex 设置 → Hooks 审阅桌宠钩子。" if status.get("ok") else status.get("message","基础工作状态使用本地会话记录。"))
        self.showNormal()
        self.raise_()
        self.activateWindow()


class Tasks(QDialog):
    def __init__(self,owner):
        super().__init__()
        self.base=DATA if owner.profile=="main" else owner.folder
        self.setWindowTitle("卡提希娅 · 待办")
        self.resize(410,320)
        box=QVBoxLayout(self)
        self.list=QListWidget()
        box.addWidget(self.list)
        self.text=QLineEdit(placeholderText="新待办")
        box.addWidget(self.text)
        self.due=QCheckBox("设置到期时间")
        self.date=QDateTimeEdit(datetime.datetime.now()+datetime.timedelta(hours=1),calendarPopup=True)
        box.addWidget(self.due)
        box.addWidget(self.date)
        row=QHBoxLayout()
        for title,action in [("添加",self.add),("完成 / 重开",self.toggle),("删除",self.remove)]:
            row.addWidget(button(title,action))
        box.addLayout(row)
        self.refresh()

    def refresh(self):
        self.list.clear()
        self.items=reminders.items(self.base)
        for item in self.items:
            due=datetime.datetime.fromtimestamp(item["due"]).strftime("  %m-%d %H:%M") if item["due"] else ""
            self.list.addItem(("✓  " if item["done"] else "○  ")+item["text"]+due)

    def add(self):
        if self.text.text().strip():
            when=self.date.dateTime().toPython().astimezone().isoformat() if self.due.isChecked() else None
            reminders.add(self.base,dict(text=self.text.text()[:256],due=when))
            self.text.clear()
            self.refresh()

    def toggle(self):
        i=self.list.currentRow()
        if i>=0:
            reminders.toggle(self.base,self.items[i]["id"])
            self.refresh()

    def remove(self):
        i=self.list.currentRow()
        if i>=0 and QMessageBox.question(self,"删除待办","删除选中的待办？")==QMessageBox.Yes:
            reminders.delete(self.base,self.items[i]["id"])
            self.refresh()

