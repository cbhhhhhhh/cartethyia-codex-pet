"""Verify coverage and motion from locally baked RGBA frames in the installed supplement."""

import hashlib
import json
import subprocess
from pathlib import Path

root = Path(__file__).resolve().parents[1]
directory = (
    Path.home()
    / "Library/Application Support/CodexPetPlus/appearance/cartethyia/current"
)
scores = json.loads((root / "art/repertoire.json").read_text())
clips = json.loads((directory / "pet-plus.json").read_text())["clips"]
assert len(clips) == len(scores) == len({s["id"] for s in scores}) == 109
signatures = set()
min_different = 16
for s in scores:
    clip = clips[s["title"]]
    file = directory / clip["file"]
    assert clip["frames"] == 16 and clip["group"] == s["group"]
    proc = subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-i",
            str(file),
            "-vf",
            "untile=16x1,scale=48:52:flags=area,format=rgba",
            "-f",
            "rawvideo",
            "-",
        ],
        stdout=subprocess.PIPE,
        check=True,
    )
    pixels = proc.stdout
    size = 48 * 52 * 4
    assert len(pixels) == 16 * size, (file, len(pixels))
    frames = [pixels[i : i + size] for i in range(0, len(pixels), size)]
    assert all(any(f[3::4]) and min(f[3::4]) == 0 for f in frames)
    min_different = min(min_different, len(set(frames)))
    signatures.add(hashlib.sha256(pixels).hexdigest())
assert len(signatures) == 109 and min_different >= 8,(len(signatures),min_different)
result = dict(
    reference_commit="fb38ce620576f5ed3735a99536d2b1a4a9eb313f",
    listed_reference_actions=109,
    cartethyia_clips=len(clips),
    rgba_frames=16 * len(clips),
    distinct_clips=len(signatures),
    min_distinct_frames_per_clip=min_different,
    transparent_backgrounds=True,
    disk_MiB=round(sum(f.stat().st_size for f in directory.iterdir()) / 1048576, 2),
)
(root / "docs/v2-art-qa.json").write_text(json.dumps(result, indent=2))
print(result)
