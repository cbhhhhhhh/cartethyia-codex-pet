"""Explicit desktop inference routes. A settings change never sends a test prompt."""
import base64
import contextlib
import http.client
import ipaddress
import json
import os
from pathlib import Path
import queue
import re
import socket
import subprocess
import tempfile
import threading
import time
from urllib.parse import urlsplit

from chat import ACTIONS, EMOTIONS, SCHEMA, partial_text
from preference import Rpc, codex_error
from state import VALID_ID


@contextlib.contextmanager
def server(cwd=None, isolate=False):
    options = []
    if isolate:
        for feature in ("plugins", "apps", "shell_tool", "unified_exec", "multi_agent"):
            options += ["--disable", feature]
        options += ["-c", 'web_search="disabled"', "-c", "project_doc_max_bytes=0"]
        conf = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")) / "config.toml"
        try:
            import tomllib
            servers = tomllib.loads(conf.read_text(encoding="utf-8-sig")).get("mcp_servers", {})
        except ImportError:
            servers = re.findall(r'^\s*\[mcp_servers\."?([\w-]+)"?\]', conf.read_text(encoding="utf-8-sig"), re.M) if conf.exists() else []
        except (ValueError, OSError):
            servers = []
        options += ["-c", "mcp_servers={}", "-c", "features.multi_agent_v2=false"]
        for name in servers:
            if re.fullmatch(r"[a-zA-Z0-9_-]+", name):
                options += ["-c", "mcp_servers." + name + ".enabled=false"]
    rpc = Rpc(options, cwd)
    try:
        rpc.call("initialize", {"clientInfo": {"name": "cartethyia_companion", "version": "0.2.0"},
                                "capabilities": {"experimentalApi": True}})
        rpc.send({"method": "initialized", "params": {}})
        yield rpc
    finally:
        rpc.close()


def account(method, **params):
    with server() as rpc:
        return rpc.call(method, params)


def route(cfg, whisper):
    source = cfg.get("chatSource") or "local"
    if whisper and cfg.get("whisperSource") in ("local", "api", "codex"):
        source = cfg["whisperSource"]
    key = {"local": "model", "api": "apiModel", "codex": "codexModel"}.get(source)
    if not key:
        raise ValueError("模型来源无效")
    override = {"local": "whisperModel", "api": "whisperApiModel", "codex": "whisperCodexModel"}[source]
    # Pre-0.2.0 profiles may already have a GGUF exclusively for whispers.
    separate = cfg.get("whisperSource") == source or (not cfg.get("whisperSource") and source == "local")
    model = (cfg.get(override) if whisper and separate else None) or cfg.get(key) or ""
    return source, model


def endpoint(cfg):
    base = urlsplit((cfg.get("apiURL") or "").strip())
    hostname = base.hostname or ""
    try:
        loopback = ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        loopback = hostname == "localhost"
    if not hostname or base.username or base.password or base.query or base.fragment or (
            base.scheme != "https" and not (base.scheme == "http" and loopback)):
        raise ValueError("API 地址需使用 HTTPS；本机服务可以使用 http://127.0.0.1")
    path = base.path.rstrip("/")
    connection = http.client.HTTPSConnection if base.scheme == "https" else http.client.HTTPConnection
    conn = connection(hostname, base.port, timeout=45)
    env_name = (cfg.get("apiKeyEnv") or "").strip()
    if env_name and not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", env_name):
        raise ValueError("API Key 环境变量名无效")
    key = os.environ.get(env_name, "") if env_name else ""
    if not key and os.name == "nt":
        from win_credentials import get_key
        key = get_key(base.scheme + "://" + base.netloc)
    elif not key:
        result = subprocess.run(["/usr/bin/security", "find-generic-password", "-s",
                                 "local.cartethyia.petplus.api", "-a", base.scheme + "://" + base.netloc,
                                 "-w"], capture_output=True, timeout=8)
        if result.returncode == 0:
            key = result.stdout.decode().strip()
    return conn, path, {"Content-Type": "application/json", **({"Authorization": "Bearer " + key} if key else {})}


def list_models(source, cfg):
    if source == "codex":
        models = []
        with server(isolate=True) as rpc:
            cursor = None
            for _ in range(20):
                page = rpc.call("model/list", {"cursor": cursor, "limit": 100})
                models.extend(x["model"] for x in page.get("data", []) if x.get("model"))
                cursor = page.get("nextCursor")
                if not cursor:
                    break
        return list(dict.fromkeys(models))
    conn, prefix, headers = endpoint(cfg)
    try:
        conn.request("GET", prefix + "/models", headers=headers)
        response = conn.getresponse()
        if response.status != 200:
            raise ValueError(f"查询模型失败（HTTP {response.status}）")
        return [m["id"] for m in json.loads(response.read(2_000_000)).get("data", []) if m.get("id")]
    finally:
        conn.close()


def reply(raw):
    try:
        item = json.loads(raw)
    except ValueError as error:
        raise ValueError("模型没有返回要求的回复格式") from error
    if not isinstance(item, dict) or not isinstance(item.get("text"), str) or not item["text"].strip():
        raise ValueError("模型没有返回文字")
    return {"text": item["text"][:3000],
            "action": item.get("action") if item.get("action") in ACTIONS else "idle",
            "emotion": item.get("emotion") if item.get("emotion") in EMOTIONS else "calm"}


def api_chat(cfg, model, messages, cancel, publish, image=None):
    if not model:
        raise ValueError("请选择或填写 API 模型名")
    if image:
        raw = Path(image).read_bytes()
        if len(raw) > 8 * 1024 * 1024:
            raise ValueError("图片超过 8 MB")
        mime = "image/png" if raw.startswith(b"\x89PNG") else "image/jpeg" if raw.startswith(b"\xff\xd8") else ""
        if not mime:
            raise ValueError("请选择 PNG 或 JPEG")
        messages[-1] = dict(role="user", content=[
            {"type": "text", "text": messages[-1]["content"]},
            {"type": "image_url", "image_url": {"url": "data:" + mime + ";base64," + base64.b64encode(raw).decode()}}])
    conn, prefix, headers = endpoint(cfg)
    finished = threading.Event()
    stream_socket = None
    def watch():
        while not finished.wait(.15):
            if cancel.is_set():
                active_socket = stream_socket or conn.sock
                if active_socket:
                    try:
                        active_socket.shutdown(socket.SHUT_RDWR)
                    except OSError:
                        pass
                return
    threading.Thread(target=watch, daemon=True).start()
    try:
        body = dict(model=model, messages=messages, stream=True, stream_options={"include_usage": True},
                    response_format={"type": "json_object"})
        for attempt in range(2):
            conn.request("POST", prefix + "/chat/completions", json.dumps(body), headers)
            response = conn.getresponse()
            if response.status == 200:
                break
            status = response.status
            error = response.read(16384).lower()
            if attempt == 0 and status in (400, 422) and any(k in error for k in (b"stream_options", b"response_format")):
                body.pop("stream_options", None)
                body.pop("response_format", None)
                conn.close()
                continue
            raise ValueError(f"API 服务返回 HTTP {status}，请检查地址、模型和凭据")
        stream_socket = getattr(getattr(response.fp, "raw", None), "_sock", None)
        result, count, previous = "", None, ""
        for line in response:
            if cancel.is_set():
                return None
            if not line.startswith(b"data:"):
                continue
            data = line[5:].strip()
            if data == b"[DONE]":
                break
            event = json.loads(data)
            if event.get("usage"):
                count = event["usage"].get("total_tokens")
            choices = event.get("choices") or []
            if choices:
                result += choices[0].get("delta", {}).get("content") or ""
                if len(result) > 64000:
                    raise ValueError("回复过长")
                visible = partial_text(result)
                if previous != visible:
                    publish(visible)
                    previous = visible
        if cancel.is_set():
            return None
        return dict(reply(result), usageTokens=count)
    finally:
        finished.set()
        conn.close()


def codex_chat(base, model, messages, cancel, publish, image=None):
    with tempfile.TemporaryDirectory(prefix="cartethyia-") as cwd, server(cwd, isolate=True) as rpc:
        params = dict(cwd=cwd, ephemeral=True, sandbox="read-only", approvalPolicy="never",
                      threadSource="cartethyia_companion", baseInstructions=messages[0]["content"] +
                      "\n你是桌宠，只回复 JSON。禁止调用工具、读取文件或运行命令。")
        if model:
            params["model"] = model
        desc = rpc.call("thread/start", params)
        tid = desc["thread"]["id"]
        if not VALID_ID.fullmatch(tid):
            raise ValueError("Codex 返回的会话标识无效")
        marker = base / "pet-threads" / tid
        marker.parent.mkdir(mode=0o700, exist_ok=True)
        marker.touch(mode=0o600)
        entries = [{"type": "text", "text": json.dumps(messages[1:], ensure_ascii=False)}]
        if image:
            entries.append({"type": "localImage", "path": str(Path(image).resolve())})
        if cancel.is_set():
            return None
        turn = rpc.call("turn/start", dict(threadId=tid, input=entries, outputSchema=SCHEMA))
        turn_id = turn["turn"]["id"]
        deadline = time.monotonic() + 100
        raw, count, visible = "", None, ""
        latest_error = {}
        while True:
            if cancel.is_set() or time.monotonic() > deadline:
                rpc.send({"id": 99999, "method": "turn/interrupt", "params": {"threadId": tid, "turnId": turn_id}})
                if cancel.is_set():
                    return None
                raise RuntimeError("Codex 回复超时")
            try:
                m = rpc.next_event(timeout=.12)
            except queue.Empty:
                continue
            if m is None:
                raise RuntimeError("Codex 连接已关闭")
            method, p = m.get("method"), m.get("params", {})
            if "id" in m and method:
                rpc.send({"id": m["id"], "error": {"code": -32601, "message": "Companion allows text replies only"}})
                continue
            if p.get("threadId") != tid or (p.get("turnId") and p["turnId"] != turn_id):
                continue
            if method == "error":
                latest_error = p.get("error") or {}
            elif method == "thread/tokenUsage/updated":
                count = (p.get("tokenUsage", {}).get("total") or {}).get("totalTokens")
            elif method == "item/agentMessage/delta":
                raw += p.get("delta", "")
                partial = partial_text(raw)
                if partial and partial != visible:
                    publish(partial)
                    visible = partial
            elif method == "item/completed" and p.get("item", {}).get("type") == "agentMessage":
                raw = p["item"].get("text") or raw
            elif method == "turn/completed" and p.get("turn", {}).get("id") == turn_id:
                if p["turn"].get("status") not in ("completed", "complete"):
                    raise RuntimeError(codex_error(p["turn"].get("error") or latest_error))
                return dict(reply(raw), usageTokens=count)
