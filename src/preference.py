"""Use public app-server stdio + the Pets MCP connector for one account preference."""

from collections import deque
import json
from pathlib import Path
import os
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import time

BASE = Path.home() / "Library/Application Support/CodexPetPlus"


def codex_error(error):
    obj = error if isinstance(error, dict) else {}
    details = json.dumps(obj, ensure_ascii=False).lower()
    families = (
        (("usagelimitexceeded", "insufficient_quota", "usage limit", "quota exceeded"), "账户额度已用尽，请查看重置时间。"),
        (("unauthorized", "not logged", "authentication", "401"), "账户登录已失效，请在 Codex 重新登录。"),
        (("modelnotfound", "model_not_found", "does not exist", "not supported", "unknown model", "unavailable model"), "所选模型当前不可用，请刷新模型列表或跟随 Codex 默认模型。"),
        (("serveroverloaded", "rate limit", "ratelimit", "429"), "服务繁忙或触发频率限制，请稍后重试。"),
        (("contextwindowexceeded", "context_length"), "对话超过模型上下文长度，可减少记忆轮数。"),
        (("httpconnectionfailed", "disconnected", "connection refused"), "无法连接模型服务，请检查网络。"),
    )
    for terms, message in families:
        if any(term in details for term in terms):
            return message
    return "服务返回错误" + ("（" + str(obj["code"]) + "）" if isinstance(obj.get("code"), int) else "。")


class Rpc:
    def __init__(self, options=(), cwd=None, internal=True):
        exe = shutil.which("codex")
        if not exe and os.name == "nt":
            bins = Path(os.environ["LOCALAPPDATA"]) / "OpenAI/Codex/bin"
            latest = max(bins.glob("*/codex.exe"), key=lambda p: p.stat().st_mtime, default=None)
            exe = str(latest) if latest else None
        if not exe:
            candidates = (
                folder / bundle / "Contents/Resources" / rel
                for folder in (Path("/Applications"), Path.home() / "Applications")
                for bundle in ("ChatGPT.app", "Codex.app")
                for rel in ("codex-cli/CodexCLI.app/Contents/MacOS/codex", "codex")
            )
            exe = next((str(p) for p in candidates if p.is_file() and os.access(p, os.X_OK)), None)
        if not exe:
            raise RuntimeError("请先安装 Codex 桌面版或将 codex 加入 PATH。")
        self.proc = subprocess.Popen(
            [exe, "app-server", "--listen", "stdio://", *options],
            env=dict(os.environ, PET_PLUS_INTERNAL="1" if internal else "0"), cwd=cwd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True, encoding="utf8", creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            bufsize=1,
        )
        self.responses = queue.Queue()
        self.pending = deque(maxlen=4096)

        def read():
            for line in self.proc.stdout:
                try:
                    self.responses.put(json.loads(line))
                except ValueError:
                    pass
            self.responses.put(None)

        threading.Thread(target=read, daemon=True).start()
        self.count = 0

    def send(self, m):
        self.proc.stdin.write(json.dumps(m) + "\n")
        self.proc.stdin.flush()

    def call(self, method, params):
        self.count += 1
        self.send(dict(id=self.count, method=method, params=params))
        deadline = time.monotonic() + 25
        while True:
            try:
                msg = self.responses.get(timeout=max(0, deadline - time.monotonic()))
            except queue.Empty:
                raise RuntimeError("本地 Codex 服务响应超时")
            if msg is None:
                raise RuntimeError("本地 Codex 服务不可用")
            if msg.get("id") != self.count or "method" in msg:
                if "method" in msg:
                    self.pending.append(msg)
                continue
            if "error" in msg:
                raise RuntimeError(
                    method + " · " + codex_error(msg["error"])
                )
            return msg["result"]

    def next_event(self, timeout):
        return self.pending.popleft() if self.pending else self.responses.get(timeout=timeout)

    def close(self):
        try:
            self.proc.stdin.close()
        except BrokenPipeError:
            pass
        try:
            self.proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait()


def run(action):
    file = BASE / "native-account.json"
    if not file.exists() and action != "enable-sync":
        raise ValueError("尚未允许同步宠物选择")
    cfg = json.loads(file.read_text()) if file.exists() else {}
    server = "codex_apps"
    rpc = Rpc()
    try:
        rpc.call(
            "initialize",
            dict(
                clientInfo=dict(name="cartethyia_companion", version="1.0"),
                capabilities=dict(experimentalApi=True),
            ),
        )
        rpc.send(dict(method="initialized", params={}))
        # Ephemeral local thread, no turn or model call. No workspace or chat contents supplied.
        with tempfile.TemporaryDirectory() as cwd:
            session = rpc.call(
                "thread/start",
                dict(
                    cwd=cwd, ephemeral=True, sandbox="read-only", approvalPolicy="never"
                ),
            )
            tid = session["thread"]["id"]
            inventory = rpc.call(
                "mcpServerStatus/list",
                dict(threadId=tid, serverName=server, detail="toolsAndAuthOnly"),
            )
            available = [
                k
                for r in inventory.get("data", [])
                if r.get("name") == server
                for k in r.get("tools", {})
                if k == "pets.select_pet"
            ]
            if len(available) != 1:
                raise RuntimeError(
                    "当前 CLI 未挂载 Pets 连接，可在 Codex 的 Pets 中切换"
                )
            if action == "check":
                return "available"
            if action == "enable-sync" and not cfg:
                listed = rpc.call(
                    "mcpServer/tool/call",
                    dict(
                        threadId=tid,
                        server=server,
                        tool="pets.list_pets",
                        arguments=dict(limit=1),
                    ),
                )

                def active(v):
                    if isinstance(v, dict):
                        if isinstance(v.get("active_pet_id"), str):
                            return v["active_pet_id"]
                        for sub in v.values():
                            found = active(sub)
                            if found:
                                return found
                    if isinstance(v, list):
                        for sub in v:
                            found = active(sub)
                            if found:
                                return found
                    if isinstance(v, str) and v.lstrip().startswith("{"):
                        try:
                            return active(json.loads(v))
                        except ValueError:
                            pass

                previous = active(listed)
                if not previous:
                    raise RuntimeError("无法保存原宠物选择")
                cfg = {"restore_id": previous}
                file.write_text(json.dumps(cfg))
                file.chmod(0o600)
            pet_id = cfg["restore_id"] if action == "restore" else "default"
            result = rpc.call(
                "mcpServer/tool/call",
                dict(
                    threadId=tid,
                    server=server,
                    tool=available[0],
                    arguments=dict(pet_id=pet_id),
                ),
            )

            def match(value):
                if isinstance(value, dict):
                    return value.get("active_pet_id") == pet_id or any(
                        match(v) for v in value.values()
                    )
                if isinstance(value, list):
                    return any(match(v) for v in value)
                if isinstance(value, str) and value.lstrip().startswith("{"):
                    try:
                        return match(json.loads(value))
                    except ValueError:
                        pass
                return False

            if result.get("isError") or not match(result):
                raise RuntimeError("Pets 未确认选择；请在 Codex 中核对")
            cfg["mode"] = "native" if action == "restore" else "companion"
            tmp = file.with_suffix(".tmp")
            tmp.write_text(json.dumps(cfg))
            tmp.chmod(0o600)
            tmp.replace(file)
            return pet_id
    finally:
        rpc.close()


if __name__ == "__main__":
    try:
        action = sys.argv[1]
        if action not in ("check", "restore", "disable", "enable-sync"):
            raise ValueError("无效的选择")
        print(run(action))
    except (
        OSError,
        ValueError,
        KeyError,
        RuntimeError,
        subprocess.TimeoutExpired,
    ) as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)
