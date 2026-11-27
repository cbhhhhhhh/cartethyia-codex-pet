"""Run the installed desktop controls using an isolated test profile."""

from pathlib import Path
import datetime, os, tempfile, sys, time, json

install = Path(sys.argv[1]).resolve()
out = Path(sys.argv[2]).resolve()
sys.path.insert(0, str(install / "windows"))
with tempfile.TemporaryDirectory(prefix="cartethyia-policy-") as tmp:
    os.environ["LOCALAPPDATA"] = tmp
    os.environ["CODEX_HOME"] = str(Path(tmp) / "codex")
    from common import CODEX, DATA, read, write
    from app import QApplication, Companion, QLocalServer
    from transport import name
    from PySide6.QtGui import QImage, QColor
    from PySide6.QtWidgets import QComboBox
    import reminders

    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)

    def companion(key):
        s = QLocalServer()
        s.setSocketOptions(QLocalServer.UserAccessOption)
        assert s.listen(name(key))
        return Companion(key, s)

    a = companion("garden")
    b = companion("library")
    a.history = [{"id": "a", "user": "garden", "assistant": "garden reply"}]
    b.history = [{"id": "b", "user": "library", "assistant": "library reply"}]
    a.save_history()
    b.save_history()
    assert (
        read(a.folder / "memory.json", [])[0]["id"] == "a"
        and read(b.folder / "memory.json", [])[0]["id"] == "b"
    )
    pack = CODEX / "pets/QA-Pack"
    pack.mkdir(parents=True)
    image = QImage(1536, 1872, QImage.Format_ARGB32)
    image.fill(QColor("#ae6655"))
    image.save(str(pack / "qa.png"))
    write(pack / "pet.json", {"displayName": "QA alternate", "spritesheetPath": "qa.png"})
    a.setting("pack", "QA-Pack")
    assert a.pet.image().toImage().pixelColor(30, 30) == QColor("#ae6655")
    assert b.config["pack"] == "cartethyia"
    a.setting("persona", "档案一")
    b.setting("persona", "档案二")
    assert read(a.cfgfile, {})["persona"] != read(b.cfgfile, {})["persona"]
    a.shutdown()
    a.tick.stop()
    a.work.timer.stop()
    a.pet.hide()
    results = {"independent_histories": True, "independent_personas": True, "custom_pack_loaded": True}
    b.setting("whispers", True)
    b.setting("minutes", 5)
    b.setting("muted", True)
    b.setting("focus", True)
    now = datetime.datetime.now().hour
    b.setting("quietStart", now)
    b.setting("quietEnd", (now + 2) % 24)
    begin = time.monotonic()

    def pump(seconds):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            app.processEvents()
            time.sleep(0.05)

    pump(303)
    assert not b.card.isVisible()
    b.setting("muted", False)
    pump(2.5)
    assert not b.card.isVisible()
    b.setting("focus", False)
    pump(2.5)
    assert not b.card.isVisible()
    b.setting("quietEnd", now)
    pump(3)
    assert b.card.mode == "notice" and b.card.isVisible()
    results["real_whisper_after_seconds"] = round(time.monotonic() - begin, 2)
    results["muted_focus_quiet_suppression"] = True
    b.card.close_card()
    reminders.add(
        b.folder, {"text": "时限验收", "due": datetime.datetime.now().astimezone().isoformat()}
    )
    pump(2.5)
    assert "时限验收" in b.card.body.text()
    results["due_notification"] = True
    b.shutdown()
    b.tick.stop()
    b.work.timer.stop()
    b.pet.hide()
    b.card.hide()
    out.write_text(json.dumps(results, indent=2))
    print(results)
