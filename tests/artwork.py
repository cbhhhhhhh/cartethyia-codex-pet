"""Verify coverage and motion from locally baked RGBA frames in the installed supplement."""

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

root = Path(__file__).resolve().parents[1]
directory = (Path.home() / "Applications/Codex Pet Plus.app/Contents/Resources/pets/cartethyia")
if not (directory / "pet-plus.json").exists():
    directory = root / "art/performances"
parser = argparse.ArgumentParser()
parser.add_argument("--directory", type=Path, default=directory)
directory = parser.parse_args().directory
scores = json.loads((root / "art/repertoire.json").read_text())
clips = json.loads((directory / "pet-plus.json").read_text())["clips"]
assert len(clips) == len(scores) == len({s["id"] for s in scores}) == 109
signatures = set()
min_different = 24
min_keys = 4
for s in scores:
    clip = clips[s["title"]]
    file = directory / clip["file"]
    assert clip["frames"] == 24 and clip["group"] == s["group"]
    proc = subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-i",
            str(file),
            "-vf",
            "untile=24x1,scale=48:52:flags=area,format=rgba",
            "-f",
            "rawvideo",
            "-",
        ],
        stdout=subprocess.PIPE,
        check=True,
    )
    pixels = proc.stdout
    size = 48 * 52 * 4
    assert len(pixels) == 24 * size, (file, len(pixels))
    frames = [pixels[i : i + size] for i in range(0, len(pixels), size)]
    assert all(any(f[3::4]) and min(f[3::4]) == 0 for f in frames)
    min_different = min(min_different, len(set(frames)))
    min_keys = min(min_keys, len({frames[i] for i in (0,6,12,20)}))
    signatures.add(hashlib.sha256(pixels).hexdigest())
assert len(signatures) == 109 and min_different >= 12 and min_keys == 4,(len(signatures),min_different)
result = dict(
    reference_commit="fb38ce620576f5ed3735a99536d2b1a4a9eb313f",
    listed_reference_actions=109,
    cartethyia_clips=len(clips),
    rgba_frames=24 * len(clips),
    distinct_keyframes_per_clip=min_keys,
    distinct_clips=len(signatures),
    min_distinct_frames_per_clip=min_different,
    transparent_backgrounds=True,
    disk_MiB=round(sum(f.stat().st_size for f in directory.glob("clips/*.webp")) / 1048576, 2),
)
output = root / ".build/qa/artwork.json"
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps(result, indent=2))
print(result)
