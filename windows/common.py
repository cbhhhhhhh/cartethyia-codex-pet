"""Paths shared by the GUI, plugin helpers and installer."""
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
DATA = Path(os.environ["LOCALAPPDATA"]) / "CartethyiaPet"
CODEX = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")
ART = ROOT / "art"
CLIPS = ART / "pets/cartethyia"
if not (CLIPS / "pet-plus.json").exists():
    CLIPS = ROOT / ".build/clips"


def read(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as tmp:
        tmp.write(json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8"))
    try:
        os.replace(tmp.name, path)
    finally:
        Path(tmp.name).unlink(missing_ok=True)

