"""Local named pipes, restricted by Qt to the Windows user who owns the server."""
import hashlib
import json
import os
import re
from common import DATA

def name(profile):
    tag = hashlib.sha256(str(DATA).lower().encode()).hexdigest()[:20]
    return "Cartethyia-"+tag+"-"+profile


def send(profile, payload):
    import ctypes
    path = "\\\\.\\pipe\\"+name(profile)
    if not ctypes.windll.kernel32.WaitNamedPipeW(path,350):
        return False
    try:
        with open(path,"r+b",buffering=0) as pipe:
            if payload.get("command")=="settings":
                import msvcrt
                pid=ctypes.c_ulong()
                native=ctypes.c_void_p(msvcrt.get_osfhandle(pipe.fileno()))
                if ctypes.windll.kernel32.GetNamedPipeServerProcessId(native,ctypes.byref(pid)):
                    ctypes.windll.user32.AllowSetForegroundWindow(pid.value)
            pipe.write(json.dumps(payload).encode()+b"\n")
        return True
    except OSError:
        return False


def hook():
    import sys
    print("{}",flush=True)
    if os.environ.get("PET_PLUS_INTERNAL") == "1":
        return
    raw = sys.stdin.buffer.read(1048577)
    if len(raw)>1048576:
        return
    data = json.loads(raw)
    event = data.get("hook_event_name")
    kinds={"UserPromptSubmit":"start","PreToolUse":"tool","PostToolUse":"result","PermissionRequest":"approval","Stop":"stop-attempt","Interrupt":"abort","SubagentStop":"child-stop"}
    if event not in kinds:
        return
    fields={"thread":"agent_id" if event=="SubagentStop" else "session_id","turn":"turn_id","tool":"tool_name","call":"tool_use_id"}
    e={k:v[:160] for k,src in fields.items() if isinstance(v:=data.get(src),str)}
    if not e.get("thread") or not e.get("turn"):
        return
    for profile in (DATA/"profiles").glob("*"):
        if re.fullmatch(r"[\w-]{1,32}",profile.name):
            send(profile.name,dict(e,v=1,source="hook",kind=kinds[event]))

