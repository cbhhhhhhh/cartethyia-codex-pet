"""Pinned upstream model/engine downloads. A verified file is atomically published."""
import hashlib
import os
import shutil
import tempfile
import zipfile
from pathlib import Path
from urllib.request import Request, urlopen
from common import DATA

RUNTIME = DATA/"runtime"
TEXT = "qwen2.5-1.5b-instruct-q4_k_m.gguf"
VISION = "Qwen3VL-2B-Instruct-Q4_K_M.gguf"
PROJECTOR = "mmproj-Qwen3VL-2B-Instruct-Q8_0.gguf"
TEXT_URL = "https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/91cad51170dc346986eccefdc2dd33a9da36ead9/"
VISION_URL = "https://huggingface.co/Qwen/Qwen3-VL-2B-Instruct-GGUF/resolve/52d6c8ffea26cc873ac5ad116f8631268d7eb503/"
ENGINE_URL = "https://github.com/ggml-org/llama.cpp/releases/download/b12675/"
ASSETS = {
    TEXT:(TEXT_URL+TEXT,"6a1a2eb6d15622bf3c96857206351ba97e1af16c30d7a74ee38970e434e9407e"),
    VISION:(VISION_URL+VISION,"089d75c52f4b7ffc56ba998ffc50aae89fcafc755f9e7208aacca281dca6c2ae"),
    PROJECTOR:(VISION_URL+PROJECTOR,"f9a68fabba69c3b81e153367b2c7521030b0fa8bb0de400c9599c8e6725f9c82"),
}
for backend,digest in [("cpu","bc362be03528651701e6218672bb0cbf48b55ba7acad0eb5006449567f4cf821"),("vulkan","b3285ef7e298fb292b971b79c3bad9a50ea79c470b1e83721dd0ebf4783d71a5")]:
    filename = "llama-b12675-bin-win-"+backend+"-x64.zip"
    ASSETS[backend] = (ENGINE_URL+filename,digest)


def fetch(key, report):
    RUNTIME.mkdir(parents=True,exist_ok=True)
    engine = key in ("cpu","vulkan")
    dest = RUNTIME/(key+".zip" if engine else key)
    url,digest = ASSETS[key]
    def valid(path):
        if path.exists():
            with path.open("rb") as f:
                return hashlib.file_digest(f,"sha256").hexdigest()==digest
        return False
    if not valid(dest):
        with tempfile.TemporaryDirectory(dir=RUNTIME) as temp:
            part = Path(temp)/"download"
            req = Request(url+"?download=true",headers={"User-Agent":"Cartethyia-Windows/2.2"})
            with urlopen(req,timeout=45) as response, part.open("wb") as out:
                received=0
                while chunk:=response.read(1024*1024):
                    out.write(chunk)
                    received+=len(chunk)
                    if received%(8*1024*1024)<len(chunk):
                        report(f"{key}  ·  {received//1048576} MiB")
            report("正在校验 "+key)
            if not valid(part):
                raise ValueError("下载的 SHA-256 与发行清单不符，请重新下载")
            os.replace(part,dest)
    if engine:
        target = RUNTIME/("llama-b12675-"+key)
        if (target/"llama-server.exe").exists():
            return
        with tempfile.TemporaryDirectory(dir=RUNTIME) as temp, zipfile.ZipFile(dest) as z:
            staged = Path(temp)/"engine"
            staged.mkdir()
            for n in z.namelist():
                if not n.endswith("/"):
                    with z.open(n) as src, (staged/Path(n).name).open("wb") as out:
                        shutil.copyfileobj(src,out)
            if not (staged/"llama-server.exe").is_file():
                raise ValueError("发行包缺少推理引擎")
            if not target.exists():
                staged.rename(target)


def install(vision, backend, report):
    for key in ["cpu"] + (["vulkan"] if backend!="cpu" else []) + ([VISION,PROJECTOR] if vision else [TEXT]):
        report("正在准备 "+key)
        fetch(key,report)
    report("已校验，可在头顶聊天")

