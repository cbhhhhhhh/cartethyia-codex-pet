"""Content-addressed local images and per-profile conversation records."""

import hashlib
import os
from pathlib import Path
import uuid


def context(pairs, rounds):
    count = max(0, min(50, int(rounds)))
    return pairs[-count:] if count else []


def normalize(records):
    return [
        dict(item, id=item.get("id") or str(uuid.uuid4()))
        for item in records
        if isinstance(item, dict)
        and isinstance(item.get("user"), str)
        and isinstance(item.get("assistant"), str)
    ]


def keep_image(folder, source):
    with Path(source).open("rb") as f:
        data = f.read(8 * 1024 * 1024 + 1)
    if len(data) > 8 * 1024 * 1024:
        raise ValueError("图片上限为 8 MB")
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        ext = ".png"
    elif data.startswith(b"\xff\xd8\xff"):
        ext = ".jpg"
    else:
        raise ValueError("请选择 PNG 或 JPEG")
    target = folder / "images" / (hashlib.sha256(data).hexdigest() + ext)
    target.parent.mkdir(mode=0o700, exist_ok=True)
    if not target.exists():
        tmp = target.with_suffix(".tmp")
        tmp.write_bytes(data)
        os.replace(tmp, target)
    return str(target)
