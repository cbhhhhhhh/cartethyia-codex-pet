"""Check Windows' per-pixel HWND hit-test on the resident pet, even on a locked desktop."""
import argparse
import ctypes
import json
from pathlib import Path
import win32con as C
import win32gui as G
import win32process
import win32api
import win32file
import win32security
from transport import name
from common import DATA

parser=argparse.ArgumentParser()
parser.add_argument("pid",type=int)
parser.add_argument("output",type=Path)
args=parser.parse_args()
ctypes.windll.user32.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4))
windows=[]
G.EnumWindows(lambda h,_:windows.append(h) if win32process.GetWindowThreadProcessId(h)[1]==args.pid and G.GetWindowText(h)=="Cartethyia" else None,None)
assert len(windows)==1
pet=windows[0]
x,y,r,b=G.GetWindowRect(pet)
target=G.CreateWindowEx(C.WS_EX_TOOLWINDOW,"Button","Cartethyia QA underlay",C.WS_POPUP|C.WS_VISIBLE|C.BS_AUTOCHECKBOX,x,y,r-x,b-y,0,0,0,None)
try:
    G.SetWindowPos(target,pet,x,y,r-x,b-y,C.SWP_NOACTIVATE|C.SWP_SHOWWINDOW)
    point=(x+2,y+2)
    picked=G.WindowFromPoint(point)
    assert picked==target,(hex(picked),hex(target))
    center=((x+r)//2,(y+b)//2)
    assert G.WindowFromPoint(center)==pet
    lx,ly=G.ScreenToClient(picked,point)
    lp=(ly<<16)|lx
    G.SendMessage(picked,C.WM_LBUTTONDOWN,C.MK_LBUTTON,lp)
    G.SendMessage(picked,C.WM_LBUTTONUP,0,lp)
    changed=G.SendMessage(target,0xf0,0,0)
    report={"pet_rect":[x,y,r,b],"corner_hits_underlay":True,"body_hits_pet":True,
            "target_received_button_messages":changed==1,"layered":bool(G.GetWindowLong(pet,C.GWL_EXSTYLE)&C.WS_EX_LAYERED),
            "topmost":bool(G.GetWindowLong(pet,C.GWL_EXSTYLE)&C.WS_EX_TOPMOST),"dpi":ctypes.windll.user32.GetDpiForWindow(pet)}
    assert changed==1 and report["layered"] and report["topmost"]
    token=win32security.OpenProcessToken(win32api.GetCurrentProcess(),C.TOKEN_QUERY)
    sid=win32security.GetTokenInformation(token,win32security.TokenUser)[0]
    def only_user(sd):
        dacl=sd.GetSecurityDescriptorDacl()
        return dacl.GetAceCount()==1 and dacl.GetAce(0)[2]==sid
    pipe=win32file.CreateFile("\\\\.\\pipe\\"+name("main"),C.READ_CONTROL,0,None,3,0,None)
    try:
        sd=win32security.GetSecurityInfo(pipe,win32security.SE_KERNEL_OBJECT,win32security.DACL_SECURITY_INFORMATION)
        report["pipe_current_user_only"]=only_user(sd)
    finally:
        pipe.Close()
    sd=win32security.GetNamedSecurityInfo(str(DATA/"backup"),win32security.SE_FILE_OBJECT,win32security.DACL_SECURITY_INFORMATION)
    report["backup_current_user_only"]=only_user(sd)
    assert report["pipe_current_user_only"] and report["backup_current_user_only"]
    args.output.write_text(json.dumps(report,indent=2))
    print(report)
finally:
    G.DestroyWindow(target)

