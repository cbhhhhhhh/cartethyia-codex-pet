"""Run the installed desktop controls using an isolated test profile."""

from pathlib import Path
import ctypes, json, os, tempfile, time, sys

install = Path(sys.argv[1]).resolve()
output = Path(sys.argv[2]).resolve()
sys.path.insert(0, str(install / "windows"))
with tempfile.TemporaryDirectory(prefix="cartethyia-keys-") as tmp:
    os.environ["LOCALAPPDATA"] = tmp
    os.environ["CODEX_HOME"] = str(Path(tmp) / "codex")
    from common import read, write, ROOT, DATA
    from app import QApplication, QLocalServer, Companion
    from transport import name

    api = ctypes.windll.user32

    def free(ch):
        tag = 0x1234
        ok = api.RegisterHotKey(None, tag, 3 | 0x4000, ord(ch))
        if ok:
            api.UnregisterHotKey(None, tag)
        return bool(ok)

    first, second = [c for c in "JKXZEWTYUIFGBV" if free(c)][:2]
    cfg = read(ROOT / "examples/config.json", {})
    cfg["shortcut"] = first
    write(DATA / "profiles/keys/config.json", cfg)
    app = QApplication([])
    server = QLocalServer()
    server.setSocketOptions(QLocalServer.UserAccessOption)
    assert server.listen(name("keys"))
    o = Companion("keys", server)
    assert not free(first)
    o.setting("shortcut", second)
    assert free(first) and not free(second)
    for hidden in (True, False):
        api.PostMessageW(int(o.pet.winId()), 0x312, 1, (ord(second) << 16) | 3)
        end = time.monotonic() + 1
        while time.monotonic() < end and o.pet.isVisible() == hidden:
            app.processEvents()
            time.sleep(0.01)
        assert o.pet.isVisible() != hidden
    o.setting("persona", "临时测试人设")
    o.setting("model", "alternate.gguf")
    o.mapping("working", "waving")
    saved = read(o.cfgfile, {})
    assert (
        saved["shortcut"] == second
        and saved["persona"] == "临时测试人设"
        and saved["model"] == "alternate.gguf"
        and saved["mapping"]["working"] == "waving"
    )
    o.shutdown()
    o.pet.hide()
    o.tick.stop()
    o.work.timer.stop()
    assert free(second)
    out = dict(
        shortcut_rebind=True, old_chord_released=True, hide_wake_via_WM_HOTKEY=True, settings_saved=True
    )
    output.write_text(json.dumps(out, indent=2))
    print(out)
