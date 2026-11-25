"""Exercise both a red and a blue PNG through the local GGUF vision path."""

import json
from pathlib import Path
import struct
import sys
import tempfile
import threading
import zlib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from chat import generate

runtime = Path.home() / "Library/Application Support/CodexPetPlus/runtime"


def png(color):
    def chunk(kind, body):
        return (
            struct.pack(">I", len(body))
            + kind
            + body
            + struct.pack(">I", zlib.crc32(kind + body))
        )

    side = 128
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", side, side, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress((b"\0" + bytes(color) * side) * side))
        + chunk(b"IEND", b"")
    )


with tempfile.TemporaryDirectory() as td:
    results = {}
    for name, pixels in [("red", (255, 0, 0)), ("blue", (0, 0, 255))]:
        img = Path(td, "test.png")
        img.write_bytes(png(pixels))
        reply = generate(
            runtime,
            "Qwen3VL-2B-Instruct-Q4_K_M.gguf",
            "Describe the image to the user.",
            [],
            "What color fills the entire image? Answer only its color.",
            threading.Event(),
            lambda s: None,
            image=str(img),
            projector="mmproj-Qwen3VL-2B-Instruct-Q8_0.gguf",
        )
        results[name] = reply["text"]
    print(results)
    (ROOT / "docs/vision-qa.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2)
    )
