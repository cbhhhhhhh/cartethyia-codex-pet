"""Local stdio MCP. No Codex credentials and no connectivity."""

import json
import sys
import os
from pathlib import Path
from reminders import add, complete

base = Path.home() / "Library/Application Support/CodexPetPlus"


def tool(name, desc, props, required):
    return dict(
        name=name,
        description=desc,
        inputSchema=dict(
            type="object",
            properties=props,
            required=required,
            additionalProperties=False,
        ),
    )


string = dict(type="string")
tools = [
    tool("pet_status", "Read latest local pet work state", {}, []),
    tool(
        "pet_remind",
        "Add a local due reminder",
        dict(text=string, due=string, thread=string),
        ["text", "due"],
    ),
    tool("pet_complete", "Complete a local reminder", dict(id=string), ["id"]),
]


def dispatch(m, p):
    if m == "initialize":
        return dict(
            protocolVersion=p.get("protocolVersion", "2024-11-05"),
            capabilities=dict(tools={}),
            serverInfo=dict(name="pet-plus", version="1.0"),
        )
    if m == "ping":
        return {}
    if m == "tools/list":
        return dict(tools=tools)
    if m != "tools/call":
        raise ValueError("unknown method")
    n = p["name"]
    args = p.get("arguments", {})
    if n == "pet_status":
        path = base / "profiles/main/status.json"
        d = (
            json.loads(path.read_text())
            if path.exists() and (base / "events.sock").is_socket()
            else {"state": "idle", "online": False}
        )
    elif n == "pet_remind":
        d = add(base, args)
    elif n == "pet_complete":
        d = complete(base, args["id"])
    else:
        raise ValueError("unknown tool")
    return dict(content=[{"type": "text", "text": json.dumps(d, ensure_ascii=False)}])


os.umask(0o077)
for line in sys.stdin:
    req = {}
    try:
        req = json.loads(line)
        if not isinstance(req, dict):
            req = {}
            raise ValueError("invalid message")
        if "id" not in req:
            continue
        out = {"result": dispatch(req["method"], req.get("params", {}))}
    except Exception:
        out = {
            "error": {
                "code": -32602,
                "message": "Invalid request or local store unavailable",
            }
        }
    print(json.dumps(dict(jsonrpc="2.0", id=req.get("id"), **out)), flush=True)
