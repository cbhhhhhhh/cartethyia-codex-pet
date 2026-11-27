"""Decode every installed frame in Qt and compare the pet's rendered frames to the release art."""

import sys
from pathlib import Path
import json, hashlib, time

repo = Path(__file__).resolve().parents[1]
install = Path(sys.argv[1]).resolve()
out = Path(sys.argv[2]).resolve()
out.mkdir(parents=True, exist_ok=True)
sys.path[:0] = [str(install / "windows"), str(install / "src")]
from common import read
from pet import Pet
from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QImage, QPixmap, QPainter, QColor, QFont
from PySide6.QtWidgets import QApplication
from dialogue import gallery

app = QApplication([])
cfg = read(install / "examples/config.json", {})
pet = Pet(cfg)
pet.show()
app.processEvents()
manifest = repo / "art/performances"
assert pet.cliproot == install / "art/performances"
assert read(manifest / "pet-plus.json", {}) == read(pet.cliproot / "pet-plus.json", {})
catalog = json.loads((repo / "art/repertoire.json").read_bytes())


def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def raw(p):
    im = p.toImage().convertToFormat(QImage.Format_RGBA8888)
    return hashlib.sha256(bytes(im.constBits())).hexdigest()


metrics = []
seen = set()
travel = {}


def pump(seconds):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        app.processEvents()
        time.sleep(0.004)


sheet = None
for number, item in enumerate(catalog):
    name = item["title"]
    spec = pet.clips[name]
    relative = Path("clips", item["id"] + ".webp")
    assert Path(spec["file"]) == relative and digest(manifest / relative) == digest(
        pet.cliproot / relative
    )
    atlas = QPixmap(str(manifest / relative))
    count = spec["frames"]
    assert count == 24 and not atlas.isNull()
    ref = [
        atlas.copy(i * (atlas.width() // count), 0, atlas.width() // count, atlas.height())
        for i in range(count)
    ]
    pet.play(name)
    actual = []
    for i in range(count):
        pet.started = time.monotonic() - (i + 0.25) / spec["fps"]
        pix = pet.image()
        actual.append(raw(pix))
        assert actual[-1] == raw(ref[i]), (name, i)
    poses = (0, 6, 12, 20)
    assert len(set(actual)) >= 20 and len({actual[i] for i in poses}) == 4
    assert tuple(actual) not in seen
    seen.add(tuple(actual))
    metrics.append(dict(name=name, unique=len(set(actual)), key_poses=4))
    cell = number % 18
    if cell == 0:
        sheet = QImage(1260, 9 * 134, QImage.Format_RGB32)
        sheet.fill(QColor("#f3f0eb"))
    p = QPainter(sheet)
    p.setFont(QFont("Microsoft YaHei UI", 10))
    p.setPen(QColor("#25373e"))
    x, y = (cell % 2) * 630, (cell // 2) * 134
    p.drawText(x + 10, y + 15, name)
    p.setRenderHint(QPainter.SmoothPixmapTransform)
    for k, i in enumerate(poses):
        p.drawPixmap(QRect(x + k * 151 + 16, y + 18, 103, 112), ref[i])
    p.end()
    if cell == 17 or number == len(catalog) - 1:
        sheet.save(str(out / f"poses-{number//18+1}.jpg"), quality=91)
    if "travel" in spec:
        pet.move(pet.bounds().center() - pet.rect().center())
        start = pet.pos()
        pet.play(name)
        positions = []
        for _ in range(26):
            pump(0.1)
            positions.append(pet.pos())
        dx = max(abs(p.x() - start.x()) for p in positions)
        assert dx >= 50
        if spec["travel"] == "return":
            assert (pet.pos() - start).manhattanLength() <= 1
        travel[name] = dict(
            motion=spec["travel"], max_dx=dx, max_dy=max(abs(p.y() - start.y()) for p in positions)
        )
pictures = gallery(out)
assert len(pictures) == 10 and all(
    digest(Path(p["file"])) == digest(repo / "src/web/portraits" / (k + ".png"))
    for k, p in pictures.items()
)
report = dict(
    clips=len(metrics),
    frames=24 * len(metrics),
    key_poses=4 * len(metrics),
    minimum_unique=min(x["unique"] for x in metrics),
    pixels_match_original_for_all_frames=True,
    matched_file_orientation=True,
    portraits=len(pictures),
    travel=travel,
)
assert len(metrics) == 109 and len(travel) == 7
(out / "art.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf8")
print(json.dumps(report), flush=True)
