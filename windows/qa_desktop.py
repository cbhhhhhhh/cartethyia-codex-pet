"""Drive only identified Cartethyia windows on a logged-in Windows desktop.
Run in an isolated installation/profile with pywinauto, pywin32 and psutil."""
import argparse
import ctypes
import json
import math
import os
from pathlib import Path
import sys
import time
import win32api
import win32con as C
import win32gui as G
import win32process
from pywinauto import Desktop, keyboard
from common import DATA
from transport import send

parser=argparse.ArgumentParser()
parser.add_argument("pid",type=int)
parser.add_argument("out",type=Path)
args=parser.parse_args()
pid=args.pid
report={}
desktop=Desktop(backend="uia")
ctypes.windll.user32.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4))


def wait(fn,seconds=4):
    until=time.monotonic()+seconds
    while time.monotonic()<until:
        value=fn()
        if value:
            return value
        time.sleep(.035)
    raise RuntimeError("等待界面超时："+str(fn))


def windows():
    result=[]
    G.EnumWindows(lambda h,_:result.append(h) if win32process.GetWindowThreadProcessId(h)[1]==pid and G.IsWindowVisible(h) else None,None)
    return result


def by_title(title):
    return next((h for h in windows() if G.GetWindowText(h)==title),None)


def position():
    return G.GetWindowRect(pet)[:2]


def body():
    x,y,r,b=G.GetWindowRect(pet)
    for ratio in [.5,.6,.4,.7,.3]:
        for u in [.5,.45,.55,.35,.65]:
            p=(int(x+(r-x)*u),int(y+(b-y)*ratio))
            if G.WindowFromPoint(p)==pet:
                return p
    raise RuntimeError("角色主体未命中")


def click(point,right=False):
    win32api.SetCursorPos(point)
    down,up=(C.MOUSEEVENTF_RIGHTDOWN,C.MOUSEEVENTF_RIGHTUP) if right else (C.MOUSEEVENTF_LEFTDOWN,C.MOUSEEVENTF_LEFTUP)
    win32api.mouse_event(down,0,0)
    time.sleep(.035)
    win32api.mouse_event(up,0,0)


def drag(points,pause=0):
    win32api.SetCursorPos(points[0])
    win32api.mouse_event(C.MOUSEEVENTF_LEFTDOWN,0,0)
    for p in points[1:]:
        win32api.SetCursorPos(p)
        time.sleep(.013)
    time.sleep(pause)
    win32api.mouse_event(C.MOUSEEVENTF_LEFTUP,0,0)


def descendants(hwnd):
    return desktop.window(handle=hwnd).descendants()


pet=wait(lambda:by_title("Cartethyia"))
origin=win32api.GetCursorPos()
try:
    x,y,r,b=G.GetWindowRect(pet)
    report["physical_start_rect"]=[x,y,r,b]
    # Real underlying button: a transparent click must be delivered to it.
    sink=G.CreateWindowEx(C.WS_EX_TOOLWINDOW,"Button","Cartethyia QA target",C.WS_POPUP|C.WS_VISIBLE|C.BS_AUTOCHECKBOX,
                          x,y,r-x,b-y,0,0,0,None)
    try:
        G.SetWindowPos(sink,pet,x,y,r-x,b-y,C.SWP_NOACTIVATE|C.SWP_SHOWWINDOW)
        point=(x+2,y+2)
        if G.WindowFromPoint(point)!=sink:
            raise RuntimeError("透明区未命中测试按钮")
        click(point)
        import pythoncom
        def checked():
            pythoncom.PumpWaitingMessages()
            return G.SendMessage(sink,0x00f0,0,0)==1
        report["transparent_click"]=bool(wait(checked))
    finally:
        G.DestroyWindow(sink)
    p=body()
    win32api.SetCursorPos(p)
    time.sleep(.5)
    report["hover"]=any("工具" in desktop.window(handle=h).window_text() or
                        any("工具" in node.window_text() for node in descendants(h))
                        for h in windows())
    assert report["hover"]
    click(p,True)
    time.sleep(.25)
    menus=[w.window_text() for h in windows() for w in descendants(h) if w.element_info.control_type=="MenuItem"]
    report["menu"]=[s for s in menus if s in ("点播动作","待办事项","设置","聊天记录")]
    assert len(report["menu"])==4
    keyboard.send_keys("{ESC}")
    time.sleep(.2)
    pos=body()
    target=(win32api.GetSystemMetrics(0)//2,win32api.GetSystemMetrics(1)//2)
    drag([(int(pos[0]+i*(target[0]-pos[0])/20),int(pos[1]+i*(target[1]-pos[1])/20)) for i in range(21)],.3)
    resting=position()
    time.sleep(.4)
    assert position()==resting
    report["slow_drop"]=resting
    for gesture in ("circle","shake"):
        pos=body()
        count=26
        if gesture=="circle":
            points=[(pos[0]+round(42*(math.cos(i*math.tau/count)-1)),pos[1]+round(42*math.sin(i*math.tau/count))) for i in range(count+1)]
        else:
            points=[(pos[0]+round(62*math.sin(i*math.tau/12)),pos[1]) for i in range(count+1)]
        drag(points)
        path=[]
        for i in range(140):
            path.append(position())
            time.sleep(.025)
        xs=[p[0] for p in path]
        report[gesture]={"span":max(xs)-min(xs),"left":min(xs),"right":max(xs),"turned":any(b-a>4 for a,b in zip(xs,xs[1:])) and any(a-b>4 for a,b in zip(xs,xs[1:]))}
        assert report[gesture]["span"]>100 and report[gesture]["turned"],report[gesture]
    click(body())
    card=wait(lambda:by_title("Cartethyia · 气泡"))
    controls=descendants(card)
    assert any(w.element_info.control_type=="Edit" for w in controls)
    report["composer"]=True
    for w in controls:
        if w.window_text()=="×":
            w.invoke()
            break
    assert send("main",{"command":"settings"})
    settings=wait(lambda:by_title("卡提希娅 · 设置"))
    wrapper=desktop.window(handle=settings)
    spinner=wrapper.child_window(control_type="Spinner").wrapper_object()
    spinner.set_focus()
    keyboard.send_keys("^a176{ENTER}")
    wait(lambda:json.loads((DATA/"profiles/main/config.json").read_text(encoding="utf8")).get("size")==176)
    report["size_setting"]=176
    wrapper.close()
finally:
    win32api.SetCursorPos(origin)
    args.out.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding="utf8")

