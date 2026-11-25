"""Build from a clean Windows x64 checkout. Only verified upstream files enter the payload."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import zipfile

ROOT=Path(__file__).resolve().parents[1]
CACHE=Path(tempfile.gettempdir())/"Cartethyia-build"
BUILD=ROOT/".build"
STAGE=BUILD/"windows-app"
RUNTIME=STAGE/"runtime"
CACHE.mkdir(exist_ok=True)
BUILD.mkdir(exist_ok=True)
STAGE.mkdir(exist_ok=True)
RUNTIME.mkdir(exist_ok=True)
BASE="https://github.com/cbhhhhhhh/cartethyia-codex-pet/releases/download/v2.2.0/"


def sha(p):
    with p.open("rb") as f:
        return hashlib.file_digest(f,"sha256").hexdigest()


def checked(filename,url,digest):
    path=CACHE/filename
    if not path.exists() or sha(path)!=digest:
        tmp=path.with_suffix(".part")
        subprocess.run(["curl.exe","-fLsS","--retry","2","-o",str(tmp),url],check=True)
        if sha(tmp)!=digest:
            raise RuntimeError("SHA-256 mismatch: "+filename)
        os.replace(tmp,path)
    return path


def copy(src,dest):
    dest.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(src,dest)


def extract(archive,select,target):
    with zipfile.ZipFile(archive) as z:
        for entry in z.infolist():
            if entry.is_dir() or not select(entry.filename):
                continue
            path=(target/entry.filename).resolve()
            if not path.is_relative_to(target.resolve()):
                raise ValueError("Invalid archive member")
            path.parent.mkdir(parents=True,exist_ok=True)
            with z.open(entry) as inp,path.open("wb") as out:
                shutil.copyfileobj(inp,out)


def wheel(package,digest,predicate):
    import urllib.request
    with urllib.request.urlopen(f"https://pypi.org/pypi/{package}/6.9.3/json",timeout=30) as response:
        info=json.load(response)
    item=next(x for x in info["urls"] if x["filename"].endswith("win_amd64.whl"))
    path=checked(item["filename"],item["url"],digest)
    extract(path,predicate,RUNTIME)


def qt_member(n):
    if ".dist-info/" in n:
        return "/licenses/" in n or n.endswith("METADATA")
    if not n.startswith("PySide6/"):
        return False
    p=Path(n)
    if p.suffix==".py" or n.startswith("PySide6/support/"):
        return True
    if p.parent.name=="PySide6":
        if p.suffix==".pyd":
            return p.stem in {"QtCore","QtGui","QtWidgets","QtNetwork"}
        return p.suffix==".dll" and (not p.stem.startswith("Qt6") or p.stem in {"Qt6Core","Qt6Gui","Qt6Widgets","Qt6Network"})
    return p.name in {"qwindows.dll","qwebp.dll","qico.dll","qjpeg.dll","qmodernwindowsstyle.dll"}


py=checked("python.zip","https://www.python.org/ftp/python/3.13.9/python-3.13.9-embed-amd64.zip",
           "91d828c2da3a029b41699e918674a0cb379c02cf20dab9c501306885f837402a")
extract(py,lambda n:True,RUNTIME)
(RUNTIME/"python313._pth").write_text("python313.zip\n.\n../windows\n../src\n",encoding="ascii")
wheel("PySide6-Essentials","21f98077c135864473089e59a6a0bd828e64c6644b3dd7267b102da4a2ee8f21",qt_member)
wheel("shiboken6","f1498176d2d5bcade7d662e1fc5143980fb008b6c78b966289d29a4ae86cd0c6",
      lambda n:n.endswith((".py",".dll",".pyd","METADATA",".txt")))
sums=checked("SHA256SUMS",BASE+"SHA256SUMS","5a3f6a6be83065e86bdddb115dab990d05eac40a4d7878cee4e26547b1139cca")
digest,filename=sums.read_text().split()
archive=checked(filename,BASE+filename,digest)
shutil.copytree(ROOT/"art/pets",STAGE/"art/pets",dirs_exist_ok=True)
with zipfile.ZipFile(archive) as z:
    prefix="Cartethyia-Codex-Pet/payload/Codex Pet Plus.app/Contents/Resources/pets/cartethyia/"
    meta=z.read(prefix+"pet-plus.json")
    clips=json.loads(meta)["clips"]
    assert len(clips)==109 and sum(s["frames"] for s in clips.values())==1744
    target=STAGE/"art/pets/cartethyia"
    (target/"pet-plus.json").write_bytes(meta)
    for s in clips.values():
        file=s["file"]
        assert Path(file).name==file
        (target/file).write_bytes(z.read(prefix+file))
for filename in ("chat","state","observe","watch","archive","reminders","weather","mcp"):
    copy(ROOT/f"src/{filename}.py",STAGE/f"src/{filename}.py")
for filename in ("app","cards","common","core","events","model_store","pet","service","transport"):
    copy(ROOT/f"windows/{filename}.py",STAGE/f"windows/{filename}.py")
shutil.copytree(ROOT/"src/web/portraits",STAGE/"src/web/portraits",dirs_exist_ok=True)
for f in ("NOTICE","windows/THIRD-PARTY.txt","examples/config.json","art/cartethyia.ico","docs/WINDOWS.md"):
    copy(ROOT/f,STAGE/f)
for f in ("LGPL-3.0-only.txt","GPL-3.0-only.txt"):
    copy(ROOT/"windows/licenses"/f,STAGE/"windows/licenses"/f)
csc=Path(os.environ["WINDIR"])/"Microsoft.NET/Framework64/v4.0.30319/csc.exe"
subprocess.run([str(csc),"/nologo","/target:winexe","/platform:x64","/r:System.Windows.Forms.dll",
                "/win32icon:"+str(STAGE/"art/cartethyia.ico"),"/out:"+str(STAGE/"Cartethyia.exe"),str(ROOT/"windows/Launcher.cs")],check=True)
iscc=shutil.which("ISCC") or str(Path(os.environ["LOCALAPPDATA"])/"Programs/Inno Setup 6/ISCC.exe")
entries=[]
for file in sorted(RUNTIME.rglob("*")):
    if not file.is_file() or "__pycache__" in file.parts or file.suffix==".pyc":
        continue
    rel=file.relative_to(STAGE)
    entries.append(f'Source: "..\\.build\\windows-app\\{rel}"; DestDir: "{{app}}\\{rel.parent}"; '
                   f'Flags: ignoreversion; Check: NeedsRuntimeFile(\'{rel}\', \'{sha(file)}\')')
(BUILD/"runtime-files.iss").write_text("\n".join(entries),encoding="utf-8-sig")
subprocess.run([iscc,"/Qp",str(ROOT/"windows/setup.iss")],check=True)
out=ROOT/"dist/Cartethyia-2.2.0-Windows-x64-Setup.exe"
(out.parent/"SHA256SUMS-Windows.txt").write_text(sha(out)+"  "+out.name+"\n",encoding="ascii")
print(out)

