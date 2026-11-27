"""Click both model buttons in a fresh profile and verify the downloaded weights and extracted engines."""

import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import zipfile

install = Path(sys.argv[1]).resolve()
output = Path(sys.argv[2]).resolve()
sys.path.insert(0, str(install / "windows"))


def sha(stream):
    return hashlib.file_digest(stream, "sha256").hexdigest()


with tempfile.TemporaryDirectory(prefix="cart-download-") as tmp:
    os.environ.update(LOCALAPPDATA=tmp, CODEX_HOME=str(Path(tmp) / "codex"))
    from app import QApplication, Companion, QLocalServer
    from model_store import ASSETS, PROJECTOR, RUNTIME, TEXT, VISION
    from PySide6.QtWidgets import QPushButton
    from transport import name

    q = QApplication([])
    sock = QLocalServer()
    sock.setSocketOptions(QLocalServer.UserAccessOption)
    assert sock.listen(name("qa-download"))
    owner = Companion("qa-download", sock)
    owner.open_settings()
    owner.tick.stop()
    owner.work.timer.stop()
    assert not RUNTIME.exists()
    result = {}
    try:
        for category, caption in (("text", "下载并校验文字模型"), ("vision", "下载并校验视觉模型")):
            button = next(b for b in owner.settings.findChildren(QPushButton) if b.text() == caption)
            started = time.monotonic()
            button.click()
            while owner.downloading and time.monotonic() - started < 1400:
                q.processEvents()
                time.sleep(0.04)
            assert "已校验" in owner.settings.download.text(), owner.settings.download.text()
            result[category + "_download_seconds"] = round(time.monotonic() - started, 2)
            print(category, result[category + "_download_seconds"], flush=True)

        for key in (TEXT, VISION, PROJECTOR, "cpu", "vulkan"):
            engine = key in ("cpu", "vulkan")
            f = RUNTIME / (key + ".zip" if engine else key)
            with f.open("rb") as stream:
                assert sha(stream) == ASSETS[key][1]
            result[key] = dict(sha256=ASSETS[key][1], bytes=f.stat().st_size)
            if engine:
                with zipfile.ZipFile(f) as z:
                    for entry in z.infolist():
                        if not entry.is_dir():
                            path = RUNTIME / ("llama-b12675-" + key) / Path(entry.filename).name
                            with z.open(entry) as reference, path.open("rb") as extracted:
                                assert sha(reference) == sha(extracted)
                result[key]["extraction_matches_archive"] = True
        output.write_text(json.dumps(result, indent=2), encoding="utf8")
    finally:
        owner.shutdown()
        owner.settings.close()
