"""One private localhost inference process per response. No network fallback."""

import http.client
import json
import os
import secrets
import socket
import subprocess
import tempfile
import time
from pathlib import Path

ACTIONS = ["idle", "waving", "jumping", "waiting", "review", "running", "failed"]
EMOTIONS = ["calm", "happy", "curious", "sad", "focused"]
SCHEMA = {
    "type": "object",
    "properties": {
        "text": {"type": "string"},
        "emotion": {"type": "string", "enum": EMOTIONS},
        "action": {"type": "string", "enum": ACTIONS},
    },
    "required": ["text", "emotion", "action"],
    "additionalProperties": False,
}


def partial_text(raw):
    # Only publish complete decoded string characters, including escaped newlines.
    import re

    m = re.search(r'"text"\s*:\s*"', raw)
    if not m:
        return ""
    s = raw[m.end() - 1 :]
    try:
        return json.JSONDecoder().raw_decode(s)[0]
    except ValueError:
        for drop in range(min(7, len(s))):
            try:
                return json.loads((s[:-drop] if drop else s) + '"')
            except ValueError:
                pass
    return ""


def generate(
    runtime, model, persona, history, user, cancel, publish, image=None, projector=None,
    backend="auto"
):
    models = Path(runtime).resolve()
    filename = Path(model).name
    path = (models / filename).resolve()
    if path.parent != models or path.suffix != ".gguf" or not path.is_file():
        raise RuntimeError("请先安装或选择本地 GGUF 模型")
    server = models / "llama-b12675/llama-server"
    if os.name == "nt":
        gpu = models / "llama-b12675-vulkan/llama-server.exe"
        server = gpu if backend != "cpu" and gpu.exists() else models / "llama-b12675-cpu/llama-server.exe"
    if not server.is_file():
        raise RuntimeError("本地推理程序尚未安装")
    with socket.socket() as pick:
        pick.bind(("127.0.0.1", 0))
        port = pick.getsockname()[1]
    token = secrets.token_hex(32)
    messages = [
        dict(
            role="system",
            content=persona
            + " 用中文简短交流。返回 JSON，text 是给用户的回复，emotion 和 action 选择贴切的值。",
        )
    ]
    for pair in history:
        messages.extend(
            [
                dict(role="user", content=pair["user"][:1200]),
                dict(role="assistant", content=pair["assistant"][:1200]),
            ]
        )
    messages.append(dict(role="user", content=user[:2000]))
    # Bound context even if all stored turns are long.
    while len(messages) > 3 and sum(len(m["content"]) for m in messages) > 3400:
        del messages[1:3]
    extra = []
    if image:
        import base64

        mm = (models / Path(projector or "").name).resolve()
        photo = Path(image)
        if mm.parent != models or mm.suffix != ".gguf" or not mm.is_file():
            raise ValueError("请选择与视觉模型匹配的投影文件")
        if not photo.is_file() or photo.stat().st_size > 8 * 1024 * 1024:
            raise ValueError("图片大小上限为 8 MB")
        raw = photo.read_bytes()
        mime = (
            "image/png"
            if raw.startswith(b"\x89PNG\r\n\x1a\n")
            else "image/jpeg"
            if raw.startswith(b"\xff\xd8\xff")
            else ""
        )
        if not mime:
            raise ValueError("请选择 PNG 或 JPEG")
        url = "data:" + mime + ";base64," + base64.b64encode(raw).decode("ascii")
        messages[-1]["content"] = [
            {"type": "text", "text": user[:2000]},
            {"type": "image_url", "image_url": {"url": url}},
        ]
        extra = ["--mmproj", str(mm)]
    with tempfile.TemporaryDirectory() as private:
        secret = Path(private) / "key"
        with open(
            secret, "x", encoding="ascii", opener=lambda p, flags: os.open(p, flags, 0o600)
        ) as stream:
            stream.write(token)
        proc = subprocess.Popen(
            [
                str(server),
                "-m",
                str(path),
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
                "--api-key-file",
                str(secret),
                "-c",
                "6144",
                "-np",
                "1",
                "--no-webui",
                "--no-warmup",
            ]
            + extra,
            cwd=models,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        import threading

        finished = threading.Event()

        def watch():
            deadline = time.monotonic() + 100
            while not finished.wait(0.08):
                if cancel.is_set() or time.monotonic() > deadline:
                    proc.terminate()
                    return

        threading.Thread(target=watch, daemon=True).start()
        try:
            headers = {
                "Authorization": "Bearer " + token,
                "Content-Type": "application/json",
            }
            for _ in range(250):
                if cancel.is_set():
                    return None
                if proc.poll() is not None:
                    raise RuntimeError("本地模型启动失败")
                conn = http.client.HTTPConnection("127.0.0.1", port, timeout=1)
                try:
                    conn.request("GET", "/health", headers=headers)
                    res = conn.getresponse()
                    res.read()
                    if res.status == 200:
                        break
                except OSError:
                    pass
                finally:
                    conn.close()
                cancel.wait(0.1)
            else:
                raise RuntimeError("本地模型启动超时")
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=60)
            try:
                body = dict(
                    messages=messages,
                    stream=True,
                    max_tokens=240,
                    temperature=0.65,
                    response_format={
                        "type": "json_schema",
                        "json_schema": {"name": "pet_reply", "schema": SCHEMA},
                    },
                )
                conn.request("POST", "/v1/chat/completions", json.dumps(body), headers)
                res = conn.getresponse()
                if res.status != 200:
                    raise RuntimeError("模型拒绝当前请求")
                raw = ""
                last = ""
                for line in res:
                    if cancel.is_set():
                        return None
                    if not line.startswith(b"data:"):
                        continue
                    payload = line[5:].strip()
                    if payload == b"[DONE]":
                        break
                    raw += (
                        json.loads(payload)["choices"][0]["delta"].get("content", "")
                        or ""
                    )
                    visible = partial_text(raw)
                    if visible and visible != last:
                        publish(visible)
                        last = visible
                result = json.loads(raw)
                if (
                    not isinstance(result.get("text"), str)
                    or result.get("action") not in ACTIONS
                    or result.get("emotion") not in EMOTIONS
                ):
                    raise ValueError("invalid reply")
                choices = {
                    "happy": ("jumping", "waving"),
                    "sad": ("failed", "waiting"),
                    "curious": ("review", "waving"),
                    "focused": ("review", "running"),
                    "calm": ("idle", "waving", "waiting"),
                }
                compatible = choices[result["emotion"]]
                if result["action"] not in compatible:
                    result["action"] = compatible[0]
                return result
            finally:
                conn.close()
        finally:
            finished.set()
            if proc.poll() is None:
                proc.terminate()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
