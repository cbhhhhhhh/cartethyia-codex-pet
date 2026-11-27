"""Synthetic requests only. Keep the temporary account cache outside the repository."""

import contextlib
import json
import os
import queue
import shutil
import tempfile
import time
from pathlib import Path


@contextlib.contextmanager
def account_home(family=False):
    original = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")
    with tempfile.TemporaryDirectory(prefix="Cartethyia-test-") as d:
        root = Path(d)
        work = root / "empty"
        work.mkdir()
        home = root / "codex"
        home.mkdir()
        for name in ("auth.json", "models_cache.json"):
            if (original / name).exists():
                shutil.copyfile(original / name, home / name)
        config = [
            'model="gpt-6.2-sol"',
            "project_doc_max_bytes=0",
            'web_search="disabled"',
            "[features]",
            "plugins=false",
            "apps=false",
            "multi_agent_v2=" + str(family).lower(),
            "[agents]",
            "max_threads=3",
            "max_depth=1",
            "[windows]",
            'sandbox="unelevated"',
        ]
        (home / "config.toml").write_text("\n".join(config) + "\n", encoding="utf8")
        old = os.environ.get("CODEX_HOME")
        os.environ["CODEX_HOME"] = str(home)
        try:
            yield home, work
        finally:
            if old is None:
                os.environ.pop("CODEX_HOME", None)
            else:
                os.environ["CODEX_HOME"] = old


def initialize(rpc):
    rpc.call(
        "initialize",
        {
            "clientInfo": {"name": "cartethyia_windows_qa", "version": "0.2.0"},
            "capabilities": {"experimentalApi": True},
        },
    )
    rpc.send({"method": "initialized", "params": {}})


def probe():
    from preference import Rpc

    with account_home() as (_, work):
        rpc = Rpc(cwd=work, internal=False)
        try:
            initialize(rpc)
            thread = rpc.call(
                "thread/start",
                dict(
                    cwd=str(work),
                    sandbox="read-only",
                    approvalPolicy="never",
                    ephemeral=True,
                    baseInstructions="Arithmetic only. Do not use tools.",
                ),
            )["thread"]["id"]
            turn = rpc.call(
                "turn/start",
                dict(
                    threadId=thread,
                    input=[{"type": "text", "text": "Reply only with the digit equal to 2+3."}],
                    effort="low",
                ),
            )["turn"]["id"]
            text = ""
            end = time.monotonic() + 100
            while time.monotonic() < end:
                try:
                    m = rpc.next_event(0.5)
                except queue.Empty:
                    continue
                if m is None:
                    break
                p = m.get("params", {})
                if p.get("threadId") != thread:
                    continue
                if m.get("method") == "item/completed" and p["item"]["type"] == "agentMessage":
                    text = p["item"].get("text", "").strip()
                if m.get("method") == "turn/completed" and p["turn"]["id"] == turn:
                    return p["turn"]["status"] == "completed" and text.strip(".。 \n") == "5"
            return False
        finally:
            rpc.close()
