"""Build from a clean Windows x64 checkout. Only verified upstream files enter the payload."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile

ROOT=Path(__file__).resolve().parents[1]
CACHE=Path(tempfile.gettempdir())/"Cartethyia-build"
BUILD=ROOT/".build"
STAGE=BUILD/"windows-app-0.2.0"
# Package only the manifest of this build; a removed source must never survive in staging.
if STAGE.is_dir():
    assert STAGE.resolve().parent == BUILD.resolve() and not STAGE.is_symlink()
    shutil.rmtree(STAGE)
RUNTIME=STAGE/"runtime"
CACHE.mkdir(exist_ok=True)
BUILD.mkdir(exist_ok=True)
STAGE.mkdir(exist_ok=True)
RUNTIME.mkdir(exist_ok=True)



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
shutil.copytree(ROOT/"art/pets", STAGE/"art/pets", dirs_exist_ok=True)
performance = ROOT/"art/performances"
clips = json.loads((performance/"pet-plus.json").read_bytes())["clips"]
repertoire = json.loads((ROOT/"art/repertoire.json").read_bytes())
if set(clips) != {item["title"] for item in repertoire} or len(clips) != 109:
    raise RuntimeError("Action catalogue does not match the performance manifest")
for title, spec in clips.items():
    asset = (performance/spec["file"]).resolve()
    if asset.parent != (performance/"clips").resolve() or spec["frames"] != 24:
        raise ValueError("Invalid performance: " + title)
    copy(asset, STAGE/"art/performances"/spec["file"])
copy(performance/"pet-plus.json", STAGE/"art/performances/pet-plus.json")
copy(ROOT/"art/repertoire.json", STAGE/"art/repertoire.json")
copy(ROOT/"src/web/gallery.json", STAGE/"src/web/gallery.json")
lexicon = checked("jieba-0.42.1.tar.gz",
                  "https://files.pythonhosted.org/packages/c6/cb/18eeb235f833b726522d7ebed54f2278ce28ba9438e3135ab0278d9792a2/jieba-0.42.1.tar.gz",
                  "055ca12f62674fafed09427f176506079bc135638a14e23e25be909131928db2")
with tarfile.open(lexicon, "r:gz") as archive:
    words = set()
    for line in archive.extractfile("jieba-0.42.1/jieba/dict.txt"):
        word, _, tag = line.decode("utf8").split()
        if tag == "ns" and len(word) >= 2:
            words.add(word)
(STAGE/"src").mkdir(exist_ok=True)
(STAGE/"src/place-names-zh.txt").write_text("\n".join(sorted(words)), encoding="utf8")
for filename in ("chat","state","observe","watch","archive","reminders","weather","mcp","dialogue","pet_response","providers","preference","usage","win_credentials"):
    copy(ROOT/f"src/{filename}.py", STAGE/f"src/{filename}.py")
for filename in ("app","cards","common","core","events","model_store","pet","service","transport"):
    copy(ROOT/f"windows/{filename}.py", STAGE/f"windows/{filename}.py")
shutil.copytree(ROOT/"src/web/portraits",STAGE/"src/web/portraits",dirs_exist_ok=True)
for f in ("LICENSE","NOTICE","windows/THIRD-PARTY.txt","examples/config.json","art/cartethyia.ico","docs/WINDOWS.md"):
    copy(ROOT/f,STAGE/f)
for f in ("LGPL-3.0-only.txt","GPL-3.0-only.txt","jieba-MIT.txt"):
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
    entries.append(f'Source: "..\\.build\\windows-app-0.2.0\\{rel}"; DestDir: "{{app}}\\{rel.parent}"; '
                   f'Flags: ignoreversion; Check: NeedsRuntimeFile(\'{rel}\', \'{sha(file)}\')')
(BUILD/"runtime-files.iss").write_text("\n".join(entries),encoding="utf-8-sig")
subprocess.run([iscc,"/Qp",str(ROOT/"windows/setup.iss")],check=True)
out=ROOT/"dist/Cartethyia-0.2.0-Windows-x64-Setup.exe"
(out.parent/"SHA256SUMS-Windows.txt").write_text(sha(out)+"  "+out.name+"\n",encoding="ascii")
print(out)

