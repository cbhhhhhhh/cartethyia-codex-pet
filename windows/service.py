"""Installer lifecycle and stdio entry points. Configuration belongs to Codex CLI."""
import datetime
import os
import pathlib
import shutil
import subprocess
import sys
import tomllib
from common import CODEX, DATA, ROOT, read, write
from transport import hook, send

ID = "cartethyia-windows-local"
PLUGIN = "pet-plus@"+ID
MARKET = DATA/"marketplace"
PY = ROOT/"runtime/python.exe"


def private_data():
    """Prevent inherited read access to configuration backups, images and memories."""
    DATA.mkdir(parents=True,exist_ok=True)
    script = """
$ErrorActionPreference = 'Stop'
$folder = Join-Path $env:LOCALAPPDATA 'CartethyiaPet'
$acl = New-Object System.Security.AccessControl.DirectorySecurity
$acl.SetAccessRuleProtection($true,$false)
$sid = [System.Security.Principal.WindowsIdentity]::GetCurrent().User
$rule = New-Object System.Security.AccessControl.FileSystemAccessRule($sid,'FullControl','ContainerInherit,ObjectInherit','None','Allow')
$acl.AddAccessRule($rule)
[System.IO.Directory]::SetAccessControl($folder,$acl)
"""
    subprocess.run(["powershell.exe","-NoProfile","-NonInteractive","-Command",script],
                   capture_output=True,check=True,timeout=30,creationflags=subprocess.CREATE_NO_WINDOW)


def cli():
    binary = shutil.which("codex.exe")
    if binary:
        return binary
    paths=list((pathlib.Path(os.environ["LOCALAPPDATA"])/"OpenAI/Codex/bin").glob("*/codex.exe"))
    if paths:
        return str(max(paths,key=lambda p:p.stat().st_mtime))
    raise RuntimeError("未找到 Codex CLI；安装 Codex 后可在桌宠设置里重新连接")


def call(*args):
    run=subprocess.run([cli(),"plugin",*args],capture_output=True,timeout=90,creationflags=subprocess.CREATE_NO_WINDOW)
    if run.returncode:
        raise RuntimeError(run.stderr.decode("utf8","replace")[-900:] or "Codex 注册失败")


def lifecycle(remove=False):
    if not remove:
        private_data()
    config=CODEX/"config.toml"
    contents=config.read_bytes() if config.exists() else b""
    cfg=tomllib.loads(contents.decode("utf-8-sig"))
    entry=cfg.get("marketplaces",{}).get(ID)
    marker=DATA/"registration.json"
    owned=read(marker,{})
    if entry and not os.path.samefile(entry.get("source") or entry.get("path") or ".", MARKET):
        raise RuntimeError("同名 marketplace 的来源已变更，已保留现有配置")
    if remove and not owned:
        return
    if not remove and not owned and (entry or PLUGIN in cfg.get("plugins",{})):
        raise RuntimeError("同名注册已存在，保留原注册")
    backup=DATA/"backup"/(datetime.datetime.now().strftime("%Y%m%d-%H%M%S-%f")+".toml")
    backup.parent.mkdir(parents=True,exist_ok=True)
    if config.exists():
        shutil.copy2(config,backup)
    if remove:
        if PLUGIN in cfg.get("plugins",{}):
            call("remove",PLUGIN)
        if entry:
            call("marketplace","remove",ID)
        for rel in (".agents/plugins/marketplace.json","plugins/pet-plus/.codex-plugin/plugin.json","plugins/pet-plus/.mcp.json"):
            path=MARKET/rel
            path.unlink(missing_ok=True)
            parent=path.parent
            while parent.is_relative_to(MARKET):
                try:
                    parent.rmdir()
                except OSError:
                    break
                parent=parent.parent
        marker.unlink(missing_ok=True)
        return
    plugin=MARKET/"plugins/pet-plus"
    write(MARKET/".agents/plugins/marketplace.json",{
        "name":ID,"interface":{"displayName":"Cartethyia · Windows"},
        "plugins":[{"name":"pet-plus","source":{"source":"local","path":"./plugins/pet-plus"},
                    "policy":{"installation":"AVAILABLE","authentication":"ON_INSTALL"},"category":"Productivity"}]})
    # The native Windows Codex session launches hooks through its selected PowerShell.
    command='"'+PY.as_posix()+'" -B "'+(ROOT/"windows/service.py").as_posix()+'" hook'
    def ps_literal(path):
        return "'"+str(path).replace("'","''")+"'"
    windows_command="& "+ps_literal(PY)+" -B "+ps_literal(ROOT/"windows/service.py")+" hook"
    events="UserPromptSubmit PreToolUse PostToolUse PermissionRequest Stop Interrupt SubagentStop".split()
    hooks={e:[{"hooks":[{"type":"command","command":command,"commandWindows":windows_command,"timeout":3,"async":True}]}] for e in events}
    write(plugin/".codex-plugin/plugin.json",{"name":"pet-plus","version":"2.2.0-win.1","description":"卡提希娅 Windows 桌宠","hooks":{"hooks":hooks},"mcpServers":"./.mcp.json"})
    write(plugin/".mcp.json",{"mcpServers":{"pet_plus":{"command":str(PY),"args":["-B",str(ROOT/"windows/service.py"),"mcp"]}}})
    write(marker,{"market":str(MARKET),"codex":str(CODEX)})
    if not entry:
        call("marketplace","add",str(MARKET))
    call("add",PLUGIN)


if __name__=="__main__":
    action=sys.argv[1]
    try:
        if action=="hook":
            hook()
        elif action=="mcp":
            sys.stdin.reconfigure(encoding="utf-8")
            sys.stdout.reconfigure(encoding="utf-8")
            import mcp
        elif action=="shutdown":
            for folder in (DATA/"profiles").glob("*"):
                send(folder.name,{"command":"quit"})
        elif action in ("register","unregister"):
            lifecycle(action=="unregister")
            write(DATA/"connection.json",{"ok":True,"action":action})
    except Exception as exc:
        if action in ("register","unregister"):
            write(DATA/"connection.json",{"ok":False,"message":str(exc)})
            sys.exit(1)

